#requires -Version 5.1
[CmdletBinding()]
param(
  # If a run is "running" longer than this threshold — it is considered stale.
  [int]$RunningMinutes = 120,

  # If a run is "pending" longer than this threshold — it is considered stale.
  [int]$PendingMinutes = 15
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

try {
  $repoRoot = Resolve-RepoRoot
  Set-Location -LiteralPath $repoRoot
  $python = Resolve-Python

  Write-Host "=== Stale Import Detector ==="
  Write-Host ("Repo root:        {0}" -f $repoRoot)
  Write-Host ("RunningMinutes:   {0}" -f $RunningMinutes)
  Write-Host ("PendingMinutes:   {0}" -f $PendingMinutes)
  Write-Host ""

  & $python -m scripts.mark_stale_import_runs `
    --running-minutes $RunningMinutes `
    --pending-minutes $PendingMinutes

  if ($LASTEXITCODE -ne 0) {
    throw "Stale detector exited with code $LASTEXITCODE."
  }

  Write-Host ""
  Write-Host "Stale detector completed successfully."
  exit 0
}
catch {
  Write-Error $_
  exit 1
}
