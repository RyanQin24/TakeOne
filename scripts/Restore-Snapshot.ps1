param([Parameter(Mandatory=$true)][string]$Destination)
$ErrorActionPreference = 'Stop'
$projectRoot = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$target = [IO.Path]::GetFullPath($Destination)
if (-not $target.StartsWith($projectRoot + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw 'Restore destination must be a new directory inside the workspace.' }
if (Test-Path -LiteralPath $target) { throw 'Restore never overwrites an existing destination.' }
$snapshot = Join-Path $projectRoot 'archive\recovery\20260912T023620Z'
$manifest = Get-Content -LiteralPath (Join-Path $snapshot 'manifest.json') -Raw | ConvertFrom-Json
$archivePath = Join-Path $snapshot 'workspace.zip'
Add-Type -AssemblyName System.IO.Compression.FileSystem
$zip = [IO.Compression.ZipFile]::OpenRead($archivePath)
try {
    foreach ($entry in $zip.Entries) {
        $resolved = [IO.Path]::GetFullPath((Join-Path $target $entry.FullName))
        if (-not $resolved.StartsWith($target + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe archive path.' }
    }
} finally { $zip.Dispose() }
Expand-Archive -LiteralPath $archivePath -DestinationPath $target
foreach ($entry in $manifest.files) {
    $path = Join-Path $target $entry.path
    if ((Get-FileHash -LiteralPath $path -Algorithm SHA256).Hash.ToLowerInvariant() -ne $entry.sha256) { throw "Restored hash mismatch: $path" }
}
Write-Host "Restored and verified $($manifest.files.Count) files at $target"
