param([string]$ToolkitPath)
$ErrorActionPreference = 'Stop'
if ([Environment]::OSVersion.Platform -ne 'Win32NT') {
    throw 'Native CapCut automation requires a Windows runner.'
}

# Prefer a configured OCR executable, then PATH, then the conventional install.
$ocrPath = $env:CAPCUT_TESSERACT
if (-not $ocrPath) {
    $ocrCommand = Get-Command tesseract -ErrorAction SilentlyContinue
    if ($ocrCommand) { $ocrPath = $ocrCommand.Source }
    elseif ($env:ProgramFiles) { $ocrPath = Join-Path $env:ProgramFiles 'Tesseract-OCR\tesseract.exe' }
}
if (-not $ocrPath -or -not (Test-Path -LiteralPath $ocrPath -PathType Leaf)) {
    throw 'Install Tesseract OCR with English (eng) data or set CAPCUT_TESSERACT.'
}
$languages = & $ocrPath --list-langs 2>&1
if ($LASTEXITCODE -ne 0 -or -not ($languages -match '^eng$')) {
    throw 'Tesseract must have the English eng language data installed.'
}
$env:CAPCUT_TESSERACT = $ocrPath
foreach ($tool in @('ffmpeg','ffprobe')) {
    if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
        throw "Install $tool and make it available on PATH."
    }
}

$kit = Get-Command capcut-kit -ErrorAction SilentlyContinue
if (-not $kit) {
    foreach ($tool in @('uv','git')) {
        if (-not (Get-Command $tool -ErrorAction SilentlyContinue)) {
            throw "Install $tool before installing the toolkit."
        }
    }
    if (-not $ToolkitPath) {
        if (-not $env:LOCALAPPDATA) { throw 'Provide -ToolkitPath on this host.' }
        $ToolkitPath = Join-Path $env:LOCALAPPDATA 'capcut-automation-toolkit'
        if (-not (Test-Path -LiteralPath $ToolkitPath)) {
            & git clone https://github.com/bahattab/capcut-automation-toolkit.git $ToolkitPath
            if ($LASTEXITCODE -ne 0) { throw 'Toolkit clone failed.' }
        }
    }
    $ToolkitPath = (Resolve-Path -LiteralPath $ToolkitPath).Path
    $project = Join-Path $ToolkitPath 'pyproject.toml'
    if (-not (Test-Path -LiteralPath $project -PathType Leaf) -or
        -not ((Get-Content -LiteralPath $project -Raw) -match 'name\s*=\s*"for-windows-capcut-kit"')) {
        throw 'ToolkitPath must be a trusted CapCut Automation Toolkit checkout.'
    }
    & uv tool install --force --reinstall --python 3.12 $ToolkitPath
    if ($LASTEXITCODE -ne 0) { throw 'Toolkit installation failed.' }
    $kit = Get-Command capcut-kit -ErrorAction SilentlyContinue
    if (-not $kit) {
        $binOutput = & uv tool dir --bin
        if ($LASTEXITCODE -ne 0) { throw 'Could not discover the uv tool binary directory.' }
        $binary = Join-Path (($binOutput | Out-String).Trim()) 'capcut-kit.exe'
        if (-not (Test-Path -LiteralPath $binary -PathType Leaf)) { throw 'Toolkit executable was not installed.' }
        $kit = Get-Item -LiteralPath $binary
    }
}
$kitPath = if ($kit.Source) { $kit.Source } else { $kit.FullName }
$null = & $kitPath --help
if ($LASTEXITCODE -ne 0) { throw 'Toolkit help smoke test failed.' }
$doctorText = & $kitPath doctor
if ($LASTEXITCODE -ne 0) { throw 'Toolkit doctor failed.' }
$doctor = ($doctorText | Out-String) | ConvertFrom-Json
if (-not $doctor.success -or -not $doctor.result.capcut_installed -or
    -not $doctor.result.draft_root_exists -or -not $doctor.result.ffmpeg -or -not $doctor.result.ffprobe) {
    throw 'CapCut or a required media prerequisite is missing; inspect capcut-kit doctor.'
}
[pscustomobject]@{
    setup_verified = $true
    toolkit_executable = $kitPath
    tesseract_executable = $ocrPath
    english_ocr = $true
    capcut_installed = $true
    ffmpeg = $true
    ffprobe = $true
    native_edit_effect_verified = $false
} | ConvertTo-Json
