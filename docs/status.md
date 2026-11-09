# Implementation and validation status

## Implemented and exercised

- Legacy Whisper TXT/SRT/metadata are grouped in a <video>-transcript/ folder
  beside source footage, or under --output. Repeated runs use numbered folders
  without changing existing files. Intermediate files use unique
  temporary folders; cleaned on success and retained on failure. Destination
  regression tests simulate ASR/FFmpeg; no real whisper.cpp inference rerun for
  this filesystem-only change.

- Transcript-only primary mode and npm alias: complete UTF-8 text beside each
  source, chronological timestamped paragraphs, non-overwriting filenames and shared
  ASR caches. No pause/duration splits: conservative explicit topic transitions
  locally, or optional LLM topic titles/boundaries with strict validation and
  fragment merging. No live semantic accuracy claim; model adapter tested mocked. No video
  rendering occurs in this mode. Legacy whisper.cpp command retained separately.

- Highlights cut-only defaults: no loudness normalization, gain, compression,
  music mixing, ducking, fades or automatic captions. Native source dimensions
  and nominal FPS unless a platform conversion is explicitly requested. Audio
  uses PCM MOV intermediates and one final AAC encode; source rate/channels kept.
  Old cached Highlights treatment is overridden on reuse, without redoing ASR.

- Primary Highlights/YouTube/Shorts modes reuse creator planning, caching, history,
  rendering and QA. Single edits now default to non-overwriting MP4s beside the
  source, processing state in user cache. --project creates all three edits in a
  source-adjacent organized bundle. --output and --cache-dir override paths.
- Per-mode persistent projects preserve agent revisions. Preview-bound final
  exports, cached plans, safe retries and retained failure diagnostics.
- Highlights compilation/separate ideas; YouTube chronological deduplicated
  sentence cuts; Shorts adjacent complete-sentence clips with vertical defaults.
- Legacy edit syntax retained with warning; URL retry/path-order/UTF-8 failures
  corrected. Legacy default moved to output/legacy; output override added.

- Existing local/transcription/cut/download and vendored Video Use commands retained.
- Persistent source metadata, word transcripts, versioned projects and rollback.
- Standalone sentence-based planning: target duration, bilingual relevance signals,
  include/exclude timestamp constraints, duplicate filtering and selection reasons.
- Common strict plan validator: known fields/sources, revision binding, complete
  sentence/word endpoints, non-overlapping ranges, constraints and explanations.
- Plans save separately and apply only ranges; deep object patches preserve unrelated
  settings. Arrays intentionally replace arrays. Unknown nested settings rejected.
- Semantic requests exclude paths, metadata, brand, settings and unrelated project data.
- Machine JSON inspection, transcript/timeline access, contact sheets, validation,
  apply, previews, approval-bound final exports and revision-tagged feedback.
- Repurposing now produces candidates with preview/approve/export via --clip INDEX.
- Caption cues split on long pauses; invalid timestamps/configuration rejected.
- Fit/crop layouts, profiles, audio-bed mixing/ducking, captions, platform exports,
  manifests, decode/resolution/duration QA and immutable render-job directories.
- Reusable agent editing instructions and practical acceptance checklist.

## Experimental

The new modes are first-pass strategies, not professional creative guarantees.
YouTube removes repeated sentences and trims inter-sentence gaps, not individual
repeated words. Local briefs are recorded but not semantically interpreted. AI
Shorts currently supports count 1; local Shorts supports multiple clips. Music
YouTube preserves the full performance without ASR. New modes take local files;
URL downloads remain a separate command (legacy combined URL editing retained).

Local selection uses complete sentences and simple bilingual ranking, not deep
narrative understanding. It can select weak or context-dependent sentences.
Mechanical completeness uses ASR punctuation; manual review remains mandatory for
context/payoff. Semantic planning is implemented against chat-completions services
and tested using a mocked provider; no live provider or real-footage quality claim.
Repurposing avoids overlapping ranges and near-duplicate sentences in a candidate,
but cross-candidate topic similarity still needs creator review. Music without
speech should use manual ranges rather than speech planning.

## Tests actually executed for this update

- `npm test`: **87 passed, 0 failed, 0 skipped** (61 core, 26 vendored).
- `tests/smoke_highlights.py`: synthetic quiet-tone test passed with native
  640x360/24fps, mono 44.1kHz, two retained cuts, 2-second output, and less than
  0.25 dB interior RMS difference from source in both cuts. Actual listening and
  real-footage perceptual equivalence were not assessed. Frame-accurate cuts
  still require video re-encoding and final AAC is lossy, as in the original tool.
- Destination-default follow-up: synthetic real FFmpeg checks passed for all
  single modes, source-adjacent final MP4s without --output, collision-safe reruns,
  explicit destination/cache overrides, and a default source-adjacent project
  bundle producing YouTube, Highlights and two Shorts. Fixtures generated outside
  the repository in Windows Temp. Windows known Downloads resolved to the user's
  Downloads folder; no external video download was performed for this test.
- `tests/smoke_modes.py`: all three modes through Node CLI passed with paths
  containing spaces, organized output, source-keyed transcript import, saved agent
  revisions, plan caching, previews/approval, two vertical Shorts and QA/manifests.
- Unit simulations verify transcription failure, interrupted rendering, preserved
  diagnostics/state, bad options/targets, missing preview approval and music mode.
- Synthetic FFmpeg acceptance: **passed** landscape/vertical encoding, captions,
  audio mixing, concatenation, QA decode/manifests, multi-source project creation,
  transcript import, deep patch, local plan, plan validation/application, final
  export approval gating, contact sheet, two separate short previews and final
  exports, audio/video stream-duration agreement, history and safe rollback.
- CLI help and git whitespace checks executed successfully.
- Local ASR follow-up: installed faster-whisper 1.2.1 with pinned PyAV 16.1.0,
  downloaded the small model, and passed actual word-timestamp transcription,
  planning and preview rendering on locally synthesized English speech. Retrying
  reused the cached transcript. Provider timestamp scalars/zero-duration markers
  are normalized before strict validation. This is not real-footage language
  accuracy validation.
- Transcription performance follow-up: per-segment console spam replaced with
  start/finish messages. One model reused per invocation; configurable greedy/
  beam decoding, VAD, CPU threads and CUDA detection. On the existing synthetic
  speech clip, two measured runs after warm-up gave median 11.03s previous vs
  7.87s fast (1.40x throughput, 29% less time); both returned 15 words. This is
  not a real-footage accuracy or long-video throughput claim. Fast decoding/VAD
  tradeoffs and overrides are documented in README.
- Real-footage speech/subtitle perceptual sync, creative review, live cloud service
  behavior and platform upload acceptance **not run**; see docs/acceptance.md.
- macOS/Linux runtime testing remains outstanding. Synthetic fixtures are Windows
  test patterns/tones and imported word JSON, not actual Portuguese/English speech.

## Still missing

Face/subject/speaker tracking, manual/animated crop boxes, PiP/split-screen,
independent SFX/music buses, fades/crossfades/sync tools, ASS/keyword animations,
custom font/vocabulary configuration, integrated transitions/B-roll/branding,
duration/file-size platform limits, thumbnails/publishing drafts, automatic
preference retrieval/application, AI budget enforcement and shared render caching.
Comprehensive black-frame/silence/clipping/loudness/caption/overlay QA is missing;
fully_verified remains false. Existing grading/overlays remain available through
legacy helpers, not yet unified into the project renderer.

## Readiness

Suitable for controlled first-pass creator trials with preview and approval.
Not a fully verified professional autonomous editor. No personal footage or paid
API requests were used for these tests; generated media remains ignored in output/.
No push was performed. Prior architecture/audit context is in docs/architecture.md.
