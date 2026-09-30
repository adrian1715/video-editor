#!/usr/bin/env node
// cut.js — cut segments out of a video and join them into a highlights reel.
//
//   node cut.js <video> [segments.json] [--vertical] [--separate] [--no-fade]
//               [--fade 0.3] [--cpu]
//
// segments.json: [{"start": "00:02:14.00", "end": "00:02:41.50", "reason": "..."}]
// (defaults to output/<videoname>/segments.json)
//
// Output (in output/<videoname>/):
//   highlights.mp4            joined reel (highlights-vertical.mp4 with --vertical)
//   clips/01-<reason>.mp4     one file per segment with --separate (clips-vertical/ with --vertical)
//
// Every segment is re-encoded, so cuts land on the exact frame even when the
// timestamp isn't on a keyframe.

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const lib = require('./lib');

const USAGE = 'Usage: node cut.js <video> [segments.json] [--vertical] [--separate] [--no-fade] [--fade 0.3] [--cpu]';

// H.264 encoders to try, fastest first. `pix` is the pixel format each wants.
const ENCODERS = [
  { name: 'h264_nvenc', pix: 'yuv420p', args: ['-preset', 'p5', '-rc', 'vbr', '-cq', '23', '-b:v', '0'] }, // NVIDIA
  { name: 'h264_qsv', pix: 'nv12', args: ['-preset', 'medium', '-global_quality', '23'] },                // Intel Quick Sync
  { name: 'h264_amf', pix: 'nv12', args: ['-quality', 'quality', '-rc', 'cqp', '-qp_i', '21', '-qp_p', '23'] }, // AMD
  { name: 'h264_videotoolbox', pix: 'nv12', args: ['-q:v', '65'] },                                      // macOS
];
const SOFTWARE = { name: 'libx264', pix: 'yuv420p', args: ['-preset', 'veryfast', '-crf', '20'] };

// Pick the first hardware encoder that actually works on this machine
// (FFmpeg lists encoders it was built with, not ones the hardware supports),
// by encoding a few frames of a test pattern.
function pickEncoder(forceCpu) {
  if (forceCpu) return SOFTWARE;
  const { ffmpeg } = lib.ffTools();
  for (const enc of ENCODERS) {
    const r = spawnSync(ffmpeg, ['-hide_banner', '-loglevel', 'error', '-f', 'lavfi', '-i', 'color=black:s=640x360:d=0.2',
      '-vf', `format=${enc.pix}`, '-c:v', enc.name, ...enc.args, '-f', 'null', '-'], { stdio: 'ignore', timeout: 20000, windowsHide: true });
    if (r.status === 0) return enc;
  }
  return SOFTWARE;
}

// Read, validate and normalise segments.json -> [{start, end, dur, reason}] in seconds.
function loadSegments(file, duration) {
  let raw;
  try { raw = JSON.parse(fs.readFileSync(file, 'utf8')); }
  catch (e) { lib.die(`Could not read ${file}: ${e.message}`); }
  if (!Array.isArray(raw) || !raw.length) lib.die(`${file} must be a non-empty JSON array`);

  return raw.map((s, i) => {
    const n = i + 1;
    let start, end;
    try { start = lib.parseTime(s.start); end = lib.parseTime(s.end); }
    catch (e) { lib.die(`Segment ${n}: ${e.message}`); }
    if (end > duration) {
      console.warn(`Segment ${n}: end ${s.end} is past the end of the video; clamping.`);
      end = duration;
    }
    if (!(end > start) || start < 0) lib.die(`Segment ${n}: start (${s.start}) must be before end (${s.end}) and inside the video`);
    return { start, end, dur: end - start, reason: String(s.reason || '') };
  });
}

// Video filter chain: constant frame rate, size (landscape or 9:16), fades.
function videoFilter({ fps, vertical, fade, dur, pix }) {
  const f = [`fps=${fps}`];
  if (vertical) {
    // Centre-crop to 9:16 (keeps full height of a landscape video), then scale to 1080x1920.
    f.push("crop='min(iw,trunc(ih*9/16/2)*2)':'min(ih,trunc(iw*16/9/2)*2)'", 'scale=1080:1920');
  } else {
    f.push('scale=trunc(iw/2)*2:trunc(ih/2)*2'); // H.264 needs even dimensions
  }
  f.push('setsar=1');
  if (fade > 0) f.push(`fade=t=in:st=0:d=${fade}`, `fade=t=out:st=${(dur - fade).toFixed(3)}:d=${fade}`);
  f.push(`format=${pix}`);
  return f.join(',');
}

function audioFilter({ fade, dur }) {
  const f = ['aresample=48000:async=1'];
  if (fade > 0) f.push(`afade=t=in:st=0:d=${fade}`, `afade=t=out:st=${(dur - fade).toFixed(3)}:d=${fade}`);
  return f.join(',');
}

// Encode one segment to `outFile`. `audio` is 'pcm' (intermediate part for
// joining) or 'aac' (standalone clip).
async function encodeSegment(video, seg, outFile, opts, label) {
  const fade = opts.fade > 0 ? Math.min(opts.fade, seg.dur / 4) : 0;
  const build = (enc) => {
    const args = ['-ss', seg.start.toFixed(3), '-i', video];
    // Videos without audio get a silent track so every part has the same layout.
    if (!opts.hasAudio) args.push('-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo');
    args.push('-t', seg.dur.toFixed(3),
      '-map', '0:v:0', '-map', opts.hasAudio ? '0:a:0' : '1:a:0',
      '-vf', videoFilter({ fps: opts.fps, vertical: opts.vertical, fade, dur: seg.dur, pix: enc.pix }),
      '-af', audioFilter({ fade, dur: seg.dur }),
      '-c:v', enc.name, ...enc.args,
      ...(opts.audio === 'pcm' ? ['-c:a', 'pcm_s16le'] : ['-c:a', 'aac', '-b:a', '192k']),
      '-ar', '48000', '-ac', '2', '-sn', '-dn', '-map_metadata', '-1');
    if (outFile.endsWith('.mp4')) args.push('-movflags', '+faststart');
    args.push(outFile);
    return args;
  };
  try {
    await lib.runFfmpeg(build(opts.encoder), { duration: seg.dur, label });
  } catch (e) {
    if (opts.encoder === SOFTWARE) throw e;
    console.warn(`  ${opts.encoder.name} failed on this segment, retrying with libx264...`);
    await lib.runFfmpeg(build(SOFTWARE), { duration: seg.dur, label });
  }
}

// "Key insight: nobody cares!" -> "key-insight-nobody-cares"
function slug(text) {
  return text.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/[^a-z0-9]+/g, '-').replace(/^-|-$/g, '').slice(0, 40).replace(/-$/, '');
}

async function main() {
  const { flags, positional } = lib.parseArgs(process.argv.slice(2), ['fade']);
  const [video, segArg] = positional;
  if (!video || flags.help) lib.die(USAGE);

  const info = lib.probe(video);
  if (!info.hasVideo) lib.die('No video stream found in ' + video);
  const outDir = lib.outputDir(video);
  const segFile = segArg || path.join(outDir, 'segments.json');
  const segments = loadSegments(segFile, info.duration);

  const encoder = pickEncoder(flags.cpu);
  const opts = {
    fps: info.fps,
    hasAudio: info.hasAudio,
    vertical: !!flags.vertical,
    fade: flags['no-fade'] ? 0 : (flags.fade !== undefined ? Number(flags.fade) : 0.3),
    encoder,
  };
  const suffix = opts.vertical ? '-vertical' : '';
  console.log(`Encoder: ${encoder.name}${encoder === SOFTWARE ? '' : ' (hardware)'}, ${opts.vertical ? '1080x1920 vertical' : 'original size'}, fade ${opts.fade}s\n`);

  if (flags.separate) {
    // One standalone clip per segment. Clear old clips so removed segments don't linger.
    const clipDir = path.join(outDir, 'clips' + suffix);
    fs.rmSync(clipDir, { recursive: true, force: true });
    fs.mkdirSync(clipDir, { recursive: true });
    for (const [i, seg] of segments.entries()) {
      const name = `${String(i + 1).padStart(2, '0')}${seg.reason ? '-' + slug(seg.reason) : ''}.mp4`;
      await encodeSegment(video, seg, path.join(clipDir, name), { ...opts, audio: 'aac' }, `[${i + 1}/${segments.length}] Clip`);
    }
    console.log(`\nClips written to ${clipDir}`);
  } else {
    // Encode parts, then join them. Parts use PCM audio so the join is gapless
    // and AAC is only encoded once, at the end.
    const partsDir = path.join(outDir, '.parts');
    fs.rmSync(partsDir, { recursive: true, force: true });
    fs.mkdirSync(partsDir, { recursive: true });
    const list = [];
    for (const [i, seg] of segments.entries()) {
      const part = `part-${String(i + 1).padStart(3, '0')}.mkv`;
      await encodeSegment(video, seg, path.join(partsDir, part), { ...opts, audio: 'pcm' }, `[${i + 1}/${segments.length}] Segment`);
      list.push(`file '${part}'`);
    }
    const listFile = path.join(partsDir, 'list.txt');
    fs.writeFileSync(listFile, list.join('\n') + '\n');
    const out = path.join(outDir, `highlights${suffix}.mp4`);
    const total = segments.reduce((a, s) => a + s.dur, 0);
    await lib.runFfmpeg(['-f', 'concat', '-safe', '0', '-i', listFile,
      '-c:v', 'copy', '-c:a', 'aac', '-b:a', '192k', '-movflags', '+faststart', out],
    { duration: total, label: 'Joining         ' });
    fs.rmSync(partsDir, { recursive: true, force: true });
    console.log(`\nWrote ${out}`);
  }

  // Summary table so it's easy to decide what to add/remove.
  const total = segments.reduce((a, s) => a + s.dur, 0);
  console.log('\n  #  start        end          length  reason');
  segments.forEach((s, i) => console.log(
    `${String(i + 1).padStart(3)}  ${lib.formatTime(s.start)}  ${lib.formatTime(s.end)}  ${lib.fmtDuration(s.dur).padStart(6)}  ${s.reason}`));
  console.log(`\nTotal: ${lib.fmtDuration(total)} of ${lib.fmtDuration(info.duration)} ` +
    `(${((total / info.duration) * 100).toFixed(1)}% of the original kept)`);
}

main().catch((e) => lib.die(e.message));
