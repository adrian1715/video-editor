# Production acceptance checklist

## Repeatable automated checks

Run `npm test` and `python tests/smoke_creator.py` with FFmpeg on PATH and
PYTHONUTF8=1. The smoke creates ignored synthetic patterns/tones, word JSON,
projects, contact sheets, previews and final files. It checks real decode,
horizontal/vertical dimensions/duration, captions, multi-source project import,
audio mixing, stream-duration synchronization, nested revisions, plan validation,
approval, two short clip exports and rollback. It does not establish perceptual
speech/subtitle synchronization (the fixture has no real speech).

## Before calling a real edit publishable

- [ ] Import approved footage with English and Brazilian Portuguese speech.
- [ ] Install faster-whisper and verify local ASR word accuracy and timing.
- [ ] If used, consent to Scribe/LLM uploads and verify provider/model behavior.
- [ ] Check hook, complete ideas, narrative context and duplicates by watching.
- [ ] Verify include/exclude constraints and source boundaries on real footage.
- [ ] Listen across every cut: no chopped words, clicks or lost reactions.
- [ ] Check captions against speech, punctuation and phone-sized readability.
- [ ] Listen to narration/music/SFX balance and inspect loudness measurements.
- [ ] Check screens/faces remain readable in fit/crop and platform dimensions.
- [ ] Review every candidate short independently, including its opening/ending.
- [ ] Verify QA JSON and disclose checks that could not run.
- [ ] Approve the reviewed revision, export, and watch final encoded output.
- [ ] Record accepted/rejected choices and confirm rollback preserves originals.

Real ASR/provider quality, artistic coherence and platform upload acceptance require
approved footage, optional credentials and human review. Synthetic success alone
is not a production-readiness claim.
