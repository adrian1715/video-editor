#!/usr/bin/env node
// Download one supported video URL without starting an edit.
// Usage: npm run download -- <url> [--output <directory>]

const { spawn, spawnSync } = require('child_process');
const fs = require('fs');
const path = require('path');
const lib = require('./lib');

const USAGE = 'Usage: npm run download -- <video-url> [--output <directory>]';

function findPython() {
  const candidates = [process.env.PYTHON, 'python', 'py'].filter(Boolean);
  if (process.platform === 'win32' && process.env.LOCALAPPDATA) {
    candidates.push(path.join(process.env.LOCALAPPDATA, 'Programs', 'Python', 'Python312', 'python.exe'));
  }
  for (const command of candidates) {
    const args = command === 'py' ? ['-3', '--version'] : ['--version'];
    const result = spawnSync(command, args, { stdio: 'ignore', windowsHide: true });
    if (!result.error && result.status === 0) return command;
  }
  lib.die('Python 3.10+ is required. Install it, then set PYTHON if it is not on PATH.');
}

function pythonArgs(python, args) { return python === 'py' ? ['-3', ...args] : args; }

async function main() {
  const { flags, positional } = lib.parseArgs(process.argv.slice(2), ['output']);
  const url = positional[0];
  if (!url || flags.help) return console.log(USAGE);
  if (!/^https?:\/\//i.test(url)) lib.die('Provide a complete http:// or https:// video URL.');

  const outputDir = path.resolve(flags.output || downloadsDirectory());
  fs.mkdirSync(outputDir, { recursive: true });
  const python = findPython();
  const args = pythonArgs(python, [
    '-m', 'yt_dlp', '--no-playlist', '--merge-output-format', 'mp4',
    '-o', path.join(outputDir, '%(title).180B-%(id)s.%(ext)s'), url,
  ]);

  console.log(`Downloading to ${outputDir}`);
  const child = spawn(python, args, { stdio: 'inherit', windowsHide: true });
  child.on('error', (error) => lib.die(`Could not start yt-dlp: ${error.message}`));
  child.on('close', (code) => {
    if (code === 0) console.log(`\nDone. Download saved in ${outputDir}`);
    else lib.die(`yt-dlp exited with code ${code}. Install/update it with: python -m pip install -U yt-dlp`);
  });
}

function downloadsDirectory() {
  if (process.platform === 'win32') {
    // Respect Windows' redirected Downloads known folder (e.g. another drive).
    const query = spawnSync('reg.exe', ['query', 'HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\User Shell Folders', '/v', '{374DE290-123F-4565-9164-39C4925E467B}'], { encoding: 'utf8', windowsHide: true });
    const match = /REG_(?:EXPAND_)?SZ\s+(.+)/.exec(query.stdout || '');
    if (match) return match[1].trim().replace(/%([^%]+)%/g, (_, name) => process.env[name] || process.env[name.toUpperCase()] || `%${name}%`);
  }
  return path.join(require('os').homedir(), 'Downloads');
}

if (require.main === module) main().catch((error) => lib.die(error.message));
module.exports = { downloadsDirectory };
