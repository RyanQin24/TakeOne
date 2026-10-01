param(
    [ValidateSet('simulator','diagnose','dry-run','test')][string]$Command = 'diagnose',
    [ValidateSet('windows','linux')][string]$Profile = 'windows',
    [int]$Port = 8766,
    [string]$VerificationOutputDirectory
)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$pythonPath = Join-Path $projectRoot '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) { throw 'Run scripts\Setup.ps1 first.' }
if ($Command -eq 'test') {
    if ($VerificationOutputDirectory) {
        & $pythonPath (Join-Path $projectRoot 'scripts\verify.py') --output-dir $VerificationOutputDirectory
    } else {
        & $pythonPath (Join-Path $projectRoot 'scripts\verify.py')
    }
} elseif ($Command -eq 'simulator') {
    & $pythonPath -m takeone.cli simulator --port $Port
} elseif ($Command -eq 'diagnose') {
    & $pythonPath -m takeone.cli diagnose --profile $Profile
} else {
    & $pythonPath -m takeone.cli dry-run
}
if ($LASTEXITCODE -ne 0) { throw "TakeOne command failed with exit code $LASTEXITCODE" }
