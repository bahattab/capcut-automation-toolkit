# Verification

## 0.3 adaptive layout acceptance — 2026-10-08

**568 tests passed**, with zero failures, errors or skips. This release removes the 9.5 editor resolution allowlist and automatic resizing of an identified editor. Four independent toolbar glyphs and the Cover control determine panel regions. Duplicate normal/hover variants and mixed playback states are rejected together. Native history allows a bounded monitor compositor shadow only while the process, editor rectangle and project title remain stable.

- [Native acceptance](verification/native-adaptive-acceptance.json): 1280×760 and 1920×1080 split/Undo/Redo/Undo/save state comparisons; 1536×864 inspection/seek/export; installed 1600×900 inspection/seek/split/Undo/save/export. `open` retained the installed editor rectangle.
- [Exports](verification/export-adaptive-summary.json): three new synthetic 1920×1080 H.264, 24 fps, six-second exports, independently probed and fully decoded.
- [Regression](verification/tests-adaptive-summary.json), [independent review](verification/review-adaptive-summary.json), [package parity](verification/package-adaptive-summary.json) and [preservation](verification/preservation-adaptive-summary.json).
- [DPI scope](verification/dpi-adaptive-summary.json): actual native monitors are 96 DPI. Synthetic assets and physical coordinates cover 75–400% scaling. Native higher-DPI rendering remains unverified and strict export-footer checks may reject it.

Native acceptance remains bounded to CapCut 9.5.0.4050, English UI, readable Latin titles, visible primary timeline controls and the supported local export settings. Dispatch receipts are supported by independent saved-state comparisons; no fresh claim is made for every historical command at every size. Public evidence excludes personal paths, user media, raw desktop captures and application logs. The archived 0.2 resizing behavior below describes that release and is superseded in 0.3.

## 0.2 measured 900p acceptance — 2026-10-08

503 regression tests passed with no failures, errors or skips. Native acceptance is bounded to CapCut 9.5.0.4050, English UI, the exact 1600×900 work area, restored 1616×916 editor frame, and 720×663 local export dialog. Native history labels are checked in both OCR scales, including the inset menu after reopening.

- [Native edits and reopening](verification/native-900-acceptance.json): saved split/history/delete/trim/marker effects, fit enlargement, actual playback, complete tracked state comparisons for two reopened synthetic projects, and installed console checks.
- [Rendered effects and audio](verification/render-900-summary.json): three animated blue-overlay frames, yellow graphic, timed text, primary 440 Hz audio, muted 880 Hz overlay and an unmuted positive control; full FFmpeg decode. Both final synthetic exports contain 144 H.264 frames at 24 fps and 1920×1080.
- [Preservation](verification/preservation-900-summary.json): all 35 baseline project files unchanged.
- [Packaging](verification/package-900-summary.json): installed package and wheel match all 31 source/template files.
- [Regression](verification/tests-900-summary.json) and [independent review](verification/review-900-summary.json).

The final installed native smoke performed split at two seconds, Undo and Save, then verified the complete baseline saved state. Public evidence contains measurements and synthetic fixture names; private media paths and desktop captures are excluded. The original broader command acceptance below is historical evidence for its original profile, not a fresh 900p run of all 35 routes.

## Original release acceptance

Final Windows Python 3.12 suite: **443 passed**, zero failed/error/skipped. See verification/tests.xml and tests-summary.json. Tests include real FFmpeg media, transaction rollback, input ownership, stale pixels, ambiguous OCR, clipboard recovery and native schema regression.

All 35 upstream commands are covered:

| Group | Commands | Evidence |
|---|---|---|
| File edits | replay, graphics, add-overlay, add-text, remove, transform, keyframe, clear-keyframes | Ten native-file-*-reopen receipts, render/pixel/audio verification |
| Lifecycle | ls, launch, quit, open | Native openings, graceful native-cli-quit |
| Inspection | clips, playhead, state, dump, shot | Generic and final installed-console acceptance |
| Input | click, clickxy, scroll, key | native-cli-generic, remaining-live, final-live |
| Editing | seek, select, split, delete, del, trim-left, trim-right, undo, redo, marker, zoomfit, play | Saved editing/trims, marker/fit, playback, exact long seek 0â†’75.25â†’0, final 30 fps split/delete and complete Undo restoration |
| Persistence | save, export | Native autosave/full reopen; ten exported videos fully decoded |

`doctor` is an additional Windows command. Dispatch receipts can retain effect_verified=false: independent saved-state and rendered comparisons provide effect evidence; a dispatched input alone is never treated as success.

Ten variants cover source offsets, Arabic three-line text and emoji, overlay placement, scale/position/rotation/opacity, removal, cleared animation, generated graphics, all five keyframe properties with midpoint interpolation, and 30 fps output. Audio checks independently detect primary 440 Hz audio across cuts, a muted 880 Hz overlay, and an unmuted positive control. Export checks verify 1920Ã—1080, 24Ã—72 or 30Ã—90 frames, and full FFmpeg decode.

Native CapCut canonicalizes text source ranges to null and removes empty tracks. Comparisons allow only those observed changes; integer timing is exact and finite float tolerance is 1e-12. Position coordinates use half-canvas dimensions: x=.1 is 96 px right and y=.1 is 54 px up at 1920Ã—1080.

File edits require CapCut closed and retain transactional backups. Native export reads preserve supported HGLOBAL clipboard formats; unsupported formats are rejected before copy. Temporary recovery is user-scoped DPAPI encrypted before copying and deleted only after exact restoration. An external clipboard update is preserved. No forced process termination or cloud/social publishing is used.

Scope: exact CapCut 9.5.0.4050, English UI, readable unique Latin project names, visible Home List row, editor 1680Ã—1050/1051, export 720Ã—663 at 1080P/H.264/MP4 24/30 fps. Unknown or ambiguous profiles fail closed. Reversed/retimed keyframe edits and arbitrary export settings are not claimed verified. Original user project: all 33 baseline file hashes unchanged. Public evidence contains synthetic fixture names and measurements, without original project data or raw desktop captures.
