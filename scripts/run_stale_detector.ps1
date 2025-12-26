#requires -Version 5.1
[CmdletBinding()]
param(
  # If a run is "running" longer than this threshold — it is considered stale.
  [int]$RunningMinutes = 120,

  # If a run is "pending" longer than this threshold — it is considered stale.
  [int]$PendingMinutes = 15,

  # Dry run: show what would be executed, but do not execute anything.
  [switch]$WhatIf
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Resolve-RepoRoot {
  $scriptDir = Split-Path -Parent $PSCommandPath
  return (Resolve-Path (Join-Path $scriptDir "..")).Path
}

function Resolve-Python {
  $repoRoot = Resolve-RepoRoot
  $venvPy = Join-Path $repoRoot ".venv\Scripts\python.exe"
  if (Test-Path -LiteralPath $venvPy) {
    return $venvPy
  }
  return "python"
}

function Format-LogArg {
  param([object]$Value)
  if ($null -eq $Value) { return '""' }

  $s = [string]$Value
  if ($s -match '[\s"]') {
    return '"' + ($s -replace '"', '\"') + '"'
  }
  return $s
}

try {
  $repoRoot = Resolve-RepoRoot
  Set-Location -LiteralPath $repoRoot
  $python = Resolve-Python

  Write-Host "=== Wine Assistant - Stale Import Runs Detector ==="
  Write-Host ("Repo root:       {0}" -f $repoRoot)
  Write-Host ("RunningMinutes:  {0}" -f $RunningMinutes)
  Write-Host ("PendingMinutes:  {0}" -f $PendingMinutes)
  Write-Host ""

  Write-Verbose ("PowerShell: {0}" -f $PSVersionTable.PSVersion)
  Write-Verbose ("Python: {0}" -f $python)

  $pyArgs = @(
    "-m", "scripts.mark_stale_import_runs",
    "--running-minutes", $RunningMinutes,
    "--pending-minutes", $PendingMinutes
  )

  $argStr = (($pyArgs | ForEach-Object { Format-LogArg $_ }) -join " ")
  $cmdStr = ('"{0}" {1}' -f $python, $argStr)

  Write-Verbose ("Command: {0}" -f $cmdStr)

  if ($WhatIf) {
    Write-Host "WHATIF: stale detector will NOT be executed."
    Write-Host ("WHATIF: command        = {0}" -f $cmdStr)
    Write-Host ("WHATIF: RunningMinutes = {0}" -f $RunningMinutes)
    Write-Host ("WHATIF: PendingMinutes = {0}" -f $PendingMinutes)
    exit 0
  }

  Write-Host "Running stale detector..."
  Write-Host ""

  & $python @pyArgs

  if ($LASTEXITCODE -ne 0) {
    throw "Stale detector exited with code $LASTEXITCODE."
  }

  Write-Host ""
  Write-Host "Stale detector completed successfully."
  exit 0
}
catch {
  Write-Host ""
  Write-Error ("Stale detector failed: {0}" -f $_.Exception.Message)
  Write-Verbose ("ErrorRecord: {0}" -f ($_ | Out-String))
  exit 1
}
