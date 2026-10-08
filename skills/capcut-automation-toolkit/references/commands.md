# Commands and project inputs

Run commands from the intended working directory; Python file operations create backups and validate inputs. Desktop operations require the authorized Windows session and foreground CapCut. All toolkit options precede the subcommand: `--draft-root`, `--exe`, `--projects-root`, `--backend auto|uia|vision`, `--allow-close`. Environment equivalents: `CAPCUT_DRAFT_ROOT`, `CAPCUT_EXE`, `CAPCUT_PROJECTS_ROOT`; optical OCR override: `CAPCUT_TESSERACT`.

## Read-only inspection and lifecycle

```powershell
capcut-kit doctor
capcut-kit ls
capcut-kit state --draft Example
capcut-kit clips
capcut-kit playhead
capcut-kit shot "<private-screenshot.png>"
capcut-kit launch
capcut-kit open Example
# Only after the user's work has been saved and closing is authorized:
capcut-kit --allow-close quit
```

`shot` creates a potentially private screenshot. `state` can expose project paths and data. Keep raw outputs local. Read JSON `success` and check the process exit code; stderr carries diagnostics. An argparse error may produce no JSON, so handle empty stdout as a failure.

## File editing: CapCut must be closed

Create `<job>/raw/source.mp4` and `<job>/transcript/cuts.json`:

```json
{"clip":"source.mp4","fps":24,"segments":[{"start":1,"end":3},{"start":4,"end":5}]}
```

```powershell
capcut-kit replay "<job>" --name Example
capcut-kit add-text Example "Title" --at 0 --dur 3
capcut-kit add-overlay Example "<overlay.mp4>" --at 1 --dur 2 --src 0 --layer 1 --mute
capcut-kit transform Example --track overlay --index 0 --scale 0.5 --x 0.1 --y 0 --rotate 0 --opacity 1
capcut-kit keyframe Example --track overlay --index 0 --at 1 --x 0.1
capcut-kit clear-keyframes Example --track overlay --index 0
capcut-kit remove Example --track text --index 0
```

`replay` refuses an existing draft name. `--force` on supported add commands permits matching duplicate additions; it is not permission to overwrite projects. Transform x/y are normalized to half canvas dimensions: x=0.1 is 96 pixels right at width 1920; y=0.1 is 54 pixels up at height 1080. Keyframes on reversed/retimed clips remain unsupported. `graphics Example <job>` reads `<job>/graphics-plan.json`: `{"graphics":[{"file":"card.mp4","start":0}]}` and `<job>/assets/card.mp4`. Every referenced asset must exist; repeated batches add another track.

## Native timeline and local export

```powershell
capcut-kit open Example
capcut-kit seek 2 --draft Example
capcut-kit select 0
capcut-kit split 2 --draft Example
capcut-kit undo
capcut-kit redo
capcut-kit delete 0
capcut-kit trim-left
capcut-kit trim-right
capcut-kit marker
capcut-kit zoomfit
capcut-kit play
capcut-kit save
capcut-kit export --to "<output-directory>" --timeout 180
```

History, trims and markers operate on the active timeline/selection. `play` toggles playback. Verify playhead and selection before editing. `save` checks the visible native Auto saved indicator and saved-file timestamp; an unchanged freshly reopened project may have no indicator yet. Do not claim full saved-state verification from this receipt alone.

Prefer semantic commands over `click`, `clickxy`, `scroll` or `key`. Generic pointer coordinates are physical screen pixels, including negative monitor origins; do not derive them by stretching another layout. Those commands dispatch input without independently proving the effect.

Export acceptance covers supported local 1080P/H.264/MP4 settings at 24/30 fps, cloud sync off. A preexisting output or ambiguous settings should stop for inspection. Check each actual result:

```powershell
ffprobe -v error -show_streams -show_format -of json "<output.mp4>"
ffmpeg -v error -i "<output.mp4>" -f null -
```

A full decode proves media readability, not editing intent; compare requested timing, representative rendered frames and audio. AAC encoder padding can make container duration slightly longer than video duration. Toolkit documentation and release evidence remain authoritative for the installed version: [README](https://github.com/bahattab/capcut-automation-toolkit/blob/main/README.md), [verification](https://github.com/bahattab/capcut-automation-toolkit/blob/main/VERIFICATION.md).
