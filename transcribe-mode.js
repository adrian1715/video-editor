#!/usr/bin/env node
// Keep legacy Whisper flags working while making transcript-only mode primary.
const { spawnSync } = require('child_process');
const path = require('path');
const args = process.argv.slice(2);
const legacy = args.some((arg) => /^--(?:model|language|threads)(?:=|$)/.test(arg));
const entry = legacy ? 'transcribe.js' : 'auto-edit.js';
if (legacy) console.error('Legacy whisper.cpp flags detected. Use npm run transcribe:legacy for the original pipeline.');
const result = spawnSync(process.execPath, [path.join(__dirname, entry), ...(legacy ? [] : ['transcribe']), ...args], { stdio: 'inherit', windowsHide: true });
process.exit(result.status ?? 1);
