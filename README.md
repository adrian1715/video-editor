# Creator Video Editor

A local-first personal video toolkit using FFmpeg, Node.js and Python. Choose
automatic first-pass highlights, manual cuts, or persistent projects that an
editing agent can revise. Cloud transcription and semantic planning are optional.

**Status:** an experimental creator pipeline with tested rendering fundamentals.
It is not yet production-ready against the full mission requirements. See
[implementation status](docs/status.md) for the gaps and validation evidence.

## Contents

- [Creator Video Editor](#creator-video-editor)
  - [Contents](#contents)
  - [Features and architecture](#features-and-architecture)
  - [Installation](#installation)
  - [Configuration and privacy](#configuration-and-privacy)
  - [Quick start](#quick-start)
  - [Primary command reference](#primary-command-reference)
  - [Advanced creator commands](#advanced-creator-command-reference)
  - [Captions, audio and layouts](#captions-audio-and-layouts)
  - [Platforms and content profiles](#platforms-and-content-profiles)
  - [Existing commands](#existing-commands)
  - [Agent-assisted editing](#agent-assisted-editing)
  - [QA and testing](#qa-and-testing)
  - [Troubleshooting and development](#troubleshooting-and-development)

## Features and architecture

`editor.js` discovers Python/FFmpeg and starts `creator/cli.py`. This new adapter
stores source metadata, editable ranges, word transcripts, profile defaults,
audio settings, export dimensions, history, feedback, manifests and QA in a
project directory. Rendering uses FFmpeg directly; the Scribe adapter reuses
vendored helpers. The original `auto-edit.js`, `cut.js`, `silence.js`,
`transcribe.js` and `download.js` remain compatible.

Features implemented: multi-source cuts, missing-audio handling, fit/padded or
centre-cropped composition, landscape/portrait/square dimensions, frame-rate
normalization, captions, music/SFX beds with gain/delay and speech ducking,
optional loudness normalization, multi-platform exports, JSON revisions,
rollback, feedback logs, optional chat-completions planning, local word ASR,
and opt-in Scribe. Legacy helpers also provide grading, timed overlays and
filmstrip inspection. These advanced features are not yet unified in the new
project renderer. See [architecture](docs/architecture.md).

## Installation

Required: Node.js 18+, Python 3.10+, FFmpeg/FFprobe with libx264, AAC and libass.
The new core needs only the Python standard library. Node scripts have no npm
dependencies or build step.

Windows PowerShell:

```powershell
winget install --id OpenJS.NodeJS.LTS -e
winget install --id Python.Python.3.12 -e
winget install --id Gyan.FFmpeg -e
# Open a fresh terminal, then from this repository:
node --version
python --version
ffmpeg -version
ffprobe -version
npm run creator -- doctor
```

macOS: install Python/Node/FFmpeg with your preferred package manager, for
example `brew install node python ffmpeg whisper-cpp`.
Debian/Ubuntu Linux: `sudo apt install nodejs npm python3 python3-venv ffmpeg`.
Check Node is at least version 18; distribution defaults vary.

Optional packages (a virtual environment is recommended):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-local.txt  # tested local ASR/audio versions
python -m pip install -e ./video-use   # Scribe, waveform/image helper dependencies
python -m pip install yt-dlp          # URL download support
```

On macOS/Linux activate using `source .venv/bin/activate` and use `python3`
where needed. Set `PYTHON` to the interpreter executable if discovery fails.

## Configuration and privacy

The new CLI reads environment variables, not a root `.env` automatically:

```powershell
$env:PYTHON = 'C:\path\to\python.exe'
$env:FFMPEG_DIR = 'C:\path\to\ffmpeg\bin'
$env:WHISPER_MODEL = 'small'
# Optional cloud Scribe:
$env:ELEVENLABS_API_KEY = '<your-key>'
# Optional local or cloud chat-completions service:
$env:LLM_URL = 'http://localhost:1234/v1/chat/completions'
$env:LLM_MODEL = 'your-model'
$env:LLM_API_KEY = '<optional-provider-key>'
```

`FFMPEG`/`FFPROBE` can override executable names in Python. `WHISPER_CLI`
configures the legacy local transcriber. Scribe also supports the Git-ignored
`video-use/.env` containing `ELEVENLABS_API_KEY=...`.

Local ASR does not upload footage. Scribe requires `--allow-upload`; it uploads
audio and incurs provider charges. `plan --semantic` uploads only the brief,
target, constraints, source IDs and word transcripts to `LLM_URL`; use a local service
for privacy. No budget enforcement or token estimation is implemented. Model
responses are treated as JSON data and never executed as shell commands.
Keep project folders under ignored `output/`, or outside the repository.
Transcripts and feedback persist until you delete their project folder.

## Quick start

For local automatic editing, install the transcription dependency once:

```powershell
npm run setup:local
npm run creator -- doctor
npm run highlights -- "D:\Videos\recording.mp4"
```

`setup:local` installs the pinned local ASR requirements into the same Python interpreter the editor
uses. Whisper downloads its model on first transcription; this requires network
access and disk space. Later runs reuse it. Set `$env:WHISPER_MODEL='tiny'` for a
smaller, faster model with lower expected accuracy, or leave `small` as default.
`npm run highlights`, `npm run youtube` and `npm run shorts` are aliases for
`npm run edit -- highlights`, `youtube` and `shorts` respectively.

### Transcription speed and console output

The creator pipeline prints `Transcribing...` and `Transcription concluded.`
once per uncached source. Unchanged footage reuses its saved transcript. The
model is loaded once for all uncached sources in one command.

Local speech recognition can take substantial time on long recordings,
particularly on CPU; first use also downloads/loads model weights. The default
`fast` preset uses the same `small` model with greedy decoding (beam size 1),
silence filtering (VAD), CPU int8 and up to eight CPU threads. It automatically
selects CUDA when the installed backend detects a compatible NVIDIA device;
Intel integrated graphics are not CUDA acceleration. GPU runtime libraries are
optional and are not installed automatically.

PowerShell overrides:

```powershell
$env:WHISPER_PRESET = 'fast'     # default; lower decoding cost, possible accuracy tradeoff
$env:WHISPER_THREADS = '8'       # CPU tuning; more threads are not always faster
$env:WHISPER_DEVICE = 'cpu'      # auto (default), cpu, or cuda
$env:WHISPER_VAD = '1'          # skip non-speech; original timestamps are restored
# For a wider decoding search, or quiet speech missed by VAD:
$env:WHISPER_PRESET = 'accurate' # beam size 5; slower
$env:WHISPER_VAD = '0'
# Optional smaller model: faster, usually less accurate, downloads once
$env:WHISPER_MODEL = 'base'     # small remains default
```

Changing these variables affects new transcription, not existing cached words.
Use a new output project to compare settings without deleting the original edit.
VAD can miss quiet or unusual speech; turn it off if needed. Timing measurements
and effective local ASR settings are recorded on each source in project JSON.
The manual `tests/benchmark_asr.py --audio FILE` compares previous/fast settings
locally and excludes warm-up; results on short synthetic speech are not an
estimate of long-video throughput or recognition quality.

Choose a **mode** (editorial job), a **profile** (content defaults), and export
**platforms** (delivery formats). They are independent concepts. All modes share
the persistent creator engine. No coding agent or paid AI is required; local
transcription requires the optional faster-whisper package described above.

```powershell
# Highlights: a selective compilation, with complete ideas and explanations
npm run edit -- highlights "D:\Videos\recording.mp4" --target 2m --preview
# Review the preview, then rerun identical editorial options with --approve:
npm run edit -- highlights "D:\Videos\recording.mp4" --target 2m --approve
# Separate highlight clips rather than a compilation:
npm run edit -- highlights "D:\Videos\recording.mp4" --target 2m --separate

# YouTube: chronological long-form first pass, repeated explanations removed
npm run edit -- youtube "D:\Videos\devlog.mp4" --profile build-in-public --captions

# Shorts: independently planned adjacent ideas, vertical exports and captions
npm run edit -- shorts "D:\Videos\recording.mp4" --count 3 --target 60

# All three edits in one organized project beside the original video:
npm run project -- "D:\Videos\recording.mp4" --count 3
# Equivalent option on any primary mode; --output overrides the project root:
npm run highlights -- "D:\Videos\recording.mp4" --project --output "E:\Edits\Full Project"
```

Default behavior renders full-resolution edited files beside the source:
`recording-highlights.mp4`, `recording-youtube.mp4`, or
`recording-shorts-01.mp4`, `recording-shorts-02.mp4`, etc. Repeated runs add a
numeric suffix and never overwrite footage or previous edits. For multiple
inputs, outputs default to the first input's directory. Use `--preview` for a
lower-resolution draft; then `--approve` explicitly exports that reviewed edit.
Neither step needs a coding agent. A plain command without either flag creates
a final first-pass edit immediately, without an approval prerequisite.
On completion the terminal prints **Final video ready** (or **Preview ready**),
the exact playable MP4 path, and, for previews, a copy-paste final-export command. A cached-transcript
message means existing words were reused successfully. Add `--json` for agent
automation; the result includes both output directories and exact `video_files`.
Local instructions are saved as a creative brief, not interpreted as commands.
For semantic interpretation add `--ai --instructions "..."` with LLM_URL configured,
or ask an agent to revise the saved mode project. Real narrative quality needs
review; sentence completeness is only a mechanical proxy.

### Primary command reference

`npm run edit -- MODE "FILE" ["SECOND FILE"] [OPTIONS]`

| Option | Meaning |
| --- | --- |
| `MODE` | `highlights`, `youtube`, `shorts`, or `project` (all three) |
| `--profile NAME` | Any content profile below; default `build-in-public` |
| `--target 60` / `--target 1m30s` | Approximate editorial duration; complete/required ideas may exceed it |
| `--count 3` | Maximum Shorts count, 1–100; fewer if insufficient distinct material |
| `--ai` | Opt into configured LLM; currently AI Shorts requires `--count 1` |
| `--output PATH` | Single mode: destination directory for MP4s; project: root folder |
| `--project` | Generate YouTube, Highlights and Shorts in a full organized project beside the first source |
| `--cache-dir PATH` | Single mode: override the user cache location holding transcripts, history and logs |
| `--preview` | Render a draft instead of the default final; cannot combine with `--approve` |
| `--approve` | Final render of the already-previewed revision |
| `--instructions TEXT` | Creative brief for AI/agents; recorded but not interpreted by local rules |
| `--platforms youtube,shorts` | Export profiles; default `youtube` for Highlights/YouTube, `shorts` for Shorts |
| `--transcript FILE` | Import corrected source-keyed word JSON instead of running ASR |
| `--provider local` / `scribe` | Word ASR provider; Scribe also requires `--allow-upload` |
| `--allow-upload` | Explicit Scribe consent; cloud charges may apply |
| `--captions` | Burn captions; enabled by default for Shorts |
| `--separate` | Highlights only: one clip per selected idea |
| `--constraints FILE` | JSON include/exclude timestamps; see agent workflow |
| `--help` | Complete command usage and supported flags |
| `--json` | Structured output for agents; normal runs show readable completion and video paths |

Highlights uses Pareto as an editorial heuristic: selective value and context,
not an obligation to keep exactly 20%. YouTube preserves chronology and removes
near-duplicate sentences and inter-sentence gaps; it does not automatically remove
repeated individual words or invent a narrative. Shorts groups adjacent complete
sentences rather than mixing unrelated moments. Hooks/payoffs remain experimental
creative judgments. With `--profile music`, YouTube preserves the original full
performance and skips speech ASR; manual edits are needed for musical cuts.

**Highlights preserves the original treatment by default.** It only selects and
joins moments: no loudness normalization, gain/compression/ducking, music mix,
grading, fades, or captions. Source resolution, aspect ratio, nominal frame rate,
audio sample rate and channel count are retained for a single source. Explicit
`--platforms` requests conversion; `--captions` explicitly enables captions.
Previews can be smaller for review. Audio is held as PCM between segments and
encoded once to AAC at final export. Video is still re-encoded for accurate cuts,
as in the original cutter; this is not a bit-for-bit lossless copy. Multiple
sources use the first selected source's format to make concatenation consistent.
The old commit's brief fades are intentionally omitted to honor cut-only edits.
Cached Highlights settings from older versions are updated automatically without
retranscribing or deleting existing outputs. Rerun your usual Highlights command
to generate the corrected file; previous exports are left intact.

### Output locations and retries

Single edits create only MP4 files in the source directory (or `--output`).
Transcripts, editable mode projects, QA, history and failure diagnostics live in
`%LOCALAPPDATA%\VideoEditor\Cache` on Windows, or `$XDG_CACHE_HOME/video-editor`
(normally `~/.cache/video-editor`) elsewhere. `--cache-dir` overrides this.
The command prints delivered paths and the processing-state location. Caches
persist for retries; delete them manually when no longer needed.

Only `--project` / the `project` mode creates the following full project beside
the first source, by default `<source-name>-edited-project/`:

```text
<source-directory>/<source-name>-edited-project/
  data/          source project, cached transcripts, plans, history
    edits/       persistent per-mode/per-clip projects for agent revisions
  highlights/    unique preview/final compilation or clip folders
  youtube/       unique long-form output folders
  shorts/        unique vertical output folders
  assets/        reserved for creator-provided assets (no sourcing/generation)
  temporary/     intermediate render jobs, retained on failure
  reports/       run logs, results, preview approval records
```

In project mode each delivered folder contains `preview.mp4` or `final.mp4`, `captions.srt`,
`qa.json`, and `manifest.json`. JSON results report exact paths and `mode_projects`.
Original footage is never overwritten. Single edits don't create project folders.
Retry the same command after fixing an error: unchanged transcripts and plans are
reused. Changing source size/mtime invalidates ASR cache. Logs and project state
remain on failure. Keep options identical between preview and approval. Existing
repository output/projects data is copied into the new workspace on first reuse
when available, avoiding repeat transcription; previous outputs are not deleted.

### Agent-assisted mode and advanced revisions

From the repository root launch `codex` or `claude`, then request, for example:

```text
Read README and docs/agent-workflow.md. Run the Shorts mode on my recording with
three candidates. Inspect each returned mode_project and contact sheet. Propose
a better hook and payoff using complete transcript ideas. Validate changes,
preview them and show me QA before final approval.
```

An agent uses the returned `data/edits/...` path with `node editor.js inspect`,
`plan`, `validate-plan`, `apply-plan`, `revise`, `frames` and `feedback`.
For example `node editor.js revise --project "<mode_project>" --patch patch.json`
can change captions or manually adjust ranges. Re-running the primary mode with
the same options reloads that project, preserving revisions, then generates a
new preview. Different editorial options create a new project variant. Approval
is bound to the exact edit/settings/platforms. Both standalone and agents use
the same FFmpeg renderer and QA reports.

Licensed music supplied by you can be added through project audio patches. Legacy
helpers still support grades and overlays. Automatic music sourcing, generated
B-roll, smart face tracking, dynamic layouts, zooms/transitions/visual effects are
not integrated into these modes. `fit` preserves screen content using padding;
it is not intelligent subject tracking. See [status](docs/status.md).

## Advanced creator command reference


All use `npm run creator -- COMMAND`. The advanced `--project PATH` names one
persistent workspace (different from the primary mode's boolean --project flag).
If omitted, it defaults to `advanced-project` in the user cache.

| Command             | Flags and behavior                                                                            |
| ------------------- | --------------------------------------------------------------------------------------------- |
| `doctor`            | Report whether FFmpeg and FFprobe can be found                                                |
| `profiles`          | Print built-in content, caption and platform defaults                                         |
| `init`              | `--sources FILE ... --profile NAME`; refuses an existing project                              |
| `analyze`           | Print stored metadata; `--transcript FILE` imports source-keyed word JSON                     |
| `transcribe`        | `--provider local` (default) or `scribe --allow-upload`; skip unchanged sources               |
| `plan`              | `--target 60 --constraints FILE`; local selection or optional `--semantic --instructions TEXT` |
| `repurpose`         | `--count 3 --target 30`; write reviewed clip candidates; use `--clip INDEX` for preview/approve/export |
| `preview`           | `--platforms youtube,shorts`; lower-resolution review renders                                 |
| `render` / `export` | `--platforms youtube,shorts`; full-size per-platform renders                                  |
| `qa`                | `--file FILE`; decode file and write `qa.json`                                                |
| `revise`            | `--patch FILE`; recursively merge objects, replace arrays, preserve history                  |
| `history`           | List saved project JSON versions                                                              |
| `rollback`          | `--version FILENAME`; restore and version an earlier edit                                     |
| `feedback`          | `--instructions TEXT --decision accepted` (also `rejected`, `note`); record revision-specific feedback |
| `inspect`           | Return project, metadata, words, timeline, settings and revision hash as JSON |
| `frames`            | `--source s0`; generate an eight-frame contact sheet |
| `validate-plan`     | `--plan-file FILE`; validate boundaries, constraints, overlap and base revision |
| `apply-plan`        | `--plan-file FILE`; validate and apply only ranges with history |
| `approve`           | Approve current revision (or `--clip INDEX`) before final export |

`--help` lists all flags. Project files are JSON. Source keys (`s0`, `s1`, ...)
map to absolute files plus FFprobe metadata. Ranges contain numeric seconds:
`{"source":"s0","start":1.2,"end":12.3}`. A transcript import looks like
`{"s0":{"words":[{"start":1.2,"end":1.6,"text":"Olá","type":"word"}]}}`.
Correct imported words before rendering. Transcript hashes are not cryptographic:
the cache uses file size and modification time.

Semantic plan and revision:

```powershell
npm run creator -- plan --project output/talk --semantic --instructions "Choose a complete hook and lesson in Brazilian Portuguese. Keep essential context."
# Inspect the returned plan_file before applying:
npm run creator -- apply-plan --project output/talk --plan-file "output/talk/plans/<id>.json"
npm run creator -- feedback --project output/talk --instructions "Accepted slower pacing; prefer cinematic captions."
npm run creator -- history --project output/talk
```

Semantic support is experimental: sentence/word boundaries, overlap, revision and
include/exclude constraints are checked. Narrative quality is subjective and
language/provider quality still needs real-footage review. Candidate generation
is local, with a complete preview/approve/export path. Feedback is an inspectable JSON log;
automatic preference retrieval and learning are not yet implemented.

## Captions, audio and layouts

Create a patch JSON and apply with `revise --patch`. Objects merge recursively;
arrays replace entire arrays. For example `{"settings":{"caption":"shorts"}}`
preserves layout, audio and loudness settings. Unknown settings are rejected.

```json
{
  "settings": {
    "layout": "fit",
    "caption": "tech",
    "captions": true,
    "fps": 30,
    "lufs": -14
  },
  "audio": [
    { "file": "D:/Music/authorized-bed.wav", "gain": 0.12, "start": 0 },
    { "file": "D:/Sounds/click.wav", "gain": 0.4, "start": 5 }
  ]
}
```

Caption presets: `tech` (3 words), `cinematic` (8 words), `shorts` (2 words).
The renderer exports SRT and optionally burns subtitles after scaling. Defaults
use outlined libass text with safe-zone margins. Font/colour/keyword animation
configuration and ASS export are not yet exposed. Set `captions:false` for a
clean export. Use transcript corrections for vocabulary changes.

All extra audio sources are delayed by `start` seconds, gain-adjusted and mixed
into a bed ducked by narration. This also ducks SFX; separate bus routing,
crossfades, fades, sync offsets and two-pass loudness are pending. `lufs:null`
preserves normalization-free output for music; AAC encoding still occurs.

`layout:fit` pads to preserve screens, code, faces and portrait orientation.
`layout:crop` uses a static centre crop. Face/subject/speaker tracking, manual
crop boxes, picture-in-picture and split-screen are not implemented in this CLI.
Prefer `fit` for programming tutorials and app demonstrations.

## Platforms and content profiles

Export defaults: YouTube/LinkedIn 1920x1080; Shorts/Instagram/TikTok 1080x1920;
X 1280x720; square 1080x1080. All use H.264/AAC MP4. These are creator defaults,
not assertions about platform maximums or account limits. Change dimensions with:

```json
{
  "exports": {
    "youtube": [3840, 2160],
    "shorts": [1080, 1920],
    "square": [1080, 1080]
  }
}
```

Content profiles set editable caption/layout/loudness defaults:

| Profile                 | Intended content                       | Defaults                             |
| ----------------------- | -------------------------------------- | ------------------------------------ |
| `build-in-public`       | Programming, products, project updates | tech captions, fit, -14 LUFS         |
| `personal-essays`       | Reflections and self-improvement       | cinematic captions, fit, -16 LUFS    |
| `music`                 | Guitar/songwriting/performances        | cinematic captions, fit, no loudnorm |
| `creative-storytelling` | Fiction, horror, writing               | cinematic captions, fit, -16 LUFS    |
| `social-shorts`         | Lessons, humor and quick updates       | shorts captions, fit, -14 LUFS       |

Profiles do not invent transitions, music or narrative. Supply assets and edit
ranges deliberately. The brand motto is stored as `Underdogs Win.` in projects.
Per-platform limits, file-size budgets, chapters, thumbnails, cover candidates,
publishing copy and automatic asset generation remain future work.

## Existing commands

These are still supported; their output is separate from persistent projects.

```powershell
npm run setup -- --model medium
npm run download -- "https://example.com/video" --output "D:\Videos\Downloads"
npm run transcribe -- "video.mp4" --model small --language pt --threads 8
npm run silence -- "video.mp4" --noise -35 --min 0.7 --pad 0.25
npm run cut -- "video.mp4" output/video/no-silence.json --no-fade
npm run cut -- "video.mp4" segments.json --vertical --separate --cpu
npm run cut -- "video.mp4" segments.json --fade 0.3
npm run edit -- "video.mp4" --edit highlights --target 60 --vertical --subtitles --grade auto
npm run edit -- "video.mp4" --edit silence-cut --language pt --preview
```

`setup` downloads whisper.cpp/model assets. Local `transcribe` writes TXT, SRT,
metadata under `output/<name>/`. `silence` writes detected gaps plus inverse
segments. `cut` accepts `[{"start":"00:01:00","end":"00:01:10","reason":"hook"}]`,
defaults to `output/<name>/segments.json`, optionally exports separate clips,
and supports fades/hardware encoders with CPU fallback. `download` saves a single
URL with yt-dlp. Only download material you have permission to use.

Legacy `edit` uses Scribe automatically, with English keyword ranking as a
fallback selector. `--target` accepts seconds or `1m30s`; `--overlay FILE@SECONDS`
is repeatable with a fixed five-second window. Existing files may be overwritten;
it is a compatibility path, with weaker cache/output isolation than projects.

Migration: `npm run edit -- "video.mp4" --edit highlights ...` still invokes the
legacy Scribe workflow, with a deprecation message. Its default output is now
the source directory, or explicit `--output PATH`; intermediates are kept in the
user cache. Prefer `npm run edit -- highlights "video.mp4" ...` for cached
projects and approval. Legacy `--vertical`, `--subtitles`, `--grade`, `--language`,
`--overlay`, and `--edit silence-cut` remain available there. New modes use
`--platforms shorts` and `--captions`; grade/overlay integration is still legacy.
Primary mode inputs are local paths; run `npm run download -- URL` first.
Unknown legacy flags now fail with migration guidance instead of being ignored.

Downloads default to your Windows Downloads known folder (including a redirected
folder), or `~/Downloads` elsewhere. `npm run download -- URL --output PATH`
changes that destination. Downloads do not default to this repository.

Advanced helpers:

```powershell
python video-use/helpers/transcribe.py "video.mp4" --edit-dir output/asr --num-speakers 2 --audio-track 1 --language pt
python video-use/helpers/transcribe_batch.py "D:\Videos\Takes" --workers 4
python video-use/helpers/pack_transcripts.py --edit-dir output/asr --silence-threshold 0.7 -o output/packed.md
python video-use/helpers/timeline_view.py "video.mp4" 12 18 --n-frames 16 -o output/timeline.png
python video-use/helpers/grade.py --list-presets
python video-use/helpers/grade.py --analyze "video.mp4"
python video-use/helpers/grade.py "in.mp4" -o output/graded.mp4 --preset neutral_punch
python video-use/helpers/grade.py "in.mp4" -o output/graded.mp4 --filter "eq=contrast=1.1"
python video-use/helpers/render.py "edl.json" -o output/final.mp4 --build-subtitles --fps 30
```

Grade presets include `subtle`, `neutral_punch`, `warm_cinematic`, `none`;
omitting a preset runs auto-analysis. Vendored render options include `--preview`,
`--draft`, `--no-subtitles`, `--no-loudnorm`. Its EDL differs from project JSON:
`sources` maps names directly to file paths, and `ranges` uses those names.
Optional `overlays` contains `{file,start_in_output,duration}`; `grade` accepts
a preset/filter; `aspect:"vertical"` centre crops. Manim, Remotion and HyperFrames
are optional authoring tools described in the vendored skill, not installed
engines or automatic animation features of the core CLI.

## Agent-assisted editing

Start your agent in this repo and ask:

```text
Read README and docs/status.md. Import my footage into output/launch using the
creator CLI. Propose a 60-second vertical story: problem, attempt, result, lesson.
Use fit layout for code. Show me the proposed ranges before applying them.
```

The agent should inspect transcripts and visual evidence, propose decisions,
apply reviewed JSON patches, render previews and disclose unrun QA checks.
Revisions such as “keep the joke at 2:15” are agent instructions, not a natural
language CLI parser. Agents should reuse transcripts and write history entries.
The vendored Video Use skill remains available as an alternative workflow.

Use Codex by running `codex` from the repository root; use Claude Code by running
`claude` there. Both should read [the stable agent CLI contract](docs/agent-workflow.md)
and [the reusable editing skill](skills/creator-editing/SKILL.md). No global skill
installation or engine changes are necessary. Machine callers should use
`node editor.js inspect --project output/talk --json` (without npm's banner).

Preview and export multiple shorts using the same engine:

```powershell
npm run creator -- repurpose --project output/talk --count 3 --target 30
npm run creator -- preview --project output/talk --clip 1 --platforms shorts
npm run creator -- approve --project output/talk --clip 1
npm run creator -- export --project output/talk --clip 1 --platforms shorts,instagram,tiktok
npm run creator -- feedback --project output/talk --decision rejected --instructions "Candidate 2 lacks context"
```

Repeat for other candidate indices returned by repurpose. Apply project changes
before regenerating candidates: stale candidates are rejected. Plan constraints,
JSON schemas, and six content-brief examples are in the agent contract.

## QA and testing

```powershell
npm run creator -- qa --project output/talk --file "output/talk/renders/<job>/final.mp4"
$env:PYTHONUTF8='1'
python -m unittest discover -s tests -v
python -m unittest discover -s video-use/tests -v
python tests/smoke_creator.py
python tests/smoke_modes.py
```

New exports write a manifest and QA JSON with resolution/duration checks and
complete decode verification. `fully_verified` intentionally remains false:
black frames, silence/clipping measurements, caption safe-zone geometry,
overlay timing and creative judgment are not comprehensively tested.
The smoke script generates test patterns and tones under ignored `output/`;
it verifies actual landscape/vertical exports, captions and mixing. It does not
validate real speech recognition, language quality or professional editing taste.
See [production acceptance checklist](docs/acceptance.md) for the real-footage
checks that require credentials or manual review.

## Troubleshooting and development

- Missing Python: activate your environment or set `PYTHON` explicitly.
- Missing FFmpeg: reopen the terminal, set `FFMPEG_DIR`, then run `doctor`.
- ASR package missing: install `faster-whisper`; first model download needs network.
- Caption render fails: ensure FFmpeg includes libass and fonts are installed.
- Semantic plan fails: check endpoint/model/key; no model shell commands are run.
- Invalid EDL: check source keys and finite `start < end` inside source duration.
- Interrupted render: earlier project/history remains; rerun into a new render job.
  Remove abandoned render job directories manually to reclaim space.

Project stages cache transcripts, but exports currently re-encode segments for
each target. This costs CPU and disk; source-aware render caching is pending.
Feedback can be inspected/edited/exported as `preferences.json`; delete that file
to erase it. It is not yet applied automatically to future projects.

Development: use small changes, preserve legacy commands, test media paths with
spaces and Unicode, and never commit generated media or credentials. See
[audit and current status](docs/status.md). Vendored code is MIT, copyright
Browser Use; retain [its license](video-use/LICENSE). Root package declares MIT;
FFmpeg and optional libraries retain their respective distribution licenses.
