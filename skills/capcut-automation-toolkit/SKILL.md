---
name: capcut-automation-toolkit
description: 'Edit videos and automate CapCut Desktop projects on Windows. Trigger phrases: "Edit", "Edit vidoe" (exact user spelling), and "Edit video", when the request concerns video editing or CapCut. Use for cuts, overlays, text, transforms, animation, native timeline editing and verified local export.'
metadata:
  display_name: CapCut Automation Toolkit
---

# CapCut Automation Toolkit

Trigger this skill for **Edit** or **Edit vidoe** in a video-editing context. Preserve the user's requested editing app and output; ask for the source/project and edit intent only when missing. A bare "Edit" with no video context needs clarification. Text/code editing is outside this skill.

## Setup and agent portability

Any agent with file access and a Windows command runner can use this package; no Codex API, MCP server, paid service or account credential is required. Use PowerShell/terminal equivalents provided by the host. Resolve bundled files relative to this SKILL.md. On another operating system, use an available authorized Windows runner; without one, report that native CapCut execution is unavailable rather than silently substituting an editor.

On first use, **read this entire file**, then run the bundled [scripts/setup.ps1](scripts/setup.ps1) in PowerShell. It checks or installs the toolkit CLI, verifies CapCut discovery, English OCR data, FFmpeg and FFprobe, and runs read-only CLI checks. It does not launch, edit or close CapCut. Existing installations are reused; use `-ToolkitPath` for a trusted checkout. If prerequisites are missing, install the named prerequisite through the host's supported installer and rerun setup. Never install the upstream `.mcp.json`.

```powershell
& "<skill-directory>/scripts/setup.ps1" -ToolkitPath "<toolkit-checkout>"
```

`-ToolkitPath` is optional. Without an installed CLI or supplied checkout, setup clones the public repository into a user-local application directory and installs with uv/Python 3.12. Git and uv are needed for that installation. CapCut Desktop, Tesseract with `eng`, FFmpeg and FFprobe are required locally. If OCR is not on PATH, use the discovered path as `CAPCUT_TESSERACT` in each command execution environment. Discover project/executable locations with `doctor` and environment overrides; never embed another user's paths.

## Editing workflow

Read [references/commands.md](references/commands.md) for CLI syntax and input schemas before executing an operation. Use the installed `capcut-kit --help` and subcommand help to resolve version differences. Toolkit source and current documentation: [capcut-automation-toolkit](https://github.com/bahattab/capcut-automation-toolkit).

1. Resolve the user's source files, target project, requested cuts/effects, output location and frame rate. Inspect media with FFprobe. Work in a disposable/new project when possible and preserve originals. Treat timestamps as seconds and timeline/source offsets as distinct values.
2. Choose file editing for deterministic cuts, text, overlays, transforms and keyframes. Save and gracefully close CapCut before file edits; the backend refuses writes while any CapCut process is running. Ask the user to save unsaved work if its state is unknown. Close only when authorized, never force terminate. Do not bypass the backend or overwrite an existing draft.
3. Use native commands for inspecting/adjusting the live timeline. Confirm the intended active draft and leave CapCut foreground during the command. Read `clips`, `playhead` or a project snapshot before changing it. Seek/select deliberately; do not blindly repeat a command after uncertain dispatch because the first attempt may have applied.
4. Save and export locally using an explicit `--to` directory. Keep cloud synchronization disabled; do not publish/share media without the user's instruction. Validate the exported file with FFprobe and a full FFmpeg decode; inspect representative frames/audio for the requested effects. Compare complete relevant saved state after history or reopening when those effects matter.
5. Report what changed, the actual output path, verification performed and any remaining limitation. CLI `success` or `effect_verified=false` dispatch is not proof of a completed native edit. `doctor` confirms prerequisites only.

## Native recognition scope

The 0.3 toolkit has native acceptance for CapCut **9.5.0.4050, English UI**, readable unique Latin project titles and visible primary timeline controls. Editor regions are detected from native anchors rather than a screen resolution allowlist; identified editors retain their window size. Tested windows: 1280×760, 1600×900, 1536×864 and 1920×1080 across two monitors, all at **100% scaling**. Synthetic 75–400% asset/coordinate checks do not certify native high-DPI execution. Strict export-footer recognition may reject different rendering. Historical full command acceptance is not fresh acceptance of every command at every size.

If focus, ownership, DPI, pixels, OCR or icon uniqueness checks fail, reacquire the intended stable editor and inspect the effect before retrying. Do not scale old coordinates, lower confidence thresholds or bypass ambiguity guards to make a command succeed. A changed version/language/layout requires its own native acceptance. Keep screenshots, application logs, personal project metadata and user media private unless the user requests sharing them.
