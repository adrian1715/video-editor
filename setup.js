#!/usr/bin/env node
// setup.js — check/install everything the pipeline needs.
//
//   node setup.js                 check FFmpeg, fetch whisper.cpp + the "small" model
//   node setup.js --model medium  also fetch another model
//
// On Windows the prebuilt whisper.cpp binary is downloaded from GitHub, so no
// C++ compiler or CMake is needed. On macOS/Linux it tells you what to install.

const { spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const { ROOT, IS_WIN, findFfTool, findWhisper, parseArgs, progressBar, die } = require('./lib');

const MODELS_DIR = path.join(ROOT, 'models');
const BIN_DIR = path.join(ROOT, 'bin');
const MODEL_URL = (name) => `https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-${name}.bin`;

// Download a URL to a file with a progress bar (Node's built-in fetch).
async function download(url, dest, label) {
  const res = await fetch(url, { redirect: 'follow', headers: { 'User-Agent': 'video-highlights-setup' } });
  if (!res.ok) throw new Error(`Download failed (${res.status}): ${url}`);
  const total = Number(res.headers.get('content-length')) || 0;
  const tmp = dest + '.part';
  const out = fs.createWriteStream(tmp);
  const bar = progressBar(label);
  let got = 0;
  for await (const chunk of res.body) {
    got += chunk.length;
    if (!out.write(chunk)) await new Promise((r) => out.once('drain', r));
    if (total) bar.update(got / total);
  }
  await new Promise((r, j) => out.end((e) => (e ? j(e) : r())));
  bar.done();
  fs.renameSync(tmp, dest); // only "complete" once fully downloaded
}

// Download a whisper model (e.g. "small", "medium") into ./models if missing.
async function ensureModel(name) {
  const file = path.join(MODELS_DIR, `ggml-${name}.bin`);
  if (fs.existsSync(file)) return file;
  fs.mkdirSync(MODELS_DIR, { recursive: true });
  console.log(`Downloading whisper model "${name}" (one-time)...`);
  await download(MODEL_URL(name), file, `  ggml-${name}.bin`);
  return file;
}

// Windows: fetch the newest official prebuilt CPU build of whisper.cpp.
// Tagged releases don't always carry binaries, so we scan recent releases
// for the first one that has whisper-bin-x64.zip attached.
async function installWhisperWindows() {
  const asset = 'whisper-bin-x64.zip';
  const res = await fetch('https://api.github.com/repos/ggml-org/whisper.cpp/releases?per_page=20', {
    headers: { 'User-Agent': 'video-highlights-setup' },
  });
  if (!res.ok) throw new Error(`GitHub API error ${res.status}`);
  const releases = await res.json();
  const rel = releases.find((r) => r.assets.some((a) => a.name === asset));
  if (!rel) throw new Error(`No release with ${asset} found`);
  const url = rel.assets.find((a) => a.name === asset).browser_download_url;

  fs.mkdirSync(BIN_DIR, { recursive: true });
  const zip = path.join(BIN_DIR, asset);
  console.log(`Downloading whisper.cpp ${rel.tag_name} (prebuilt Windows binary)...`);
  await download(url, zip, `  ${asset}`);
  const dest = path.join(BIN_DIR, 'whisper');
  fs.rmSync(dest, { recursive: true, force: true });
  fs.mkdirSync(dest, { recursive: true });
  // Windows 10+ ships bsdtar, which extracts .zip files. Use its full path so
  // Git Bash's GNU tar (which can't read zips or C:\ paths) isn't picked up.
  const tar = path.join(process.env.SystemRoot || 'C:\\Windows', 'System32', 'tar.exe');
  const r = spawnSync(tar, ['-xf', zip, '-C', dest], { stdio: 'inherit' });
  if (r.status !== 0) throw new Error('Could not extract ' + zip);
  fs.rmSync(zip);
}

async function main() {
  const { flags } = parseArgs(process.argv.slice(2), ['model']);
  console.log(`OS: ${process.platform} ${process.arch}, Node ${process.version}\n`);
  let ok = true;

  // 1. FFmpeg
  const ffmpeg = findFfTool('ffmpeg');
  const ffprobe = findFfTool('ffprobe');
  if (ffmpeg && ffprobe) {
    console.log(`[ok] FFmpeg: ${ffmpeg}`);
  } else {
    ok = false;
    console.log('[missing] FFmpeg. Install it with:');
    if (IS_WIN) console.log('    winget install --id Gyan.FFmpeg -e');
    else if (process.platform === 'darwin') console.log('    brew install ffmpeg');
    else console.log('    sudo apt install ffmpeg   (or your distro\'s equivalent)');
  }

  // 2. whisper.cpp
  let whisper = findWhisper();
  if (!whisper && IS_WIN && process.arch === 'x64') {
    try { await installWhisperWindows(); whisper = findWhisper(); }
    catch (e) { console.log(`  whisper.cpp download failed: ${e.message}`); }
  }
  if (whisper) {
    console.log(`[ok] whisper.cpp: ${whisper}`);
  } else {
    ok = false;
    console.log('[missing] whisper.cpp (whisper-cli). Install it with:');
    if (process.platform === 'darwin') console.log('    brew install whisper-cpp');
    else console.log('    git clone https://github.com/ggml-org/whisper.cpp && cd whisper.cpp && cmake -B build && cmake --build build -j --config Release\n    then set WHISPER_CLI=/path/to/whisper.cpp/build/bin/whisper-cli');
  }

  // 3. Models (small by default, plus --model if given)
  for (const name of new Set(['small', flags.model].filter(Boolean))) {
    try { console.log(`[ok] model: ${await ensureModel(name)}`); }
    catch (e) { ok = false; console.log(`[missing] model "${name}": ${e.message}`); }
  }

  console.log(ok ? '\nAll set. Try: node transcribe.js <video>' : '\nSome pieces are missing; see above.');
  process.exit(ok ? 0 : 1);
}

if (require.main === module) main().catch((e) => die(e.message));
module.exports = { ensureModel };
