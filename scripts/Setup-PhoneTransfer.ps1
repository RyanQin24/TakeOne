param()
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$environmentPath = Join-Path $projectRoot '.runtime\phone-transfer'
$transferPython = Join-Path $environmentPath 'Scripts\python.exe'
if (-not (Test-Path -LiteralPath $transferPython)) {
    & uv venv $environmentPath --python (Join-Path $projectRoot '.venv\Scripts\python.exe')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the USB transfer environment.' }
}
# This lock contains the USB/AFC service dependencies only. Firmware restore,
# image decoding and developer services are not used by the transfer worker.
& uv pip install --python $transferPython --no-deps -r (Join-Path $projectRoot 'requirements-phone-transfer.lock.txt')
if ($LASTEXITCODE -ne 0) { throw 'Could not install USB transfer dependencies.' }
& $transferPython (Join-Path $PSScriptRoot 'phone_transfer.py') --configure
if ($LASTEXITCODE -ne 0) { throw 'Connect an unlocked iPhone and complete Trust in Apple Devices, then retry.' }
Write-Output 'USB saving is configured. Start or restart TakeOne to run the background copier.'
