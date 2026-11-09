#!/usr/bin/env node
// transcribe.js — extract audio with FFmpeg and transcribe it with whisper.cpp.
//
//   node transcribe.js <video> [--model small|medium|...] [--language pt|en|auto]
//
// Saves transcript.txt/.srt and meta.json in <video>-transcript/ beside the
// source, or under --output. Repeated exports get a new numbered folder.
// Intermediate WAV/Whisper JSON stays in a unique system temporary directory.

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const lib = require('./lib');
const { ensureModel } = require('./setup');

const USAGE = 'Usage: node transcribe.js <video> [--output <directory>] [--model small|medium] [--language auto|pt|en] [--threads 8]';

async function main(argv = process.argv.slice(2), dependencies = {}) {
  const runtime = { ...lib, ...dependencies.lib };
  const { flags, positional } = runtime.parseArgs(argv, ['model', 'language', 'threads', 'output']);
  if (flags.help) { console.log(USAGE); return; }
  if (!positional[0]) throw new Error(USAGE);
  if (argv.some((arg) => arg === '--output' || arg.startsWith('--output=')) && (typeof flags.output !== 'string' || !flags.output.trim() || flags.output.startsWith('--'))) {
    throw new Error('--output requires a destination directory.');
  }
  const unknown = Object.keys(flags).find((key) => !['model', 'language', 'threads', 'output', 'help'].includes(key));
  if (unknown) throw new Error(`Unknown option --${unknown}. ${USAGE}`);
  if (positional.length !== 1) throw new Error(`Provide exactly one video path. ${USAGE}`);
  const video = path.resolve(positional[0]);

  const model = flags.model || 'small';
  if (!/^[\w.-]+$/.test(model)) lib.die(`Bad model name "${model}"`);
  const language = flags.language || 'auto';
  // whisper.cpp scales well up to ~8 threads; beyond that gains are small.
  const threads = Number(flags.threads) || Math.min(8, lib.os.cpus().length);

  const whisper = runtime.findWhisper();
  if (!whisper) throw new Error('whisper.cpp not found. Run `node setup.js` first.');
  const modelFile = await (dependencies.ensureModel || ensureModel)(model);

  const info = runtime.probe(video);
  if (!info.hasAudio) throw new Error('This video has no audio track to transcribe.');
  const outDir = flags.output ? path.resolve(flags.output) : path.dirname(video);
  fs.mkdirSync(outDir, { recursive: true });
  const workDir = fs.mkdtempSync(path.join(runtime.os.tmpdir(), 'video-editor-whisper-'));
  console.log(`Video: ${video} (${lib.fmtDuration(info.duration)})`);
  console.log(`Output: ${outDir}\n`);

  // 1. Audio: 16 kHz mono 16-bit WAV is exactly what whisper expects.
  //    (-vn skips decoding the video, so this is fast even for huge files.)
  const wav = path.join(workDir, 'audio.wav');
  try {
    await runtime.runFfmpeg(['-i', video, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav],
      { duration: info.duration, label: 'Extracting audio' });

    // 2. Transcribe.
    const t0 = Date.now();
    const { segments, language: detected } = await (dependencies.runWhisper || runWhisper)(whisper, {
      modelFile, outDir: workDir, language, threads, duration: info.duration,
    });
    fs.rmSync(wav, { force: true }); // ~115 MB per hour of audio; no need to keep it

    // 3. Save a grouped export without overwriting older transcript folders.
    const files = writeTranscripts(video, outDir, segments, {
      video, duration: info.duration, language: detected, model,
    });
    console.log(`\nDone in ${lib.fmtDuration((Date.now() - t0) / 1000)}. Language: ${detected}, ${segments.length} segments.`);
    for (const file of Object.values(files)) console.log(`  ${file}`);
    fs.rmSync(workDir, { recursive: true, force: true });
    return files;
  } catch (error) {
    throw new Error(`${error.message}\nTemporary files retained at ${workDir}`);
  }
}

function writeTranscripts(video, outDir, segments, metadata) {
  fs.mkdirSync(outDir, { recursive: true });
  const stem = path.basename(video, path.extname(video)) + '-transcript';
  let folder;
  for (let index = 0; ; index++) {
    folder = path.join(outDir, stem + (index ? '-' + index : ''));
    try {
      // mkdir is exclusive: existing folders, files and links are never reused.
      fs.mkdirSync(folder);
      break;
    } catch (error) {
      if (error.code !== 'EEXIST') throw error;
    }
  }
  const files = { txt: path.join(folder, 'transcript.txt'), srt: path.join(folder, 'transcript.srt'), meta: path.join(folder, 'meta.json') };
  const txt = segments.map((s) => `[${lib.formatTime(s.start)} - ${lib.formatTime(s.end)}] ${s.text}`).join('\n');
  fs.writeFileSync(files.txt, txt + '\n', 'utf8');

  const srt = segments.map((s, i) => [
    i + 1,
    `${lib.formatTime(s.start, { decimals: 3, sep: ',' })} --> ${lib.formatTime(s.end, { decimals: 3, sep: ',' })}`,
    s.text,
    '',
  ].join('\n')).join('\n');
  fs.writeFileSync(files.srt, srt, 'utf8');

  fs.writeFileSync(files.meta, JSON.stringify(metadata, null, 2), 'utf8');
  return files;
}

// Run whisper-cli and return { segments: [{start, end, text}], language }.
// Progress comes from the timestamps whisper prints as it finishes each segment.
function runWhisper(whisper, { modelFile, outDir, language, threads, duration }) {
  return new Promise((resolve, reject) => {
    // Run inside outDir with relative file names: whisper.cpp can struggle with
    // non-ASCII paths on Windows (e.g. "Episódio 1.mp4").
    const args = ['-m', modelFile, '-f', 'audio.wav', '-l', language, '-t', String(threads),
      '-oj', '-of', 'whisper'];
    const child = spawn(whisper, args, { cwd: outDir, windowsHide: true });
    const bar = lib.progressBar('Transcribing    ');
    let stderr = '';
    let buf = '';
    let detected = language;

    child.stdout.setEncoding('utf8');
    child.stdout.on('data', (chunk) => {
      buf += chunk;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i);
        buf = buf.slice(i + 1);
        // e.g. "[00:01:02.340 --> 00:01:05.120]   text"
        const m = /-->\s*(\d+:\d+:\d+[.,]\d+)\]/.exec(line);
        if (m && duration) bar.update(lib.parseTime(m[1]) / duration);
      }
    });
    child.stderr.setEncoding('utf8');
    child.stderr.on('data', (chunk) => {
      stderr += chunk;
      const m = /auto-detected language:\s*(\w+)/.exec(stderr);
      if (m) detected = m[1];
    });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code !== 0) { bar.fail(); return reject(new Error(`whisper-cli exited with code ${code}\n${stderr.slice(-2000)}`)); }
      bar.done();
      try {
        const jsonFile = path.join(outDir, 'whisper.json');
        const json = JSON.parse(fs.readFileSync(jsonFile, 'utf8'));
        fs.rmSync(jsonFile, { force: true });
        const segments = (json.transcription || [])
          .map((s) => ({ start: s.offsets.from / 1000, end: s.offsets.to / 1000, text: s.text.trim() }))
          .filter((s) => s.text);
        resolve({ segments, language: json.result?.language || detected });
      } catch (error) { reject(error); }
    });
  });
}

if (require.main === module) main().catch((e) => lib.die(e.message));
module.exports = { main, writeTranscripts };
