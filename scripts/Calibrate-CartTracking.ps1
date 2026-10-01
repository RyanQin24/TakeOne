$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$configPath = Join-Path $projectRoot 'configs\tracking.json'
$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$trackingPython = if ([IO.Path]::IsPathRooted($config.python)) {
    [IO.Path]::GetFullPath($config.python)
} else {
    [IO.Path]::GetFullPath((Join-Path $projectRoot $config.python))
}
if (-not (Test-Path -LiteralPath $trackingPython)) {
    throw 'Tracking Python is missing. Check configs/tracking.json.'
}

$previousRoot = $env:TAKEONE_ROOT
$previousPythonPath = $env:PYTHONPATH
try {
    $env:TAKEONE_ROOT = $projectRoot
    $env:PYTHONPATH = Join-Path $projectRoot 'packages'
    & $trackingPython -B -m takeone.motion.body_calibration
    if ($LASTEXITCODE -notin @(0, 2)) {
        throw "Cart tracking calibration failed with exit code $LASTEXITCODE."
    }
} finally {
    $env:TAKEONE_ROOT = $previousRoot
    $env:PYTHONPATH = $previousPythonPath
}
