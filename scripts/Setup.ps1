param([string]$PythonVersion = '3.13')
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
Push-Location $projectRoot
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) { throw 'Install uv from its official distribution, then retry.' }
    if (-not (Test-Path -LiteralPath '.venv\Scripts\python.exe')) {
        uv venv --python $PythonVersion .venv
        if ($LASTEXITCODE -ne 0) { throw 'Python environment creation failed.' }
    }
    uv pip install --python '.venv\Scripts\python.exe' -r requirements-simulation.lock.txt -e '.[dev]'
    if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
    Push-Location (Join-Path $projectRoot 'apps\rehearsal')
    try { npm ci --no-audit --no-fund; if ($LASTEXITCODE -ne 0) { throw 'Web dependency installation failed.' } }
    finally { Pop-Location }
    & (Join-Path $projectRoot '.venv\Scripts\python.exe') -m takeone.simulation.model
    if ($LASTEXITCODE -ne 0) { throw 'Robot asset generation failed.' }
    Write-Host 'Setup complete. LeRobot and physical devices were not changed.'
} finally { Pop-Location }
