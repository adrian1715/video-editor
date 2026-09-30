# Video highlights pipeline

Local, free tools that turn a long video (Portuguese or English, any size) into a
short highlights video. Everything runs on this machine with FFmpeg and whisper.cpp;
nothing is uploaded. Plain Node.js, no npm dependencies.

**Project root:** `C:\Users\Adrian\Documents\Projects\Coding\video-editor` (called
`$P` below). A session may be started in any directory, so always run the scripts
by absolute path, e.g.
`node "C:/Users/Adrian/Documents/Projects/Coding/video-editor/transcribe.js" "<video>"`.
Outputs always go to `$P/output/<name>/` whatever the working directory is, where
`<name>` is the video file name without its extension. Quote paths, since video
paths often contain spaces.

| Script | What it does |
|---|---|
| `node $P/setup.js [--model medium]` | Checks FFmpeg, downloads the prebuilt whisper.cpp binary into `bin/` and models into `models/`. Run it if another script says something is missing |
| `node $P/transcribe.js <video> [--model medium] [--language pt]` | Writes `output/<name>/transcript.txt`, `transcript.srt` and `meta.json` (duration, language) |
| `node $P/cut.js <video> [segments.json] [--vertical] [--separate] [--no-fade] [--fade 0.3] [--cpu]` | Cuts and joins into `output/<name>/highlights.mp4` (`highlights-vertical.mp4`, or `clips/` / `clips-vertical/` with `--separate`). Defaults to `output/<name>/segments.json` |
| `node $P/silence.js <video> [--noise -30] [--min 1]` | Lists dead air in `silence.json` and writes `no-silence.json` (a segments file of only the parts with sound) |

## When the user says "make highlights of <file>"

1. **Transcribe.** First check whether `$P/output/<name>/transcript.txt` already
   exists. If it does, reuse it unless the user asks to redo it. Otherwise run
   `transcribe.js` **in the background** (Bash `run_in_background: true`,
   redirecting output to a log file) and wait for the completion notification.
   Don't poll it or sleep.
   - It takes about 0.3× the video's length with the `small` model on this laptop
     (1h45m took 31 min). Tell the user the ETA, that you'll continue
     automatically when it's done, and that they should keep the session open and
     the PC awake.
   - Use `--model medium` if the user asks for better accuracy or the transcript
     is clearly garbled.

2. **Read the whole transcript** (in chunks of ~300 lines if it's long) and take
   the duration from `meta.json`. Work out what kind of video it is (vlog, meeting,
   tutorial, podcast...) and who it's for. The user is a content creator; e.g.
   `Videos\Creative Process\Unify\` holds build-in-public footage of friends
   planning a student dating app.

3. **Pick the highlights using Pareto: ~20% of the video carrying ~80% of the
   impact.** Be selective and keep only the moments that carry the value.
   - **Keep:** strong hooks, funny or surprising moments, key insights,
     decisions and takeaways, emotional peaks, quotable lines, and plot twists
     (e.g. finding out a competitor exists).
   - **Cut:** filler, tangents, circular debates (keep the sharpest exchange and
     the resolution, not every lap), setup that goes nowhere, mic checks,
     repeated takes (keep the best, usually the last clean one), and dead air.
   - **Leave out** gossip or insults about people who aren't present, and
     comments about strangers' looks. Keep crude or edgy-but-funny moments, but
     **flag them** (⚠️) in the report so the user can decide.
   - **Each segment is a complete thought.** Start at the beginning of a sentence
     and end at the end of one. Transcript lines often break mid-sentence, so read
     the neighbouring lines to find the real boundaries. Pad about 1–2s either
     side, clamped so you don't reach into speech you're not keeping.
   - Merge kept moments that are only a few seconds apart. Keep chronological
     order unless the user asks otherwise. Ending on the natural outro or
     sign-off works well.

4. **Write `$P/output/<name>/segments.json`:**
   ```json
   [{"start": "00:02:14.00", "end": "00:02:41.50", "reason": "One line on why this earns its place"}]
   ```

5. **Length.** If the user gave a length, hit it. Otherwise aim for about 20% of
   the original. That's a target, not a hard rule: go under for short or thin
   videos, and a little over if it's packed with strong material. Add up the
   segment lengths before cutting. Only ask for a target length if it's genuinely
   unclear what the user wants.

6. **Cut.** Run `node $P/cut.js "<file>"`, adding `--vertical` for
   Shorts/Reels/TikTok, `--separate` for individual clips, and `--no-fade` for
   hard cuts. Redirect the progress output to a log and show only the summary.
   Then confirm the result with ffprobe: the duration should match the total and
   the audio and video durations should match each other.

7. **Report back** with:
   - The output path, the total length, and **the percentage of the original
     kept**.
   - A markdown table of segments: #, start, end, length, reason (⚠️ on edgy
     ones).
   - One line on what was left out, and a note that transcript timing can be ~1s
     off in noisy multi-speaker audio, so the user should skim the cut and
     report any clipped segment by number.
   - **A suggested title, a caption, and 5–8 hashtags**, in the video's language
     (Portuguese videos get Portuguese copy).

   Then invite changes ("drop #3", "add the bit about X", "10 minutes max",
   "vertical", "clips of #2 and #9"). Edit `segments.json`, re-run `cut.js` with
   the same flags (no need to re-transcribe), and report the updated table and
   percentage. For clips of only some segments, write a separate segments file
   and pass it to `cut.js --separate`.

## Notes
- Timestamps in the transcript are `[HH:MM:SS.cc - HH:MM:SS.cc]`; `segments.json`
  accepts the same format (also `MM:SS` or plain seconds).
- `cut.js` re-encodes every segment (frame-accurate), snaps phone variable
  frame rates to a standard rate, and auto-selects a hardware H.264 encoder (on
  this laptop: Intel Quick Sync `h264_qsv`), falling back to libx264. `--cpu`
  forces libx264. A ~20-minute 1080p reel takes a few minutes.
- `--vertical` centre-crops to 9:16 and scales to 1080×1920.
- To trim dead air instead of picking highlights, run `silence.js` and then
  `cut.js <file> output/<name>/no-silence.json --no-fade`.
- FFmpeg is installed via winget. The scripts find it even if PATH hasn't
  refreshed in the current shell.
