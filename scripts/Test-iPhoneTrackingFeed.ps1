param(
    [ValidateRange(1, 60)][double]$Seconds = 5
)

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
    & $trackingPython -B -m takeone.motion.srt_probe --seconds $Seconds
    if ($LASTEXITCODE -ne 0) {
        throw "iPhone tracking-feed probe failed with exit code $LASTEXITCODE."
    }
} finally {
    $env:TAKEONE_ROOT = $previousRoot
    $env:PYTHONPATH = $previousPythonPath
}
