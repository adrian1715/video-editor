# Video highlights pipeline

Drop in a long video and get back a short highlights video. Everything runs
locally and free: FFmpeg does the audio and video work, and whisper.cpp does the
speech-to-text. There are no uploads, no API keys and no file-size limits.
Portuguese and English (and ~95 other languages) are detected automatically.

## Setup

Requirements: Node.js 18+ and FFmpeg.

```bash
# Windows (FFmpeg)
winget install --id Gyan.FFmpeg -e
# macOS
brew install ffmpeg whisper-cpp

node setup.js                 # checks everything, downloads whisper.cpp + the "small" model (~470 MB)
node setup.js --model medium  # optional: the more accurate "medium" model (~1.5 GB)
```

There's nothing to `npm install`; the scripts only use Node's built-in modules.

### Why the whisper.cpp binary instead of `nodejs-whisper`?

`nodejs-whisper` compiles whisper.cpp from source when it installs, and on Windows
that needs Visual Studio Build Tools (several GB), CMake and `make`. `setup.js`
instead downloads the official prebuilt `whisper-cli.exe` from the whisper.cpp
GitHub releases. That's a ~9 MB zip with no compiler needed and nothing that can
break during `npm install`, and the scripts call it directly. On macOS,
`brew install whisper-cpp` provides the same binary. On Linux, build it with CMake
and set `WHISPER_CLI=/path/to/whisper-cli`.

## Usage

### 1. Transcribe

```bash
node transcribe.js "D:\Videos\Live 2026-09-12.mp4"
node transcribe.js episode.mkv --model medium       # more accurate, ~3× slower
node transcribe.js episode.mkv --language pt        # skip auto-detect
```

This writes to `output/<videoname>/`:

```
transcript.txt   [00:02:14.00 - 00:02:41.50] So here's the thing nobody tells you...
transcript.srt   subtitles (also handy for YouTube)
meta.json        duration, detected language, model
```

Expect about 3× real time with `small` on a modern laptop CPU, so a 1-hour video
takes roughly 20 minutes. A progress bar with an ETA is shown.

### 2. Cut

Write a `segments.json` (or let Claude write it; see below):

```json
[
  { "start": "00:02:14.00", "end": "00:02:41.50", "reason": "Strong hook" },
  { "start": "00:17:03.20", "end": "00:17:48.00", "reason": "Funniest moment" }
]
```

```bash
node cut.js episode.mp4 segments.json              # -> output/episode/highlights.mp4
node cut.js episode.mp4                            # uses output/episode/segments.json
node cut.js episode.mp4 --vertical                 # 9:16 1080x1920 -> highlights-vertical.mp4
node cut.js episode.mp4 --separate                 # one file per segment -> clips/01-strong-hook.mp4 ...
node cut.js episode.mp4 --vertical --separate      # vertical clips for Shorts/Reels/TikTok
node cut.js episode.mp4 --no-fade                  # hard cuts
node cut.js episode.mp4 --fade 0.5                 # longer fade (default 0.3s)
node cut.js episode.mp4 --cpu                      # force software x264
```

- **Frame-accurate:** every segment is re-encoded, so cuts land on the exact
  frame rather than the nearest keyframe.
- **Hardware encoding:** it tries NVIDIA NVENC, Intel Quick Sync, AMD AMF and
  Apple VideoToolbox, uses the first one that works, and otherwise falls back to
  libx264.
- **Fades:** each segment fades in and out through black with a matching audio
  fade, so the joins aren't jarring.
- It prints each segment and the percentage of the original kept.

### 3. Trim dead air (optional)

```bash
node silence.js episode.mp4                        # lists silences >= 1s below -30 dB
node silence.js episode.mp4 --noise -35 --min 0.7  # quieter threshold, shorter gaps
node cut.js episode.mp4 output/episode/no-silence.json --no-fade   # the video minus dead air
```

## With Claude Code

Open this folder in Claude Code and say:

> make highlights of D:\Videos\episode.mp4

Claude follows `CLAUDE.md`:
1. Transcribes the video.
2. Picks the ~20% with ~80% of the impact.
3. Writes `segments.json`.
4. Cuts the video.
5. Shows you the segments and the percentage kept, plus a title, caption and
   hashtags.

Then just say what to change ("drop #3", "make it vertical", "under 60 seconds")
and it re-cuts.

## Files

```
setup.js        dependency check + downloads
transcribe.js   FFmpeg audio extraction + whisper.cpp
cut.js          segment cutting / joining
silence.js      silence detection
lib.js          shared helpers (tool discovery, progress bar, time formats)
bin/            whisper.cpp binary (downloaded)
models/         whisper models (downloaded)
output/<name>/  everything generated for a video
```

## Troubleshooting

- **"FFmpeg not found"**: open a new terminal after installing (so PATH updates),
  or set `FFMPEG_DIR` to the folder containing `ffmpeg.exe`.
- **Transcript is poor or in the wrong language**: try `--model medium` and/or
  `--language pt`.
- **Hardware encoder errors**: they're retried automatically with libx264, or you
  can use `--cpu`.
- **Vertical crop cuts off the speaker**: `--vertical` crops from the centre. If
  you're off to one side of the frame, you'll need to reframe manually.
