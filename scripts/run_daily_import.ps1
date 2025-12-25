#requires -Version 5.1
[CmdletBinding()]
param(
  # Supplier name (e.g., "dreemwine")
  [Parameter(Mandatory=$true)]
  [string]$Supplier,

  # Optional: explicit file path (overrides auto-discovery)
  [string]$FilePath = "",

  # Optional: override as_of_date (if business date ≠ filename date)
  [string]$AsOfDate = ""
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

  # Find all .xlsx files
  $files = Get-ChildItem -Path $InboxPath -Filter "*.xlsx" -File

  if ($files.Count -eq 0) {
    throw "No .xlsx files found in $InboxPath"
  }

  # Try to find file with YYYY_MM_DD pattern and sort by date
  $filesWithDates = $files | ForEach-Object {
    if ($_.Name -match '(\d{4})_(\d{2})_(\d{2})') {
      try {
        $dateStr = "{0}-{1}-{2}" -f $Matches[1], $Matches[2], $Matches[3]
        $date = [DateTime]::ParseExact($dateStr, "yyyy-MM-dd", $null)
        [PSCustomObject]@{
          File = $_
          Date = $date
          HasDate = $true
        }
      } catch {
        [PSCustomObject]@{
          File = $_
          Date = $_.LastWriteTime
          HasDate = $false
        }
      }
    } else {
      [PSCustomObject]@{
        File = $_
        Date = $_.LastWriteTime
        HasDate = $false
      }
    }
  }

  # Sort: files with dates first (by date desc), then by LastWriteTime desc
  $sorted = $filesWithDates | Sort-Object -Property @{Expression={$_.HasDate}; Descending=$true}, Date -Descending

  return $sorted[0].File
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
    $inboxPath = Join-Path $repoRoot "data\inbox"
    if (-not (Test-Path -LiteralPath $inboxPath)) {
      throw "Inbox directory not found: $inboxPath"
    }

    Write-Host "Auto-discovering latest file in: $inboxPath"
    $file = Find-LatestPriceFile -InboxPath $inboxPath
    Write-Host "Selected file: $($file.Name)"
  }

  # Determine as_of_date
  if ($AsOfDate) {
    $asOfDateStr = $AsOfDate
    Write-Host "Using explicit as_of_date: $asOfDateStr"
  } else {
    $asOfDateStr = Extract-AsOfDate -FileName $file.Name
    Write-Host "Extracted as_of_date from filename: $asOfDateStr"
  }

  Write-Host ""
  Write-Host "Running import orchestrator..."
  Write-Host ""

  # Run import orchestrator
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
