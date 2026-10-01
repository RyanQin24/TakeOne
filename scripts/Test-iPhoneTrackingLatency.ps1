param(
    [ValidateRange(1, 10)][int]$Cycles = 3,
    [ValidateRange(3, 30)][double]$AimSeconds = 8
)

$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$config = Get-Content -LiteralPath (Join-Path $projectRoot 'configs\tracking.json') -Raw |
    ConvertFrom-Json
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
    Write-Host 'Point the mounted iPhone at this laptop display so the screen fills its view.'
    Write-Host 'A full-screen target will appear. Esc cancels. No motors or serial ports are opened.'
    & $trackingPython -B -m takeone.motion.srt_latency `
        --cycles $Cycles `
        --aim-seconds $AimSeconds
    if ($LASTEXITCODE -ne 0) {
        throw "iPhone tracking-latency test failed with exit code $LASTEXITCODE."
    }
} finally {
    $env:TAKEONE_ROOT = $previousRoot
    $env:PYTHONPATH = $previousPythonPath
}
