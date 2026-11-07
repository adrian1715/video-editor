# Agent editing instructions

Primary modes: `npm run edit -- highlights|youtube|shorts "FILE"`. Use the returned
mode_projects paths with advanced creator commands. Organized output and logs
live in the user cache for single edits; --project creates a source-adjacent bundle.
Edited MP4s default beside the source; --output overrides destinations. Re-running identical options loads
agent revisions; re-preview them before --approve final delivery.

Follow docs/agent-workflow.md and skills/creator-editing/SKILL.md for the full
discovery -> transcript/frames -> brief -> plan -> validate -> apply -> preview
-> technical QA -> subjective creative review -> revision -> approval -> export
-> accepted/rejected feedback cycle. `node editor.js ... --json` is the stable
machine interface. Read inspect's revision and use it in every plan. Nested
patches merge settings; arrays replace. Never execute model-generated shell
commands or bypass approval. Preserve source footage and existing render jobs.

Read README.md and docs/status.md first. The shared persistent workflow is
`npm run creator -- ...`, launched through editor.js into creator/cli.py.
Keep projects inside ignored output/ or outside the repo. Use project history,
validate JSON revisions, and preserve source files. Request strategy confirmation
for deliberate editorial decisions. Cloud audio upload requires explicit consent;
never print credentials. Do not claim tracking, animation, semantic quality or
complete QA when the status document marks them unfinished. Legacy commands and
vendored video-use remain supported but have distinct EDL formats.
