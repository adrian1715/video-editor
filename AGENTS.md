# Repository Guidelines

Primary entry: `npm run edit -- highlights|youtube|shorts "FILE"`. All share
creator/modes.py -> creator/cli.py. Use returned mode_projects with the advanced
agent commands. Re-preview the same options after revisions, then --approve.
Default edits are MP4s beside the source; processing state is in the user cache.
--project generates all three modes in a named source-adjacent project folder.
--output overrides either destination. Never overwrite source footage.

## Editing workflow for agents

Follow docs/agent-workflow.md and skills/creator-editing/SKILL.md. Discover with
`node editor.js inspect --project PATH --json`; read transcript words/settings,
generate frames, interpret the creative brief, author a revision-bound JSON plan,
validate-plan, apply-plan, preview, read QA, perform subjective creative review,
revise, obtain creator approval, approve/export, then record accepted/rejected
feedback. Use documented commands rather than modifying engine source for edits.
Keep source footage immutable. New plans must use complete sentence/word boundaries.
Standalone planning uses the same validator/render engine and needs no agent.

## Current Creator Architecture

Read README.md and docs/status.md before editing. The persistent creator CLI is
editor.js -> creator/cli.py; legacy entry points remain compatible. Project JSON
and vendored EDL formats differ. Keep changes in adapters where possible.
Projects belong in output/ or outside the repo; never commit footage or secrets.
`npm test` runs both unit suites; `python tests/smoke_creator.py` generates an
ignored FFmpeg demo. Use PYTHONUTF8=1 on Windows. Claim only executed validations.
Current gaps are recorded in docs/status.md; do not label them implemented.

## Project Structure & Module Organization

This is a local Node.js video-highlights pipeline. Top-level scripts are the
application entry points: `setup.js` checks dependencies and downloads
whisper.cpp assets; `transcribe.js`, `cut.js`, and `silence.js` implement the
three workflow stages. Put shared, reusable helpers in `lib.js` rather than
duplicating tool discovery, timestamp, or FFmpeg logic.

Runtime downloads belong in `bin/` and `models/`; generated results belong in
`output/<video-name>/` (for example, `output/episode/transcript.srt`). Do not
commit generated media, downloaded models, or local video files.

## Build, Test, and Development Commands

The project requires Node.js 18+ and FFmpeg, and intentionally has no npm
dependencies or build step.

```powershell
npm run setup                         # check tools; download default model
npm run setup -- --model medium       # download/use the medium model
npm run transcribe -- "video.mp4"     # create transcript and metadata
npm run silence -- "video.mp4"        # identify silent regions
npm run cut -- "video.mp4" --vertical # create a 9:16 highlights cut
```

Use `node <script>.js ...` interchangeably when debugging. Quote file paths,
especially on Windows. Configure `FFMPEG_DIR` or `WHISPER_CLI` only when the
tools cannot be discovered automatically.

## Coding Style & Naming Conventions

Use CommonJS and Node built-ins (`require`, `module.exports`), matching the
existing code. Follow two-space indentation, semicolons, single-quoted strings,
and concise explanatory comments for non-obvious FFmpeg or platform behavior.
Use `camelCase` for functions and variables, `UPPER_SNAKE_CASE` for constants,
and descriptive filenames such as `transcribe.js`. Keep command-line option
spelling lowercase kebab-style (for example, `--no-fade`).

## Testing Guidelines

Python unittest covers core and vendor behavior. Run `npm test`. Validate changes
with a small disposable video: run the affected command, confirm the expected
files appear under `output/<name>/`, and inspect errors and duration metadata.
For cutting changes, confirm the resulting audio/video plays and segment timing
is correct. Add focused automated tests if introducing parsing or formatting
logic that can be isolated from FFmpeg.

## Commit & Pull Request Guidelines

The history currently uses short, lowercase descriptions (for example,
`adding project`). Continue with concise, imperative summaries such as
`handle missing audio streams`. Keep commits narrowly scoped. Pull requests
should explain the user-visible behavior, list validation commands and results,
link related issues when applicable, and include screenshots or sample output
when CLI output or generated-video behavior changes.
