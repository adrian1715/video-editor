#!/usr/bin/env node
// Shared cross-platform launcher; existing commands remain compatible.
const { spawnSync } = require('child_process');
const path = require('path');
const lib = require('./lib');
const candidates = [process.env.PYTHON, 'python3', 'python', 'py',
  process.env.LOCALAPPDATA && path.join(process.env.LOCALAPPDATA, 'Programs/Python/Python312/python.exe')].filter(Boolean);
const python = candidates.find((p) => spawnSync(p, ['--version'], { windowsHide: true }).status === 0);
if (!python) lib.die('Python 3.10+ required. Set PYTHON to its executable.');
for (const tool of ['ffmpeg', 'ffprobe']) {
  const found = lib.findFfTool(tool);
  if (found) process.env[tool.toUpperCase()] = found;
}
const entry = process.argv[2] === '--mode-cli' ? 'creator/modes.py' : 'creator/cli.py';
const args = process.argv.slice(entry.endsWith('modes.py') ? 3 : 2);
const result = spawnSync(python, [path.join(__dirname, entry), ...args], {
  stdio: 'inherit', windowsHide: true, env: { ...process.env, PYTHONUTF8: '1' },
});
process.exit(result.status ?? 1);
