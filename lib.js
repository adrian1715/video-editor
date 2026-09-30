// Shared helpers for the highlights pipeline: finding tools, running FFmpeg
// with a progress bar, time formatting, and output paths.
// Only Node built-ins are used, so there is nothing to `npm install`.

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = __dirname;
const IS_WIN = process.platform === 'win32';
const EXE = IS_WIN ? '.exe' : '';

// ---------------------------------------------------------------------------
// Tool discovery
// ---------------------------------------------------------------------------

// True if `cmd -version` (or similar) runs successfully.
function works(cmd, args = ['-version']) {
  const r = spawnSync(cmd, args, { stdio: 'ignore', windowsHide: true });
  return !r.error && r.status === 0;
}

// Recursively look for a file by name (used for winget installs and the
// unzipped whisper.cpp release, whose folder layout can change between builds).
function findFile(dir, name, depth = 4) {
  if (depth < 0 || !fs.existsSync(dir)) return null;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isFile() && entry.name.toLowerCase() === name.toLowerCase()) return full;
    if (entry.isDirectory()) {
      const found = findFile(full, name, depth - 1);
      if (found) return found;
    }
  }
  return null;
}

// Locate ffmpeg/ffprobe: $FFMPEG_DIR, then PATH, then the winget install
// folder (winget updates PATH, but only for terminals opened afterwards).
function findFfTool(name) {
  if (process.env.FFMPEG_DIR) {
    const p = path.join(process.env.FFMPEG_DIR, name + EXE);
    if (fs.existsSync(p)) return p;
  }
  if (works(name)) return name;
  if (IS_WIN && process.env.LOCALAPPDATA) {
    const p = findFile(path.join(process.env.LOCALAPPDATA, 'Microsoft', 'WinGet', 'Packages'), name + EXE, 4);
    if (p) return p;
  }
  return null;
}

// Locate the whisper.cpp CLI: $WHISPER_CLI, then ./bin (downloaded by
// setup.js), then PATH (e.g. `brew install whisper-cpp` on macOS).
function findWhisper() {
  if (process.env.WHISPER_CLI && fs.existsSync(process.env.WHISPER_CLI)) return process.env.WHISPER_CLI;
  const local = findFile(path.join(ROOT, 'bin'), 'whisper-cli' + EXE, 4);
  if (local) return local;
  if (works('whisper-cli', ['--help'])) return 'whisper-cli';
  return null;
}

let _ff = null;
// Returns { ffmpeg, ffprobe } or exits with a helpful message.
function ffTools() {
  if (_ff) return _ff;
  const ffmpeg = findFfTool('ffmpeg');
  const ffprobe = findFfTool('ffprobe');
  if (!ffmpeg || !ffprobe) die('FFmpeg not found. Run `node setup.js` to install it or see README.md.');
  return (_ff = { ffmpeg, ffprobe });
}

// ---------------------------------------------------------------------------
// Media info
// ---------------------------------------------------------------------------

// Basic facts about a video: duration (s), frame rate, whether it has audio.
function probe(file) {
  if (!fs.existsSync(file)) die(`File not found: ${file}`);
  const r = spawnSync(ffTools().ffprobe, [
    '-v', 'error', '-print_format', 'json', '-show_format', '-show_streams', file,
  ], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, windowsHide: true });
  if (r.status !== 0) die(`ffprobe could not read ${file}:\n${r.stderr}`);
  const info = JSON.parse(r.stdout);
  const video = info.streams.find((s) => s.codec_type === 'video' && !s.disposition?.attached_pic);
  const audio = info.streams.find((s) => s.codec_type === 'audio');
  // avg_frame_rate is e.g. "30000/1001"; fall back to r_frame_rate, then 30.
  let fps = '30';
  for (const rate of [video?.avg_frame_rate, video?.r_frame_rate]) {
    const [n, d] = String(rate || '0/0').split('/').map(Number);
    if (n > 0 && d > 0 && n / d <= 120) { fps = `${n}/${d}`; break; }
  }
  // Phones record variable frame rate, so the average comes out as e.g.
  // 949660000/31677209 (29.98). Snap to the nearest standard rate if within 0.5%.
  const [fn, fd] = fps.split('/').map(Number);
  const standard = ['24000/1001', '24', '25', '30000/1001', '30', '50', '60000/1001', '60', '120'];
  const err = (s) => { const [a, b = 1] = s.split('/').map(Number); return Math.abs(a / b - fn / fd) / (fn / fd); };
  const snap = standard.reduce((best, s) => (err(s) < err(best) ? s : best));
  if (err(snap) < 0.005) fps = snap;
  return {
    duration: parseFloat(info.format.duration) || 0,
    hasVideo: !!video,
    hasAudio: !!audio,
    width: video?.width,
    height: video?.height,
    fps,
  };
}

// ---------------------------------------------------------------------------
// Running FFmpeg with a progress bar
// ---------------------------------------------------------------------------

// Run ffmpeg with `args`. If `duration` is given, a progress bar is drawn from
// FFmpeg's machine-readable -progress output. Resolves with FFmpeg's stderr
// (some tools, like silencedetect, report their results there).
function runFfmpeg(args, { duration = 0, label = 'ffmpeg', logLevel = 'error' } = {}) {
  return new Promise((resolve, reject) => {
    const full = ['-hide_banner', '-nostdin', '-y', '-loglevel', logLevel, '-progress', 'pipe:1', '-nostats', ...args];
    const child = spawn(ffTools().ffmpeg, full, { windowsHide: true });
    const bar = progressBar(label);
    let stderr = '';
    let buf = '';
    child.stdout.on('data', (chunk) => {
      buf += chunk;
      let i;
      while ((i = buf.indexOf('\n')) >= 0) {
        const line = buf.slice(0, i).trim();
        buf = buf.slice(i + 1);
        const m = /^out_time_us=(\d+)/.exec(line);
        if (m && duration > 0) bar.update(Number(m[1]) / 1e6 / duration);
      }
    });
    child.stderr.on('data', (chunk) => { stderr += chunk; });
    child.on('error', reject);
    child.on('close', (code) => {
      if (code === 0) { bar.done(); resolve(stderr); }
      else { bar.fail(); reject(new Error(`ffmpeg exited with code ${code}\n${stderr.trim().slice(-2000)}`)); }
    });
  });
}

// A tiny progress bar. In a terminal it redraws one line; when output is
// piped (logs, CI) it prints a line every 10% instead.
function progressBar(label) {
  const tty = process.stderr.isTTY;
  const start = Date.now();
  let lastPct = -1;
  const draw = (pct, final) => {
    const elapsed = (Date.now() - start) / 1000;
    const eta = pct > 0 && !final ? ` ETA ${fmtDuration((elapsed / pct) * (100 - pct))}` : ` ${fmtDuration(elapsed)}`;
    const width = 24;
    const filled = Math.round((pct / 100) * width);
    const line = `${label} [${'#'.repeat(filled)}${'-'.repeat(width - filled)}] ${String(pct).padStart(3)}%${eta}`;
    if (tty) process.stderr.write(`\r${line.padEnd(78)}${final ? '\n' : ''}`);
    else process.stderr.write(line + '\n');
  };
  return {
    update(fraction) {
      const pct = Math.max(0, Math.min(100, Math.floor(fraction * 100)));
      if (pct === lastPct || pct === 100) return;
      if (!tty && pct - lastPct < 10 && lastPct >= 0) return;
      lastPct = pct;
      draw(pct, false);
    },
    done() { draw(100, true); },
    fail() { if (tty) process.stderr.write('\n'); },
  };
}

// ---------------------------------------------------------------------------
// Time helpers
// ---------------------------------------------------------------------------

// "01:02:03.50" / "02:03.5" / "123.5" / 123.5  ->  seconds
function parseTime(t) {
  if (typeof t === 'number') return t;
  const parts = String(t).trim().replace(',', '.').split(':').map(Number);
  if (!parts.length || parts.some((n) => Number.isNaN(n))) throw new Error(`Bad timestamp: "${t}"`);
  return parts.reduce((acc, n) => acc * 60 + n, 0);
}

// seconds -> "HH:MM:SS.cc" (sep="." , 2 decimals) or SRT "HH:MM:SS,mmm"
function formatTime(sec, { decimals = 2, sep = '.' } = {}) {
  const scale = 10 ** decimals;
  const total = Math.round(Math.max(0, sec) * scale);
  const frac = total % scale;
  const s = Math.floor(total / scale);
  const pad = (n, w = 2) => String(n).padStart(w, '0');
  return `${pad(Math.floor(s / 3600))}:${pad(Math.floor(s / 60) % 60)}:${pad(s % 60)}${sep}${pad(frac, decimals)}`;
}

// seconds -> "1h 02m 03s" style, for humans
function fmtDuration(sec) {
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor(sec / 60) % 60, s = sec % 60;
  if (h) return `${h}h ${String(m).padStart(2, '0')}m`;
  if (m) return `${m}m ${String(s).padStart(2, '0')}s`;
  return `${s}s`;
}

// ---------------------------------------------------------------------------
// Misc
// ---------------------------------------------------------------------------

// output/<videoname>/ (created if missing)
function outputDir(video) {
  const name = path.basename(video, path.extname(video));
  const dir = path.join(ROOT, 'output', name);
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

// Minimal flag parser: `--flag`, `--key value`, `--key=value`; rest are positionals.
function parseArgs(argv, valueFlags = []) {
  const flags = {};
  const positional = [];
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (!a.startsWith('--')) { positional.push(a); continue; }
    const [key, inline] = a.slice(2).split('=');
    if (inline !== undefined) flags[key] = inline;
    else if (valueFlags.includes(key)) flags[key] = argv[++i];
    else flags[key] = true;
  }
  return { flags, positional };
}

function die(msg) {
  console.error(`\nError: ${msg}`);
  process.exit(1);
}

module.exports = {
  ROOT, IS_WIN, EXE, os,
  works, findFile, findFfTool, findWhisper, ffTools,
  probe, runFfmpeg, progressBar,
  parseTime, formatTime, fmtDuration,
  outputDir, parseArgs, die,
};
