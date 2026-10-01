param(
    [string]$Plan = '',
    [ValidateSet('windows', 'linux')][string]$Profile = 'windows',
    [double]$ApproachDegPerSecond = 25,
    [switch]$DryRun,
    [switch]$Release
)
$ErrorActionPreference = 'Stop'
$robotRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$robotPython = Join-Path $robotRoot 'lerobot\.venv\Scripts\python.exe'
if (-not $Plan) { $Plan = Join-Path $robotRoot 'data\robot-commissioning-ready.json' }

Push-Location $robotRoot
try {
    if ($Release) {
        Write-Host 'Support both arms. Turning torque off on COM9 and COM8.'
        & $robotPython -u -m takeone.motion.play --profile $Profile --release
        exit $LASTEXITCODE
    }
    $planFile = (Resolve-Path -LiteralPath $Plan).Path
    if ($DryRun) {
        # Converts the shot to encoder counts and prints them. Opens no ports.
        & $robotPython -u -m takeone.motion.play --plan $planFile --profile $Profile
        exit $LASTEXITCODE
    }
    Write-Host 'Playing the saved simulator shot: COM5 cart, COM9 phone, COM8 light.'
    Write-Host 'Both arms are read first, then eased from where they are to the shot start.'
    Write-Host 'Ctrl+C stops the cart and freezes the arms at their last goal.'
    & $robotPython -u -m takeone.motion.play `
        --plan $planFile --profile $Profile --approach-deg-s $ApproachDegPerSecond --go
    exit $LASTEXITCODE
}
finally { Pop-Location }
