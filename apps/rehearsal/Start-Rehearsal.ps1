param([int]$Port = 8766)
$ErrorActionPreference = 'Stop'
& (Join-Path $PSScriptRoot '..\..\scripts\TakeOne.ps1') -Command simulator -Port $Port
