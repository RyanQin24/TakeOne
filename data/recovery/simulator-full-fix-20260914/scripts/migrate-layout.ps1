$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$recovery = Join-Path $workspace 'archive\recovery\20260912T023620Z\manifest.json'
if (-not (Test-Path -LiteralPath $recovery)) { throw 'Verified recovery snapshot required.' }
if (-not (Get-Content -LiteralPath $recovery -Raw | ConvertFrom-Json).verified) { throw 'Recovery unverified.' }
$moves = [System.Collections.Generic.List[object]]::new()
function Move-WorkspaceItem([string]$From, [string]$To, [string]$Reason) {
    $source = [IO.Path]::GetFullPath((Join-Path $workspace $From))
    $destination = [IO.Path]::GetFullPath((Join-Path $workspace $To))
    foreach ($target in @($source,$destination)) {
        if (-not $target.StartsWith($workspace + [IO.Path]::DirectorySeparatorChar, [StringComparison]::OrdinalIgnoreCase)) { throw "Outside workspace: $target" }
    }
    if (-not (Test-Path -LiteralPath $source)) { throw "Missing source: $source" }
    if (Test-Path -LiteralPath $destination) { throw "Destination exists: $destination" }
    New-Item -ItemType Directory -Path (Split-Path $destination) -Force | Out-Null
    Move-Item -LiteralPath $source -Destination $destination
    $moves.Add([ordered]@{from=$From;to=$To;reason=$Reason;operation='move'})
    $moves | ConvertTo-Json -Depth 5 | Set-Content -LiteralPath (Join-Path $workspace 'docs\migration-manifest.json') -Encoding utf8
}
Move-WorkspaceItem 'TakeOne-main\TakeOne-main\rehearsal-mvp' 'apps\rehearsal' 'Thin simulator application and existing playback tests'
Move-WorkspaceItem 'TakeOne-main\TakeOne-main\TAKE-ONE-Simulation-Evidence\takeone_validation' 'assets\robots\reference' 'Preserve original evidence, upstream geometry and license together'
Move-WorkspaceItem 'TakeOne-main' 'archive\imports\TakeOne-main' 'Historical enclosing documentation and original distribution'
Move-WorkspaceItem 'TakeOne-main.zip' 'archive\imports\TakeOne-main.zip' 'Original distribution retained for recovery'
Move-WorkspaceItem 'lerobot-upload.tar.gz' 'archive\imports\lerobot-upload.tar.gz' 'Original distribution retained for recovery'
Move-WorkspaceItem 'ASTRA-REORGANIZATION-PROMPT.md' 'docs\requests\ASTRA-REORGANIZATION-PROMPT.md' 'Original migration brief'
Move-WorkspaceItem 'apps\rehearsal\engine.py' 'packages\takeone\planning\compiler.py' 'Canonical product planner'
Move-WorkspaceItem 'apps\rehearsal\drive.py' 'packages\takeone\simulation\drive.py' 'Conditional drive prediction separate from hardware'
Move-WorkspaceItem 'apps\rehearsal\build_rehearsal_model.py' 'packages\takeone\simulation\model.py' 'Canonical model builder'
foreach ($name in @('rig_tall.xml','rig_panel.xml','rig_tube.xml','assets')) {
    Move-WorkspaceItem "apps\rehearsal\$name" "assets\robots\takeone\$name" 'Canonical robot model and generated attachments'
}
Move-WorkspaceItem 'apps\rehearsal\dist.zip' 'archive\imports\rehearsal-dist.zip' 'Preserve prior UI distribution; not live application source'
Move-WorkspaceItem 'apps\rehearsal\server-out.log' 'data\logs\before-migration-out.log' 'Stopped server log'
Move-WorkspaceItem 'apps\rehearsal\server-error.log' 'data\logs\before-migration-error.log' 'Stopped server log'
