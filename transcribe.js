#!/usr/bin/env node
// transcribe.js — extract audio with FFmpeg and transcribe it with whisper.cpp.
//
//   node transcribe.js <video> [--model small|medium|...] [--language pt|en|auto]
//
// Writes to output/<videoname>/:
//   transcript.txt   [00:02:14.00 - 00:02:41.50] text
//   transcript.srt   standard subtitles
//   meta.json        duration, detected language, model used

const { spawn } = require('child_process');
const fs = require('fs');
const path = require('path');
const lib = require('./lib');
const { ensureModel } = require('./setup');

const USAGE = 'Usage: node transcribe.js <video> [--model small|medium] [--language auto|pt|en]';

async function main() {
  const { flags, positional } = lib.parseArgs(process.argv.slice(2), ['model', 'language', 'threads']);
  const video = positional[0];
  if (!video || flags.help) lib.die(USAGE);

  const model = flags.model || 'small';
  if (!/^[\w.-]+$/.test(model)) lib.die(`Bad model name "${model}"`);
  const language = flags.language || 'auto';
  // whisper.cpp scales well up to ~8 threads; beyond that gains are small.
  const threads = Number(flags.threads) || Math.min(8, lib.os.cpus().length);

  const whisper = lib.findWhisper();
  if (!whisper) lib.die('whisper.cpp not found. Run `node setup.js` first.');
  const modelFile = await ensureModel(model);

  const info = lib.probe(video);
  if (!info.hasAudio) lib.die('This video has no audio track to transcribe.');
  const outDir = lib.outputDir(video);
  console.log(`Video: ${video} (${lib.fmtDuration(info.duration)})`);
  console.log(`Output: ${outDir}\n`);

  // 1. Audio: 16 kHz mono 16-bit WAV is exactly what whisper expects.
  //    (-vn skips decoding the video, so this is fast even for huge files.)
  const wav = path.join(outDir, 'audio.wav');
  await lib.runFfmpeg(['-i', video, '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', wav],
    { duration: info.duration, label: 'Extracting audio' });

  // 2. Transcribe.
  const t0 = Date.now();
  const { segments, language: detected } = await runWhisper(whisper, {
    modelFile, outDir, language, threads, duration: info.duration,
  });
  fs.rmSync(wav, { force: true }); // ~115 MB per hour of audio; no need to keep it

  // 3. Write transcript.txt and transcript.srt.
  const txt = segments.map((s) => `[${lib.formatTime(s.start)} - ${lib.formatTime(s.end)}] ${s.text}`).join('\n');
  fs.writeFileSync(path.join(outDir, 'transcript.txt'), txt + '\n', 'utf8');

  const srt = segments.map((s, i) => [
    i + 1,
    `${lib.formatTime(s.start, { decimals: 3, sep: ',' })} --> ${lib.formatTime(s.end, { decimals: 3, sep: ',' })}`,
    s.text,
    '',
  ].join('\n')).join('\n');
  fs.writeFileSync(path.join(outDir, 'transcript.srt'), srt, 'utf8');

  fs.writeFileSync(path.join(outDir, 'meta.json'), JSON.stringify({
    video: path.resolve(video), duration: info.duration, language: detected, model,
  }, null, 2));

  console.log(`\nDone in ${lib.fmtDuration((Date.now() - t0) / 1000)}. Language: ${detected}, ${segments.length} segments.`);
  console.log(`  ${path.join(outDir, 'transcript.txt')}`);
  console.log(`  ${path.join(outDir, 'transcript.srt')}`);
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
      const jsonFile = path.join(outDir, 'whisper.json');
      const json = JSON.parse(fs.readFileSync(jsonFile, 'utf8'));
      fs.rmSync(jsonFile, { force: true });
      const segments = (json.transcription || [])
        .map((s) => ({ start: s.offsets.from / 1000, end: s.offsets.to / 1000, text: s.text.trim() }))
        .filter((s) => s.text);
      resolve({ segments, language: json.result?.language || detected });
    });
  });
}

main().catch((e) => lib.die(e.message));
