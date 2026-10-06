# for windows capcut-kit

[GitHub repository](https://github.com/bahattab/for-windows-capcut-kit)

Windows port of [matt-j-penny/capcut-kit](https://github.com/matt-j-penny/capcut-kit), upstream commit `304c125b626cd35843dc0ba723547ee7ff54eee5`.

Verified Windows release: **443 tests passed**, zero failures or skips. All 35 upstream commands have native acceptance evidence on **CapCut 9.5.0.4050**. Ten disposable projects survived opening and full saved-state reopening; exported video, Arabic/emoji text, overlay timing, transforms, animation and audio were independently checked. The installed `capcut-kit` command passed a final native smoke test. Original project preservation: 33 baseline file hashes unchanged.

The verified optical profile uses English UI, readable unique Latin project titles, a fully visible Home List row, editor size 1680×1050/1051, and the 720×663 export dialog. Local export was checked at 1920×1080, H.264/MP4, 24 and 30 fps, with cloud sync disabled. Other versions, layouts, languages and export settings need their own native acceptance. Uncertain recognition stops before input. Close unrelated modal dialogs before commands; title reading may take up to three minutes on a busy desktop.

See [VERIFICATION.md](VERIFICATION.md) for evidence and [GATES.md](GATES.md) for release status.

## Install

Requirements: Windows, Python 3.12 or newer, CapCut Desktop, Tesseract OCR with English language data on PATH, and FFmpeg with `ffmpeg` and `ffprobe` on PATH. The development run uses an isolated Python 3.12 environment. No Apple frameworks are required.

From this directory:

```powershell

uv venv --python 3.12 .venv

uv pip install --python .venv\Scripts\python.exe -e ".[test]"

.venv\Scripts\capcut-kit.exe doctor

.venv\Scripts\python.exe -m pytest -q

```

The original entry-point convention is also available:

```powershell

uv run capcut-bridge.py --help

uv run capcut-bridge.py doctor

```

`doctor` reports discovered prerequisites. It does not certify that CapCut starts or that every desktop command works.

## Paths

Drafts default to `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft`. The executable is discovered under `%LOCALAPPDATA%\CapCut\Apps`. Windows drafts use `draft_content.json`; legacy `draft_info.json` is also read.

Use `CAPCUT_DRAFT_ROOT`, `CAPCUT_EXE`, and `CAPCUT_PROJECTS_ROOT` to override discovery, or pass global options before the command:

```powershell

capcut-kit --draft-root "D:\Test Drafts" --projects-root "D:\Jobs" ls

```

## File commands

Save your work and close CapCut before every file edit. The bridge checks that CapCut is closed before file edits and commit, including when an unrelated project is open. Process checks cannot eliminate a concurrent-launch race. It never closes the app automatically for file edits.

```text

replay <job-directory-or-name> [--name <draft>]

add-overlay <draft> <video> --at <seconds> [--dur <seconds>] [--src <seconds>] [--layer N] [--ri N] [--mute] [--force]

add-text <draft> "<text>" --at <seconds> [--dur <seconds>] [--ri N] [--force]

graphics <draft> <job-directory-or-name>

transform <draft> [--track main|text|overlay] [--index N] [--scale S] [--x X] [--y Y] [--rotate R] [--opacity O]

remove <draft> [--track main|text|overlay] [--index N]

keyframe <draft> --at <timeline-seconds> [--track main|text|overlay] [--index N] [transform properties]

clear-keyframes <draft> [--track main|text|overlay] [--index N]

ls

state --draft <draft>

```

Times are in seconds. File commands validate numeric values, media bounds and draft names in Python. Existing drafts cannot be overwritten by `replay`. Text uses a local Windows system font; Arabic and emoji text were checked in native rendering. Keyframes on reversed or retimed clips are rejected pending native-schema verification.

Before edits, the bridge copies the draft and registry into `.capcut-kit-backups` under the configured draft root. Media is copied into the draft's `Resources` with a content-derived filename. A failed transaction restores the backup while CapCut remains closed. If CapCut starts concurrently, automatic recovery stops rather than overwriting app-owned state. Keep the backup for manual recovery after closing CapCut.

## Desktop commands

```text

launch | quit | open <draft>

seek <seconds> [--draft <draft>]

select <index> | split [seconds] [--draft <draft>] | delete <index>

trim-left | trim-right | undo | redo | marker | zoomfit | save

play | playhead | clips | state [--draft <draft>]

export [--to <directory>] [--timeout <seconds>]

shot [output.png]

dump [needle] | click <exact-name-or-id> | clickxy <x> <y> [--clicks 1|2]

key <combination> [--times N]

scroll <x> <y> <wheel-steps>

```

These commands use the selected desktop backend. The auto default uses the optical driver for the two tested executable versions; explicit --backend uia selects Windows UI Automation. The tested CapCut 9.4.0.4015 exposes editor window nodes without the required child controls, so commands that require named buttons, fields, timeline clips or timecodes cannot meet native acceptance on this installation. A missing or ambiguous control returns an error. The driver checks foreground process and owning window before sending input, and mouse targets reject overlapping foreign windows. It does not reuse macOS screen offsets.

The local Tesseract optical backend can be selected with `--backend vision`; `CAPCUT_TESSERACT` can point to its executable. Complete native command acceptance in this release is on CapCut 9.5.0.4050, with the measured editor layout and 720×663 export dialog at 1080P/H.264/MP4, 24 or 30 fps. Unknown or ambiguous layouts fail closed.

The standalone `scroll_panel.py x y steps` helper is also ported. Windows scrolling uses wheel steps rather than macOS pixel units. Positive steps scroll up, negative steps scroll down; bounds and foreground ownership are checked before dispatch.

`quit` requires the global `--allow-close` option. It requests an ordinary window close and never force-terminates CapCut or dismisses save prompts. `launch` reports a launch request, not verified application readiness. Commands that dispatch input report `effect_verified: false`; a click alone does not prove an edit happened.

Export sets and reads back an exact destination and a unique filename. Local export requires the cloud sync checkbox to be off. It waits for a stable file and verifies media duration, dimensions and decoding. The optical driver returns the verified file path. The native test then closed the post-export screen using its recognized Close button; it invoked no social publishing action. The driver does not assume that Escape closes every native popup.

## Input files

`replay` reads `<job>/transcript/cuts.json` and video from `<job>/raw/`:

```json

{

  "clip": "source.mp4",

  "fps": 24,

  "segments": [

    {"start": 1, "end": 3},

    {"start": 4, "end": 5}

  ]

}

```

`graphics` reads `<job>/graphics-plan.json` and files from `<job>/assets/`:

```json

{"graphics": [{"file": "card.mp4", "start": 0}]}

```

Every graphic must exist. The batch validates all assets before applying changes. Repeated graphics batches add another track; they are not automatically deduplicated.

## Errors and source attribution

The CLI returns structured JSON. Detailed tracebacks are logged to stderr for debugging; unexpected errors returned in JSON are generic. No credentials, existing user projects or generated test media belong in the repository.

Draft material factories in `capcut_windows/schema.py` are adapted from the upstream project and retain its attribution. The checked upstream tree contains no repository-wide license file. This port does not claim to grant a new license over that upstream code. Inter font assets retain their included OFL notice.

Windows automation references: [pywinauto guide](https://pywinauto.readthedocs.io/en/latest/getting_started.html), [Microsoft UI Automation](https://learn.microsoft.com/en-us/windows/win32/winauto/uiauto-clientsoverview), [Qt accessibility](https://doc.qt.io/qt-6/accessible.html).

## Desktop verification behavior

The default auto backend selects the optical driver for the measured CapCut profiles. Complete native acceptance in this release is on 9.5.0.4050. Explicit `--backend uia` remains available where accessible controls exist. History uses native menus/buttons because shortcut interception can occur. Selection names come from saved metadata; active-project checks guard native actions. Graceful quit refuses ambiguous roots and leaves owned save/export dialogs available.
