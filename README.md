# Video Editing Toolkit

This repository provides three editing workflows that share FFmpeg:

| Workflow | Use it for | Entry point | Outputs |
| --- | --- | --- | --- |
| **Automatic editor** | A file/URL plus a preset; no editing agent | `npm run edit -- ...` | `<source-folder>/edit/` |
| **Local highlights** | Free, local transcript-led highlight cuts | `npm run transcribe`, `npm run cut` | `output/<video-name>/` |
| **Video Use editor** | Conversation-led edits, Scribe timestamps, grades, captions, and overlays | Start Codex in the footage directory | `<footage-dir>/edit/` |

Choose one workflow per edit. The local highlights workflow uses whisper.cpp and
never uploads media. Video Use uses ElevenLabs Scribe for word-level
transcription and therefore needs an API key.

## Requirements and First-Time Setup

Run every command in this README from the repository root. Quote paths and URLs
that contain spaces.

| Requirement | Used by | Install or check |
| --- | --- | --- |
| Node.js 18+ | Local and automatic commands | `node --version` |
| FFmpeg and FFprobe | Every workflow | Windows: `winget install --id Gyan.FFmpeg -e` |
| Python 3.10+ | Automatic editor and Video Use helpers | `python --version` |
| ElevenLabs API key | Automatic editor and Video Use transcription | Store only in `video-use/.env` |
| yt-dlp | Downloading or editing supported video URLs | `python -m pip install yt-dlp` |

Set up the free, fully local Whisper workflow once:

```powershell
npm run setup                       # downloads whisper.cpp and the small model
npm run setup -- --model medium      # optional: more accurate, larger model
```

On Windows, scripts find FFmpeg through `PATH` or `FFMPEG_DIR`. On macOS, run
`brew install ffmpeg whisper-cpp`. Set `WHISPER_CLI` if whisper.cpp is installed
outside the standard locations.

## Download a Video URL

Download one supported video URL without starting an edit:

```powershell
npm run download -- "https://www.youtube.com/watch?v=example"
npm run download -- "https://www.youtube.com/watch?v=example" --output "D:\Videos\Downloads"
```

The default destination is `downloads/` in this repository. Downloads are
merged to MP4 when possible. Only download media you are authorized to save and
use. Use the automatic editor below to download and edit the same URL in one
command.

## Automatic Editor (No Coding Agent Required)

Use the `edit` command when you want an edit from a file or video URL plus a
clear preset—without starting Codex or Claude. It uses deterministic transcript
rules rather than an LLM: `highlights` ranks concise, high-signal spoken
phrases, while `silence-cut` keeps every spoken phrase and removes pauses.

```powershell
# One-time support for YouTube and other supported URLs
python -m pip install yt-dlp

# Highlight reel from a URL or local path
npm run edit -- "https://www.youtube.com/watch?v=example" --edit highlights --target 60
npm run edit -- "D:\Videos\interview.mp4" --edit highlights --target 2m --subtitles --grade auto

# Remove dead air, or deliver a vertical subtitled social version
npm run edit -- "D:\Videos\talk.mp4" --edit silence-cut --grade none
npm run edit -- "D:\Videos\talk.mp4" --edit highlights --target 45 --vertical --subtitles
```

Outputs go to `<source-folder>/edit/`: `edl.auto.json`, cached word-timed
transcript data, per-clip grades, captions, and the rendered MP4. Scribe uploads
audio to ElevenLabs and consumes transcription credits; it is not used by the
fully local highlights pipeline.

### Automatic editor options

| Option | Purpose |
| --- | --- |
| `--edit highlights` | Select a target-length reel from scored speech phrases. |
| `--edit silence-cut` | Keep all speech phrases while removing pauses. |
| `--target 60`, `--target 1m30s` | Desired highlight length. |
| `--subtitles` | Build and burn word-timed captions after overlays. |
| `--grade auto`, `neutral_punch`, `warm_cinematic`, `none` | Apply a per-segment grade. |
| `--vertical` | Centre-crop and render a 1080×1920 version. |
| `--overlay "C:\overlay.webm@4.5"` | Composite a pre-rendered overlay at an output time; repeat for more overlays. |
| `--preview` | Render a faster preview before a final run. |

The automatic selector cannot understand story, humor, or brand context as well
as a human editor. For editorial direction, multiple takes, custom animation,
or iterative feedback, use the Video Use workflow below; its helper commands
are also available directly without an agent.

## Video Use: Conversation-Led Editing

`video-use/` is installed alongside this project and registered with Codex as
the `video-use` skill. It keeps source clips untouched and writes every project
artifact to an `edit/` folder next to the footage.

### Start an edit

1. Put footage in a dedicated folder, for example `D:\Videos\Launch\`.
2. Open a new terminal there and start Codex.
3. Ask for an inventory or an edit, such as: `inventory these takes and propose a strategy` or `edit these into a launch video`.
4. Review the proposed plan and explicitly approve it. Video Use will not alter
   the cut before confirmation.

It can transcribe with speaker/timestamp detail, select takes, render a preview
or final, create subtitles, apply per-clip grades, and add requested overlays.
It caches transcripts, so follow-up changes re-render rather than re-upload.

### Direct helper commands

Use these for focused advanced work without an agent. `transcribe*.py` spends
ElevenLabs credits; it caches each source transcript and writes to the source
folder's `edit/` directory by default.

| Feature | Command |
| --- | --- |
| One video: word timings, diarization, audio events | `python video-use/helpers/transcribe.py "video.mp4"` |
| Set output, language, speakers, or OBS audio track | Add `--edit-dir "edit" --language en --num-speakers 2 --audio-track 1` |
| Transcribe a directory in parallel | `python video-use/helpers/transcribe_batch.py "D:\Videos\Takes" --workers 4` |
| Pack transcript JSON into timestamped phrases | `python video-use/helpers/pack_transcripts.py --edit-dir "D:\Videos\Takes\edit"` |
| Change phrase breaks or output file | Add `--silence-threshold 0.7 -o "packed.md"` |
| Inspect a range as frames plus waveform | `python video-use/helpers/timeline_view.py "video.mp4" 12 18` |
| Change timeline output / samples | Add `-o "timeline.png" --n-frames 16` |
| Analyse a clip's automatic grade | `python video-use/helpers/grade.py --analyze "video.mp4"` |
| List available grades | `python video-use/helpers/grade.py --list-presets` |
| Apply auto grade | `python video-use/helpers/grade.py "in.mp4" -o "out.mp4"` |
| Apply a named grade | Add `--preset subtle`, `neutral_punch`, `warm_cinematic`, or `none` |
| Apply a custom FFmpeg grade | Add `--filter "eq=contrast=1.1:saturation=1.05"` |
| Render an EDL | `python video-use/helpers/render.py "edit/edl.json" -o "edit/final.mp4"` |
| Fast render | Add `--preview` (1080p) or `--draft` (720p) |
| Build and burn output-timeline captions | Add `--build-subtitles` |
| Skip captions or loudness normalization | Add `--no-subtitles` or `--no-loudnorm` |
| Force frame rate | Add `--fps 30` or `--fps 30000/1001` |

The advanced renderer applies per-segment grades, 30 ms audio fades at cut
boundaries, lossless clip concatenation, overlays before captions, captions last
in the filter chain, HDR-to-SDR tone mapping when necessary, and default audio
normalization to -14 LUFS / -1 dBTP. Do not store the API key in tracked files;
it belongs only in Git-ignored `video-use/.env`.

### EDL format

`render.py` takes an Edit Decision List (EDL). It supports multiple source
videos, exact time ranges, grade presets/raw filters, timed MP4/WebM overlays,
captions from cached transcripts, and vertical output.

```json
{
  "version": 1,
  "sources": { "take_01": "D:/Videos/take_01.mp4" },
  "ranges": [
    { "source": "take_01", "start": 2.42, "end": 6.85,
      "beat": "HOOK", "reason": "Clean opening" }
  ],
  "grade": "auto",
  "overlays": [
    { "file": "edit/animations/slot_1/render.webm", "start_in_output": 0.0, "duration": 5.0 }
  ],
  "aspect": "vertical"
}
```

Render it with:

```powershell
python video-use/helpers/render.py "edit/edl.json" -o "edit/final.mp4" --build-subtitles
```

## Local Highlights Pipeline

Drop in a long video and get back a short highlights video. Everything runs
locally and free: FFmpeg does the audio and video work, and whisper.cpp does the
speech-to-text. There are no uploads, no API keys and no file-size limits.
Portuguese and English (and ~95 other languages) are detected automatically.

### Setup

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

### Usage

### 1. Transcribe

```bash
node transcribe.js "D:\Videos\Live 2026-09-12.mp4"
node transcribe.js episode.mkv --model medium       # more accurate, ~3× slower
node transcribe.js episode.mkv --language pt        # skip auto-detect
node transcribe.js episode.mkv --threads 8          # limit CPU worker threads
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
node silence.js episode.mp4 --pad 0.25             # preserve speech-edge breathing room
node cut.js episode.mp4 output/episode/no-silence.json --no-fade   # the video minus dead air
```

## Optional Agent-Directed Editing

Use this path when the edit needs story judgment, multiple takes, a custom
animation, or iterative feedback. Video Use is registered with Codex; start an
agent from the folder that contains the footage:

```powershell
cd "D:\Videos\Launch"
codex
```

Then use a natural-language prompt. For example:

```text
Inventory these takes and propose a 60-second vertical launch video with captions.

Edit these clips into a two-minute tutorial: keep the clearest take of every step,
use a clean neutral grade, and show captions.

Make a fast 45-second highlight reel from this interview. Preserve the strongest
hook and conclusion, flag any potentially sensitive quote, and suggest a title.
```

The agent inspects the footage, transcribes it with word-level timing, reviews
the packed transcript and relevant timelines, then proposes an editing strategy.
Review and approve that strategy before it renders. It can select takes, create
an EDL, apply per-segment grades, create or composite overlays, burn captions,
normalize audio, render previews/finals, and verify cut boundaries.

Give revision requests after a preview without re-transcribing, for example:

```text
Drop segment 3, move the conclusion earlier, keep it under 50 seconds, and re-render vertical.
```

All agent-session artifacts and final files stay in `<footage-folder>/edit/`.
For deterministic, no-agent edits, use the **Automatic Editor** commands above.

## Project Files and Output Locations

```
setup.js        dependency check + downloads
download.js     URL downloader (yt-dlp)
transcribe.js   FFmpeg audio extraction + whisper.cpp
cut.js          segment cutting / joining
silence.js      silence detection
lib.js          shared helpers (tool discovery, progress bar, time formats)
bin/            whisper.cpp binary (downloaded)
models/         whisper models (downloaded)
output/<name>/  everything generated for a video
video-use/       advanced helpers and the ignored .env key file
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
- **Automatic highlights are unsuitable for music-only footage**: use
  `npm run silence` and a hand-authored `segments.json`, or make a manual cut.
- **URL download fails**: update yt-dlp with `python -m pip install -U yt-dlp`;
  website access rules may still prevent downloads.
- **Keep credentials safe**: `video-use/.env` is Git-ignored. Never commit,
  publish, or paste the ElevenLabs key into an untrusted service.
