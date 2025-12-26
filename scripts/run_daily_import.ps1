#requires -Version 5.1
[CmdletBinding()]
param(
  # Supplier name (e.g., "dreemwine")
  [Parameter(Mandatory=$true)]
  [string]$Supplier,

  # Optional: explicit file path (overrides auto-discovery)
  [string]$FilePath = "",

  # Optional: override as_of_date (if business date ≠ filename date)
  [string]$AsOfDate = "",

  # Optional: override inbox path (default: data\inbox under repo root)
  [string]$InboxPath = "",

  # Dry run: select file + compute as_of_date, but do not run orchestrator
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

function Find-LatestPriceFile {
  param([string]$InboxPath)

  Write-Verbose ("Scanning inbox: {0}" -f $InboxPath)

  # Find all .xlsx files (exclude Excel temporary lock files: "~$*.xlsx")
  $files = @(
    Get-ChildItem -Path $InboxPath -Filter "*.xlsx" -File |
      Where-Object { $_.Name -notmatch '^\~\$' }
  )

  if (-not $files -or $files.Count -eq 0) {
    throw "No .xlsx files found in $InboxPath (after excluding ~`$*.xlsx temp files)."
  }

  # Try to find file with YYYY_MM_DD pattern and sort by parsed date
  $filesWithDates = $files | ForEach-Object {
    if ($_.Name -match '(\d{4})_(\d{2})_(\d{2})') {
      try {
        $dateStr = "{0}-{1}-{2}" -f $Matches[1], $Matches[2], $Matches[3]
        $date = [DateTime]::ParseExact($dateStr, "yyyy-MM-dd", $null)
        [PSCustomObject]@{
          File    = $_
          Date    = $date
          HasDate = $true
        }
      } catch {
        [PSCustomObject]@{
          File    = $_
          Date    = $_.LastWriteTime
          HasDate = $false
        }
      }
    } else {
      [PSCustomObject]@{
        File    = $_
        Date    = $_.LastWriteTime
        HasDate = $false
      }
    }
  }

  # Sort: files with parsed dates first (by date desc), then by LastWriteTime desc
  $sorted = $filesWithDates | Sort-Object -Property @{Expression={$_.HasDate}; Descending=$true}, Date -Descending

  # Verbose diagnostics: top candidates
  Write-Verbose "Top candidates (sorted):"
  $top = $sorted | Select-Object -First 5
  $i = 1
  foreach ($c in $top) {
    $f = $c.File
    $dateLabel = if ($c.HasDate) { $c.Date.ToString("yyyy-MM-dd") } else { "(no YYYY_MM_DD in name)" }
    Write-Verbose (" {0}) {1} | parsed_date={2} | last_write={3}" -f $i, $f.Name, $dateLabel, $f.LastWriteTime.ToString("yyyy-MM-dd HH:mm:ss"))
    $i++
  }

  $chosen = $sorted[0].File
  Write-Verbose ("Chosen file: {0}" -f $chosen.FullName)
  return $chosen
}

function Extract-AsOfDate {
  param([string]$FileName)

  # Extract YYYY_MM_DD from filename
  if ($FileName -match '(\d{4})_(\d{2})_(\d{2})') {
    $dateStr = "{0}-{1}-{2}" -f $Matches[1], $Matches[2], $Matches[3]
    try {
      [DateTime]::ParseExact($dateStr, "yyyy-MM-dd", $null) | Out-Null
      return $dateStr
    } catch {
      Write-Warning "Date in filename ($dateStr) is invalid, using current date"
    }
  }

  # Fallback to current date
  return Get-Date -Format "yyyy-MM-dd"
}

try {
  $repoRoot = Resolve-RepoRoot
  Set-Location -LiteralPath $repoRoot
  $python = Resolve-Python

  Write-Host "=== Wine Assistant - Daily Import ==="
  Write-Host ("Repo root:  {0}" -f $repoRoot)
  Write-Host ("Supplier:   {0}" -f $Supplier)
  Write-Host ""

  # Determine file path
  if ($FilePath) {
    if (-not (Test-Path -LiteralPath $FilePath)) {
      throw "Specified file not found: $FilePath"
    }
    $file = Get-Item -LiteralPath $FilePath
    Write-Host "Using explicit file: $($file.FullName)"
  } else {
    $inboxPath = if ($InboxPath) { $InboxPath } else { (Join-Path $repoRoot "data\inbox") }
    if (-not (Test-Path -LiteralPath $inboxPath)) {
      throw "Inbox directory not found: $inboxPath"
    }

    Write-Host "Auto-discovering latest file in: $inboxPath"
    $file = Find-LatestPriceFile -InboxPath $inboxPath
    Write-Host "Selected file: $($file.Name)"
    Write-Verbose ("Selected full path: {0}" -f $file.FullName)
  }

  # Determine as_of_date
  if ($AsOfDate) {
    $asOfDateStr = $AsOfDate
    Write-Host "Using explicit as_of_date: $asOfDateStr"
  } else {
    $asOfDateStr = Extract-AsOfDate -FileName $file.Name
    Write-Host "Extracted as_of_date from filename: $asOfDateStr"
    Write-Verbose ("as_of_date source: filename (override via -AsOfDate to change)")
  }

  if ($WhatIf) {
  Write-Host ""
  Write-Host "WHATIF: orchestrator will NOT be executed."
  Write-Host ("WHATIF: selected file = {0}" -f $file.FullName)
  Write-Host ("WHATIF: as_of_date     = {0}" -f $asOfDateStr)
  exit 0
  }

  Write-Host ""
  Write-Host "Running import orchestrator..."
  Write-Host ""

  & $python -m scripts.run_import_orchestrator `
    --supplier $Supplier `
    --file $file.FullName `
    --as-of-date $asOfDateStr `
    --import-fn "scripts.import_targets.run_daily_adapter:import_with_run_daily"

  if ($LASTEXITCODE -ne 0) {
    throw "Import orchestrator failed with exit code $LASTEXITCODE"
  }

  Write-Host ""
  Write-Host "Daily import completed successfully."
  exit 0
}
catch {
  Write-Error $_
  exit 1
}
