#!/usr/bin/env node
/*
 * Deterministic, no-agent video editor.
 *
 * npm run edit -- <file-or-url> --edit highlights --target 60 --subtitles --grade auto --vertical
 * npm run edit -- <file-or-url> --edit silence-cut --grade none
 *
 * The selection is deliberately heuristic: it ranks timestamped Scribe phrases
 * and never calls an LLM. For nuanced editorial choices, use the existing
 * conversation-led Video Use workflow instead.
 */

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const lib = require('./lib');

// New primary modes share the persistent creator engine. Keep legacy syntax below.
if (['highlights', 'youtube', 'shorts', 'project', 'transcribe', '--help', '-h'].includes(process.argv[2]) || process.argv.length === 2) {
  const result = spawnSync(process.execPath, [path.join(__dirname, 'editor.js'), '--mode-cli', ...process.argv.slice(2)], { stdio: 'inherit', windowsHide: true });
  process.exit(result.status ?? 1);
}

const ROOT = __dirname;
const VIDEO_USE = path.join(ROOT, 'video-use');
const HELP = `Usage: npm run edit -- <file-or-url> [options]

Options:
  --edit highlights|silence-cut   Editing preset (default: highlights)
  --target 60|1m30s               Target duration for highlights
  --vertical                      Render a 1080x1920 social version
  --subtitles                     Burn word-timed captions into the output
  --grade auto|none|neutral_punch|warm_cinematic  Per-clip color grade (default: auto)
  --language en                   Optional Scribe language code
  --preview                       Faster 1080p preview render
  --overlay <file>@<seconds>      Add a pre-rendered MP4/WebM overlay (repeatable)

URLs need yt-dlp: python -m pip install yt-dlp
Outputs are written to <source-folder>/edit/.`;

function die(message) { console.error(`\nError: ${message}`); process.exit(1); }

function run(command, args, options = {}) {
  return new Promise((resolve, reject) => {
    const child = spawn(command, args, { stdio: 'inherit', windowsHide: true, ...options });
    child.on('error', (err) => reject(new Error(`Could not run ${command}: ${err.message}`)));
    child.on('close', (code) => code === 0 ? resolve() : reject(new Error(`${command} exited with code ${code}`)));
  });
}

function findPython() {
  const candidates = [process.env.PYTHON, 'python3', 'python', 'py'].filter(Boolean);
  if (process.platform === 'win32' && process.env.LOCALAPPDATA) {
    candidates.push(path.join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python312', 'python.exe'));
  }
  for (const command of candidates) {
    const args = command === 'py' ? ['-3', '--version'] : ['--version'];
    const result = spawnSync(command, args, { stdio: 'ignore', windowsHide: true });
    if (!result.error && result.status === 0) return command;
  }
  die('Python 3.10+ is required. Install it, then set PYTHON if it is not on PATH.');
}

function pythonArgs(python, args) { return python === 'py' ? ['-3', ...args] : args; }

function parseDuration(value) {
  if (!value) return null;
  if (/^\d+(?:\.\d+)?$/.test(value)) return Number(value);
  const match = /^(?:(\d+(?:\.\d+)?)h)?(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?$/i.exec(value);
  if (!match || !match.slice(1).some(Boolean)) die(`Bad duration "${value}". Use seconds, e.g. 60 or 1m30s.`);
  return (Number(match[1] || 0) * 3600) + (Number(match[2] || 0) * 60) + Number(match[3] || 0);
}

function isUrl(value) { return /^https?:\/\//i.test(value); }

async function downloadUrl(url, python) {
  const dir = require('./download').downloadsDirectory();
  fs.mkdirSync(dir, { recursive: true });
  const manifest = path.join(dir, 'download-path.txt');
  if (fs.existsSync(manifest)) fs.unlinkSync(manifest);
  await run(python, pythonArgs(python, ['-m', 'yt_dlp', '--no-playlist', '--merge-output-format', 'mp4', '--print-to-file', 'after_move:filepath', manifest, '-o', path.join(dir, '%(title).180B-%(id)s.%(ext)s'), url]));
  const files = fs.existsSync(manifest) ? fs.readFileSync(manifest, 'utf8').trim().split(/\r?\n/).filter((name) => fs.existsSync(name)) : [];
  if (!files.length) die('yt-dlp finished but did not create a video file.');
  return files.sort((a, b) => fs.statSync(b).mtimeMs - fs.statSync(a).mtimeMs)[0];
}

function phrasesFromTranscript(data) {
  const words = (data.words || []).filter((word) => word.type === 'word'
    && Number.isFinite(word.start) && Number.isFinite(word.end) && String(word.text || '').trim());
  const phrases = [];
  let current = [];
  const flush = () => {
    if (!current.length) return;
    const start = current[0].start;
    const end = current[current.length - 1].end;
    if (end - start >= 0.45) phrases.push({ start, end, text: current.map((word) => word.text.trim()).join(' ') });
    current = [];
  };
  for (const word of words) {
    const previous = current[current.length - 1];
    if (previous && (word.start - previous.end >= 0.55 || current.length >= 22)) flush();
    current.push(word);
    if (/[.!?]$/.test(String(word.text).trim()) && current.length >= 4) flush();
  }
  flush();
  return phrases;
}

function score(phrase, index, total) {
  const text = phrase.text.toLowerCase();
  const words = text.split(/\s+/).filter(Boolean).length;
  const signal = /\b(important|key|best|first|finally|because|how|why|result|lesson|tip|secret|problem|solution|launch|new|never|always)\b/g;
  const hits = (text.match(signal) || []).length;
  const punctuation = /[!?]/.test(text) ? 1.2 : 0;
  const opening = index < Math.max(2, Math.ceil(total * 0.08)) ? 1.5 : 0;
  return Math.min(words, 18) / 6 + hits * 2 + punctuation + opening;
}

function selectRanges(phrases, preset, target) {
  if (preset === 'silence-cut') return phrases.map((phrase) => ({ ...phrase, beat: 'SPEECH' }));
  const ranked = phrases.map((phrase, index) => ({ ...phrase, score: score(phrase, index, phrases.length) }))
    .sort((a, b) => b.score - a.score || a.start - b.start);
  const chosen = [];
  let used = 0;
  for (const phrase of ranked) {
    const duration = phrase.end - phrase.start;
    if (used && used + duration > target + 3) continue;
    chosen.push({ ...phrase, beat: 'HIGHLIGHT' });
    used += duration;
    if (used >= target) break;
  }
  if (!chosen.length && phrases.length) chosen.push({ ...phrases[0], beat: 'HIGHLIGHT' });
  return chosen.sort((a, b) => a.start - b.start);
}

function mergeRanges(ranges, sourceKey) {
  const merged = [];
  for (const range of ranges) {
    const start = Math.max(0, range.start - 0.08);
    const end = range.end + 0.12;
    const prior = merged[merged.length - 1];
    if (prior && start - prior.end <= 0.65 && end - prior.start <= 35) {
      prior.end = end;
      prior.quote += ` ${range.text}`;
    } else {
      merged.push({ source: sourceKey, start, end, beat: range.beat, quote: range.text, reason: 'Automatic transcript-based selection.' });
    }
  }
  return merged;
}

function parseOverlays(values) {
  return values.map((value) => {
    if (!value) die('Missing value after --overlay. Use <file>@<seconds>.');
    const at = value.lastIndexOf('@');
    if (at <= 0 || !Number.isFinite(Number(value.slice(at + 1)))) die(`Bad overlay "${value}". Use <file>@<seconds>.`);
    const file = path.resolve(value.slice(0, at));
    if (!fs.existsSync(file)) die(`Overlay not found: ${file}`);
    return { file, start_in_output: Number(value.slice(at + 1)), duration: 5 };
  });
}

async function main() {
  const argv = process.argv.slice(2);
  const overlays = [];
  for (let i = argv.length - 1; i >= 0; i--) {
    if (argv[i] === '--overlay') { overlays.unshift(argv[i + 1]); argv.splice(i, 2); }
  }
  const { flags, positional } = lib.parseArgs(argv, ['edit', 'target', 'grade', 'language', 'output']);
  const known = ['edit','target','grade','language','output','vertical','subtitles','preview','help'];
  const unknown = Object.keys(flags).filter((name) => !known.includes(name));
  if (unknown.length) die(`Unknown legacy option --${unknown[0]}. Use npm run edit -- highlights|youtube|shorts "video.mp4" --help for the new interface.`);
  const input = positional[0];
  if (!input || flags.help) { console.log(HELP); return; }
  if (!fs.existsSync(VIDEO_USE)) die('video-use is not installed. Clone it into this repository first.');
  const preset = flags.edit || 'highlights';
  if (!['highlights', 'silence-cut'].includes(preset)) die('--edit must be highlights or silence-cut.');
  const python = findPython();
  console.warn('Legacy edit syntax: prefer npm run edit -- highlights|youtube|shorts "video.mp4". Legacy Scribe behavior still applies.');
  process.env.PYTHONUTF8 = '1';
  const tools = lib.ffTools();
  if (path.isAbsolute(tools.ffmpeg)) process.env.PATH = `${path.dirname(tools.ffmpeg)}${path.delimiter}${process.env.PATH}`;
  const source = isUrl(input) ? await downloadUrl(input, python) : path.resolve(input);
  if (!fs.existsSync(source)) die(`Video not found: ${source}`);
  // video-use's Python helpers invoke ffmpeg by name. Preserve the absolute
  // path discovered by this project's cross-platform FFmpeg lookup so a shell
  // opened before a PATH update still works.
  const { ffmpeg } = lib.ffTools();
  process.env.PATH = `${path.dirname(ffmpeg)}${path.delimiter}${process.env.PATH}`;
  const info = lib.probe(source);
  if (!info.hasVideo || !info.hasAudio) die('The input must contain both video and audio.');
  const editDir = path.join(process.env.LOCALAPPDATA || require('os').tmpdir(), 'VideoEditor', 'Cache', 'legacy', path.basename(source, path.extname(source)));
  fs.mkdirSync(editDir, { recursive: true });
  const target = parseDuration(flags.target) || (preset === 'silence-cut' ? info.duration : Math.min(Math.max(30, info.duration * 0.2), 600));

  console.log(`\nSource: ${source}\nPreset: ${preset}\nTarget: ${lib.fmtDuration(target)}\n`);
  await run(python, pythonArgs(python, [path.join(VIDEO_USE, 'helpers', 'transcribe.py'), source, '--edit-dir', editDir,
    ...(flags.language ? ['--language', flags.language] : [])]));
  const transcript = path.join(editDir, 'transcripts', `${path.basename(source, path.extname(source))}.json`);
  if (!fs.existsSync(transcript)) die(`Expected transcript was not written: ${transcript}`);
  const phrases = phrasesFromTranscript(JSON.parse(fs.readFileSync(transcript, 'utf8')));
  if (!phrases.length) die('No speech was found. Use the existing silence.js / cut.js workflow for music-only footage.');
  const sourceKey = path.basename(source, path.extname(source));
  const ranges = mergeRanges(selectRanges(phrases, preset, target), sourceKey);
  const edl = {
    version: 1,
    sources: { [sourceKey]: source },
    ranges,
    grade: flags.grade || (preset === 'highlights' ? 'none' : 'auto'),
    overlays: parseOverlays(overlays),
    total_duration_s: ranges.reduce((sum, range) => sum + range.end - range.start, 0),
    ...(flags.vertical ? { aspect: 'vertical' } : {}),
  };
  const edlFile = path.join(editDir, 'edl.auto.json');
  fs.writeFileSync(edlFile, JSON.stringify(edl, null, 2));
  const output = path.join(editDir, `${preset}${flags.vertical ? '-vertical' : ''}${flags.subtitles ? '-subtitled' : ''}.mp4`);
  await run(python, pythonArgs(python, [path.join(VIDEO_USE, 'helpers', 'render.py'), edlFile, '-o', output,
    ...(preset === 'highlights' ? ['--no-loudnorm'] : []),
    ...(flags.subtitles ? ['--build-subtitles'] : []),
    ...(flags.preview ? ['--preview'] : [])]));
  const destination = path.resolve(flags.output || path.dirname(source));
  fs.mkdirSync(destination, { recursive: true });
  const stem = `${path.basename(source, path.extname(source))}-${preset}${flags.vertical ? '-vertical' : ''}${flags.preview ? '-preview' : ''}`;
  let delivered;
  for (let index = 0; ; index++) {
    delivered = path.join(destination, `${stem}${index ? '-' + index : ''}.mp4`);
    try { fs.copyFileSync(output, delivered, fs.constants.COPYFILE_EXCL); break; }
    catch (error) { if (error.code !== 'EEXIST') throw error; }
  }
  console.log(`\nDone: ${delivered}\nEDL (cache): ${edlFile}`);
}

main().catch((error) => die(error.message));
