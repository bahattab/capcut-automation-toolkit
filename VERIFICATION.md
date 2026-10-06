# Verification

Final Windows Python 3.12 suite: **443 passed**, zero failed/error/skipped. See verification/tests.xml and tests-summary.json. Tests include real FFmpeg media, transaction rollback, input ownership, stale pixels, ambiguous OCR, clipboard recovery and native schema regression.

All 35 upstream commands are covered:

| Group | Commands | Evidence |
|---|---|---|
| File edits | replay, graphics, add-overlay, add-text, remove, transform, keyframe, clear-keyframes | Ten native-file-*-reopen receipts, render/pixel/audio verification |
| Lifecycle | ls, launch, quit, open | Native openings, graceful native-cli-quit |
| Inspection | clips, playhead, state, dump, shot | Generic and final installed-console acceptance |
| Input | click, clickxy, scroll, key | native-cli-generic, remaining-live, final-live |
| Editing | seek, select, split, delete, del, trim-left, trim-right, undo, redo, marker, zoomfit, play | Saved editing/trims, marker/fit, playback, exact long seek 0→75.25→0, final 30 fps split/delete and complete Undo restoration |
| Persistence | save, export | Native autosave/full reopen; ten exported videos fully decoded |

`doctor` is an additional Windows command. Dispatch receipts can retain effect_verified=false: independent saved-state and rendered comparisons provide effect evidence; a dispatched input alone is never treated as success.

Ten variants cover source offsets, Arabic three-line text and emoji, overlay placement, scale/position/rotation/opacity, removal, cleared animation, generated graphics, all five keyframe properties with midpoint interpolation, and 30 fps output. Audio checks independently detect primary 440 Hz audio across cuts, a muted 880 Hz overlay, and an unmuted positive control. Export checks verify 1920×1080, 24×72 or 30×90 frames, and full FFmpeg decode.

Native CapCut canonicalizes text source ranges to null and removes empty tracks. Comparisons allow only those observed changes; integer timing is exact and finite float tolerance is 1e-12. Position coordinates use half-canvas dimensions: x=.1 is 96 px right and y=.1 is 54 px up at 1920×1080.

File edits require CapCut closed and retain transactional backups. Native export reads preserve supported HGLOBAL clipboard formats; unsupported formats are rejected before copy. Temporary recovery is user-scoped DPAPI encrypted before copying and deleted only after exact restoration. An external clipboard update is preserved. No forced process termination or cloud/social publishing is used.

Scope: exact CapCut 9.5.0.4050, English UI, readable unique Latin project names, visible Home List row, editor 1680×1050/1051, export 720×663 at 1080P/H.264/MP4 24/30 fps. Unknown or ambiguous profiles fail closed. Reversed/retimed keyframe edits and arbitrary export settings are not claimed verified. Original user project: all 33 baseline file hashes unchanged. Public evidence contains synthetic fixture names and measurements, without original project data or raw desktop captures.
