$ErrorActionPreference = 'Stop'
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw 'Install uv and retry.'
    }
    Push-Location -LiteralPath $PSScriptRoot
    try {
        uv venv --python 3.12 .venv
        if ($LASTEXITCODE -ne 0) { throw 'Environment creation failed.' }
        uv pip install --python .venv\Scripts\python.exe -e '.[test]'
        if ($LASTEXITCODE -ne 0) { throw 'Package installation failed.' }
        & .\.venv\Scripts\capcut-kit.exe doctor
        if ($LASTEXITCODE -ne 0) { throw 'Prerequisite check failed.' }
    } finally {
        Pop-Location
    }
} catch {
    Write-Error $_
    exit 1
}
