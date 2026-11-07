# Architecture and extension points

Primary entry `npm run edit -- MODE FILE` dispatches auto-edit.js -> editor.js
-> creator/modes.py. Modes orchestrates existing cli.py and planning.py rather
than adding another renderer. Project roots hold data/edits/<mode-variant>/,
mode outputs, assets, temporary intermediates and reports when --project is used.
Default single-mode delivery is flat MP4 files beside the first source; the same
workspace structure is retained in the OS user cache, with --cache-dir override.
Full project bundles run all modes into a named source-adjacent root, overridable
with --output. --output for single modes names only the delivery directory.
Source transcripts
are shared at data/project.json; per-mode projects have their own history and
agent-modifiable ranges/settings. Mode plans are cached by source-project
revision and options. New options produce new variants. Preview records bind
approval to edit revision and target platforms. Logs retain full FFmpeg stderr.

Original commit 1300a980 used Node/Whisper/segments.json with agent-led Pareto
selection, complete ideas, manual iterative cuts and explicit kept-percentage
reporting. These legacy commands remain. The newer legacy auto-edit Scribe path
had new-file-only URL detection, FFmpeg PATH setup after URL merging, source-adjacent
outputs and Unicode console failures. These paths now have targeted fixes and
migration messaging; live website behavior was not tested.

Legacy Node tools remain independent. `editor.js` resolves interpreters and
FFmpeg for `creator/cli.py`, a standard-library project adapter. Subprocesses use
argument arrays without a shell. AI responses may supply only validated range
data; no generated commands run.

Each project contains project.json, history/*.json, preferences.json, optional
plans/*.json, candidates.json, per-source Scribe asr caches and renders/<job>/.
Each render contains extracted clips, concat list, base MP4, SRT, final MP4,
qa.json and manifest.json. Paths are resolved against the process directory;
source paths are absolute. Output folders must not overlap source filenames.

Revise recursively merges object fields and replaces arrays. History uses nanosecond filenames.
Project writes use same-directory temporary files followed by atomic replace.
Interrupted exports retain intermediate evidence; no automatic deletion occurs.

Extend via tested adapters rather than modifying vendor internals. Future work:
split CLI persistence, provider, caption, rendering and QA functions into modules;
add schemas with strict nested field/type validation and configuration files;
connect project grading/overlays to vendor helpers; cache segments by source,
range and rendering settings. Vendor license/attribution must remain intact.

creator/planning.py contains pure local selection, constraint/boundary validation,
minimal semantic payload and recursive patch functions. Plans carry a hash of
the project revision to reject stale edits. apply-plan only changes ranges.
Approvals bind final exports to exact revisions; preview is always available.
Candidate clip approvals use separate approval-INDEX.json files. Render jobs,
plans, and history have unique names. JSON CLI output is the agent interface.
