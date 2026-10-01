param()
$ErrorActionPreference = 'Stop'
$trackingRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$trackingConfig = Get-Content -LiteralPath (Join-Path $trackingRoot 'configs/tracking.json') -Raw | ConvertFrom-Json
$trackingPython = if ([IO.Path]::IsPathRooted($trackingConfig.python)) {
    [IO.Path]::GetFullPath($trackingConfig.python)
} else {
    [IO.Path]::GetFullPath((Join-Path $trackingRoot $trackingConfig.python))
}
if (-not (Test-Path -LiteralPath $trackingPython)) { throw 'Tracking Python is missing. Check configs/tracking.json.' }
$previousRoot = $env:TAKEONE_ROOT
$previousPythonPath = $env:PYTHONPATH
try {
    $env:TAKEONE_ROOT = $trackingRoot
    $env:PYTHONPATH = Join-Path $trackingRoot 'packages'
    & $trackingPython -B -m takeone.motion.tracking_worker --check
    if ($LASTEXITCODE -ne 0) { throw 'Tracking dependency/source checks failed.' }
} finally {
    $env:TAKEONE_ROOT = $previousRoot
    $env:PYTHONPATH = $previousPythonPath
}
