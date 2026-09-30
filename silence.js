#!/usr/bin/env node
// silence.js — find stretches of dead air with FFmpeg's silencedetect.
//
//   node silence.js <video> [--noise -30] [--min 1.0] [--pad 0.25]
//
//   --noise  loudness (dB) below which audio counts as silence (default -30;
//            try -35 for quiet recordings, -25 for noisy rooms)
//   --min    shortest silence to report, in seconds (default 1.0)
//   --pad    seconds of silence to keep either side of speech (default 0.25)
//
// Writes to output/<videoname>/:
//   silence.json          [{start, end, duration}] silent stretches
//   no-silence.json       the parts WITH sound, in segments.json format, so
//                         `node cut.js <video> output/<name>/no-silence.json --no-fade`
//                         removes the dead air.

const fs = require('fs');
const path = require('path');
const lib = require('./lib');

async function main() {
  const { flags, positional } = lib.parseArgs(process.argv.slice(2), ['noise', 'min', 'pad']);
  const video = positional[0];
  if (!video || flags.help) lib.die('Usage: node silence.js <video> [--noise -30] [--min 1.0] [--pad 0.25]');
  const noise = Number(flags.noise ?? -30);
  const min = Number(flags.min ?? 1.0);
  const pad = Number(flags.pad ?? 0.25);

  const info = lib.probe(video);
  if (!info.hasAudio) lib.die('This video has no audio track.');
  const outDir = lib.outputDir(video);

  // silencedetect logs "silence_start: 12.3" / "silence_end: 15.6 | silence_duration: 3.3"
  // at info level on stderr. -vn skips decoding video, so this is fast.
  const log = await lib.runFfmpeg(['-i', video, '-vn', '-af', `silencedetect=noise=${noise}dB:d=${min}`, '-f', 'null', '-'],
    { duration: info.duration, label: 'Scanning audio', logLevel: 'info' });

  const silences = [];
  let start = null;
  for (const line of log.split(/\r?\n/)) {
    let m;
    if ((m = /silence_start:\s*(-?[\d.]+)/.exec(line))) start = Math.max(0, parseFloat(m[1]));
    else if ((m = /silence_end:\s*([\d.]+)/.exec(line)) && start !== null) {
      silences.push({ start, end: parseFloat(m[1]) });
      start = null;
    }
  }
  // Silence that runs to the end of the file has no silence_end line.
  if (start !== null) silences.push({ start, end: info.duration });

  // The inverse: stretches with sound, keeping `pad` seconds of breathing room.
  const keep = [];
  let cursor = 0;
  for (const s of silences) {
    if (s.end - s.start <= 2 * pad) continue; // too short to cut once padded
    const end = Math.min(s.start + pad, info.duration);
    if (end - cursor > 0.1) keep.push({ start: cursor, end });
    cursor = Math.max(cursor, s.end - pad);
  }
  if (info.duration - cursor > 0.1) keep.push({ start: cursor, end: info.duration });

  const fmt = (t) => lib.formatTime(t);
  fs.writeFileSync(path.join(outDir, 'silence.json'), JSON.stringify(
    silences.map((s) => ({ start: fmt(s.start), end: fmt(s.end), duration: +(s.end - s.start).toFixed(2) })), null, 2));
  fs.writeFileSync(path.join(outDir, 'no-silence.json'), JSON.stringify(
    keep.map((k) => ({ start: fmt(k.start), end: fmt(k.end), reason: 'speech' })), null, 2));

  const total = silences.reduce((a, s) => a + s.end - s.start, 0);
  console.log(`\n${silences.length} silent stretches (< ${noise} dB, >= ${min}s):`);
  for (const s of silences) console.log(`  [${fmt(s.start)} - ${fmt(s.end)}]  ${(s.end - s.start).toFixed(1)}s`);
  console.log(`\nDead air: ${lib.fmtDuration(total)} of ${lib.fmtDuration(info.duration)} (${((total / info.duration) * 100).toFixed(1)}%)`);
  console.log(`  ${path.join(outDir, 'silence.json')}`);
  console.log(`  ${path.join(outDir, 'no-silence.json')}  (feed to cut.js with --no-fade to trim dead air)`);
}

main().catch((e) => lib.die(e.message));
