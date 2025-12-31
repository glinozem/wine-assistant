# Daily incremental import wrapper.
#
# Thin wrapper over:
#   python -m scripts.daily_import
#
# Modes:
#   - Auto-inbox (default): processes ONLY the newest .xlsx in InboxPath.
#   - Explicit list: pass -Files <file1> <file2> ...

[CmdletBinding()]
param(
  [Parameter(Mandatory = $false)]
  [string[]]$Files,

  [Parameter(Mandatory = $false)]
  [string]$InboxPath = "data\\inbox",

  [Parameter(Mandatory = $false)]
  [string]$ArchivePath = "data\\archive",

  [Parameter(Mandatory = $false)]
  [string]$QuarantinePath = "data\\quarantine",

  [Parameter(Mandatory = $false)]
  [string]$PythonExe = "python",

  [Parameter(Mandatory = $false)]
  [switch]$NoSnapshot,

  [Parameter(Mandatory = $false)]
  [switch]$SnapshotDryRunFirst
)

$ErrorActionPreference = "Stop"

$projectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Push-Location $projectRoot
try {
  $args = @(
    "-m", "scripts.daily_import",
    "--inbox", $InboxPath,
    "--archive", $ArchivePath,
    "--quarantine", $QuarantinePath
  )

  if ($Files -and $Files.Count -gt 0) {
    $args += "--files"
    $args += $Files
  }

  if ($NoSnapshot) {
    $args += "--no-snapshot"
  }

  if ($SnapshotDryRunFirst) {
    $args += "--snapshot-dry-run-first"
  }

  & $PythonExe @args
  exit $LASTEXITCODE
}
finally {
  Pop-Location
}
