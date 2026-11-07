# Stable agent interface (CLI schema version 1)

## Primary editing modes

Start with `npm run edit -- highlights|youtube|shorts "FILE" --preview` for an
organized project. Returned `mode_projects` point to `data/edits/...`.
Add `--json` to the primary mode command to receive these structured fields;
normal mode runs show a human-readable completion message. `video_files` gives
playable files while `outputs` retains the output-directory list. Use the
mode project paths with the advanced commands below. Each is a normal persistent project,
including history and word transcripts. Re-running the same primary command
loads these revisions; changed mode options create a new variant. Re-preview
after revision, then run the same mode command with --approve for final output.
Default outputs are full-resolution MP4s beside source footage, with processing
state in the user cache; use --preview for a draft. --project creates all three
edits in a named project folder beside the source. --output overrides destinations.
Profiles define defaults, modes define editorial selection, platforms define
delivery. Local rules provide a first pass; use the brief and visual evidence
to improve hook, narrative, context and payoff without editing engine source.

Use `node editor.js` for machine automation; npm adds its own banner. The creator
CLI returns JSON on stdout for editing commands; errors are JSON on stderr with
a nonzero exit. `--json` declares machine intent (results are JSON by default).
Transcription progress goes to stderr. No MCP server is needed.

## Discover, inspect, propose, validate, preview, approve, export

```powershell
node editor.js inspect --project output/launch --json
node editor.js frames --project output/launch --source s0 --json
node editor.js plan --project output/launch --target 60 --json
node editor.js validate-plan --project output/launch --plan-file "output/launch/plans/<id>.json" --json
node editor.js apply-plan --project output/launch --plan-file "output/launch/plans/<id>.json" --json
node editor.js preview --project output/launch --platforms youtube,shorts --json
node editor.js approve --project output/launch --json
node editor.js export --project output/launch --platforms youtube,shorts --json
node editor.js feedback --project output/launch --decision accepted --instructions "Keep the slower explanation" --json
```

`inspect` includes full source metadata, transcripts/word timestamps, settings,
current ranges and a revision hash. `frames` creates an eight-frame contact sheet
and reports its sampling interval; it is evidence, not automatic scene detection.
Open the returned image using the agent's image tool. Render output lists job
paths; read their adjacent qa.json and manifest.json. For focused evidence use
the existing `video-use/helpers/timeline_view.py SOURCE START END`.

## Plan contract

Agents author a JSON plan from the inspect result. Use the exact revision hash:

```json
{
  "schema_version": 1,
  "base_revision": "<revision-from-inspect>",
  "ranges": [
    {"source":"s0","start":1.2,"end":8.6,"reason":"Complete hook explaining the problem"}
  ],
  "constraints": {"include":[],"exclude":[]},
  "review_notes": ["Subjective: check whether the payoff needs more context"]
}
```

Source IDs must exist; timestamps must match complete-sentence endpoints in the
word transcript. Model text is not trusted as evidence: boundaries come from the
stored transcript. Plans reject arbitrary fields/commands, overlap, missing
required moments, excluded spans and stale project revisions. Sentence punctuation
is a mechanical completeness proxy, not proof of narrative coherence. Correct
bad ASR punctuation first. Music/no-speech projects should use manual range patches.

`apply-plan` saves history and changes ranges. It never changes sources/settings.
Preview after applying; summarize technical QA separately from subjective creative
review. Ask the creator to approve deliberate creative choices. `approve` records
the current revision; changed settings/ranges invalidate final export approval.
Existing render jobs and history snapshots are never overwritten by these commands.
Do not bypass approval by fabricating source files or modifying engine code.

## Standalone planning and constraints

Local `plan` uses sentences, bilingual relevance signals, chronological order,
and normalized-token duplicate detection. Required moments override the duration
target; excludes take precedence over conflicting includes (reported as an error).
Sentences that cannot fit may leave the result short. No punctuation means the
planner requests transcript correction rather than selecting a fragment.

```json
{"include":[{"source":"s0","start":135,"end":140}],
 "exclude":[{"source":"s0","start":20,"end":30}]}
```

Pass this as `plan --constraints constraints.json --target 60`. Optional
`--semantic --instructions "..."` sends only instructions, target, constraints,
source IDs and words to LLM_URL. Paths, brand, metadata, history and unrelated
settings are excluded. Responses pass the same plan validator before being saved.

## Repurposing

```powershell
node editor.js repurpose --project output/launch --count 3 --target 30
node editor.js preview --project output/launch --clip 1 --platforms shorts
node editor.js approve --project output/launch --clip 1
node editor.js export --project output/launch --clip 1 --platforms shorts,instagram,tiktok
```

Repeat preview/approve/export for each candidate index reported by repurpose.
Candidates have disjoint ranges across clips and share the original project
revision; changing the project invalidates them. They may still cover similar
topics. Review standalone context and originality manually. Candidate ranges are
selected locally; no semantic standalone-quality guarantee is claimed.

## Revision and feedback

`revise --patch patch.json` recursively merges known object fields. Arrays replace
entire arrays, deliberately. Example: `{"settings":{"caption":"cinematic"}}`
preserves unrelated audio/layout settings. Use inspect after a patch. New custom
export names are allowed with safe filename characters. Use `history` and
`rollback --version FILENAME` to recover prior decisions. Feedback accepts
`--decision accepted|rejected|note` and logs the exact project revision. Logs are
local and inspectable; automatic preference application remains future work.

## Creative brief examples

- Build in public: identify problem, experiment, result and lesson; keep screen
  evidence; use fit layout and explain any omitted failure/context.
- Coding tutorial: preserve prerequisite steps and readable code; avoid cropping
  controls; verify that instructions remain executable in the selected order.
- Personal essay: preserve emotional pauses and the reflection's payoff; propose
  restrained captions and transitions rather than treating every pause as waste.
- Music performance: preserve musical phrases and dynamics; use manual timeline
  ranges when no speech exists; keep lufs null unless explicitly requested.
- Creative storytelling: retain setup/payoff and intended suspense; propose any
  visual assets with relevance and rights notes before creating them.
- Social short: select one complete insight with immediate context and a clean
  ending; check the first and last spoken words in the rendered preview.

Codex and Claude Code can both follow this document from the repository root.
The reusable local instruction entry point is `skills/creator-editing/SKILL.md`;
no global skill installation is required to read it.
