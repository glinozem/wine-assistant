<#
DR smoke test for Wine Assistant (local "remote-like" backups using MinIO).

Modes:
  -Mode truncate    : TRUNCATE key tables -> restore from latest remote backup (MinIO).
  -Mode dropvolume  : docker compose down -v (base stack) -> up -> restore from latest remote backup.

Notes:
- This script assumes:
    * Base stack uses docker-compose.yml and exposes API at http://localhost:18000
    * Storage stack uses docker-compose.storage.yml and exposes MinIO at http://localhost:19000
    * Makefile targets exist: storage-up, backup, backups-list-remote, restore-remote-latest
- It is intended for LOCAL DEV ONLY.
#>

[CmdletBinding()]
param(
  [ValidateSet("truncate","dropvolume")]
  [string]$Mode = "truncate",

  # How many latest backups to keep (both locally in ./backups and remotely in MinIO)
  [int]$BackupKeep = 2,

  # Health/ready endpoints (no API key required)
  [string]$ApiReadyUrl = "http://localhost:18000/ready",
  [string]$MinioLiveUrl = "http://localhost:19000/minio/health/live",

  # Optional: if you use a non-default docker compose binary name
  [string]$DockerCompose = "docker compose",

  # Suppress "Found orphan containers" warnings when using different compose file sets
  # (e.g. running base + observability + storage as separate compose invocations).
  [bool]$ComposeIgnoreOrphans = $true,

  # Compose file sets. Adjust if your file names differ.
  [string[]]$BaseComposeFiles = @("docker-compose.yml"),
  [string[]]$StorageComposeFiles = @("docker-compose.yml","docker-compose.storage.yml"),

  # If specified, stops promtail (observability stack) before the run and starts it back at the end.
  # Use as a switch:  -ManagePromtail
  [switch]$ManagePromtail,
  [string[]]$ObservabilityComposeFiles = @("docker-compose.yml","docker-compose.storage.yml","docker-compose.observability.yml"),
  [string]$PromtailService = "promtail",

  [string]$EventsLog = ("logs/backup-dr/dr_smoke_{0}_pid{1}.jsonl" -f (Get-Date -Format "yyyyMMdd_HHmmss"), $PID)
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# Keep the DR smoke events log file opened for the whole run.
# This avoids intermittent "file is being used by another process" errors
# when a log shipper (e.g., promtail) starts tailing the newly created file.
$script:__EventsStream = $null
$script:__EventsWriter = $null

# Repo root (assumes this script is located in <repo>/scripts/)
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

# --- docker compose wrappers --------------------------------------------------
# $DockerCompose may contain spaces (e.g. "docker compose"); split it into tokens.
$__dcTokens = ($DockerCompose -split '\s+') | Where-Object { $_ -and $_.Trim() }
if ($__dcTokens.Count -lt 1) {
  throw "DockerCompose is empty; expected something like 'docker compose'."
}
$__dcExe = $__dcTokens[0]
$__dcPrefix = @()
if ($__dcTokens.Count -gt 1) {
  $__dcPrefix = $__dcTokens[1..($__dcTokens.Count - 1)]
}

function Invoke-DC {
  & $__dcExe @__dcPrefix @args
}


function Invoke-DCObs {
    # Invoke docker compose using ObservabilityComposeFiles (for promtail management)
    param([Parameter(ValueFromRemainingArguments=$true)][string[]]$Args)
    Push-Location $repoRoot
    try {
        & $__dcExe @__dcPrefix @__obsComposeArgs @Args
    }
    finally {
        Pop-Location
    }
}

function Invoke-WithoutComposeIgnoreOrphans([scriptblock]$Body) {
    $prev = $env:COMPOSE_IGNORE_ORPHANS
    Remove-Item Env:COMPOSE_IGNORE_ORPHANS -ErrorAction SilentlyContinue | Out-Null
    try { & $Body } finally {
        if ($null -ne $prev) { $env:COMPOSE_IGNORE_ORPHANS = $prev }
    }
}

function Get-ContainerRunning([string]$containerId) {
  if (-not $containerId) { return $false }
  try {
    $out = docker inspect -f '{{.State.Running}}' $containerId 2>$null
    return ($out -and $out.Trim().ToLower() -eq 'true')
  } catch {
    return $false
  }
}

function Obs-ServiceExists([string]$serviceName) {
  try {
    $services = (& $__dcExe @__dcPrefix @__obsComposeArgs config --services) 2>$null
    return ($services -and ($services -contains $serviceName))
  } catch {
    return $false
  }
}

function Get-ObsContainerId([string]$serviceName) {
  try {
    $cid = (& $__dcExe @__dcPrefix @__obsComposeArgs ps -q $serviceName) 2>$null
    if ($cid) { return ($cid | Select-Object -First 1) }
  } catch {}
  return $null
}

function Maybe-ManagePromtailStop() {
  if (-not $ManagePromtail) { return $false }

  if (-not (Obs-ServiceExists $PromtailService)) {
    Write-Host ("INFO: promtail service '{0}' not found; skip stop" -f $PromtailService)
    return $false
  }

  $cid = Get-ObsContainerId $PromtailService
  if (-not $cid) {
    Write-Host ("INFO: promtail container for service '{0}' not present; skip stop" -f $PromtailService)
    return $false
  }

  if (-not (Get-ContainerRunning $cid)) {
    Write-Host "INFO: promtail container is not running; skip stop"
    return $false
  }

  Write-Host ("INFO: stopping promtail ({0}) to avoid log file locking..." -f $PromtailService)
  try { & $__dcExe @__dcPrefix @__obsComposeArgs stop $PromtailService | Out-Null } catch {}
  return $true
}

function Maybe-ManagePromtailStart([bool]$wasRunning) {
  if (-not $ManagePromtail) { return }
  if (-not $wasRunning) { return }

  if (-not (Obs-ServiceExists $PromtailService)) {
    Write-Host ("INFO: promtail service '{0}' not found; skip start" -f $PromtailService)
    return
  }

  Write-Host ("INFO: starting promtail ({0}) back..." -f $PromtailService)
  try { & $__dcExe @__dcPrefix @__obsComposeArgs up -d $PromtailService | Out-Null } catch {}
}

function Compose-FileArgs([string[]]$Files) {
  $a = @()
  foreach ($f in $Files) { $a += @("-f", $f) }
  return $a
}

$__baseComposeArgs = Compose-FileArgs $BaseComposeFiles
$__storageComposeArgs = Compose-FileArgs $StorageComposeFiles

$__obsComposeArgs = Compose-FileArgs $ObservabilityComposeFiles
# Reduce noise when you run different compose file sets (observability/storage).
$__prevIgnoreOrphans = $env:COMPOSE_IGNORE_ORPHANS
if ($ComposeIgnoreOrphans) {
  $env:COMPOSE_IGNORE_ORPHANS = "1"
}


function Open-EventsWriter {
  if ($script:__EventsWriter) { return }

  $dir = Split-Path -Parent $EventsLog
  if ($dir -and -not (Test-Path $dir)) {
    New-Item -ItemType Directory -Force -Path $dir | Out-Null
  }

  # Open the log file once and keep it open for the whole run.
  # This prevents "file is being used by another process" when a log shipper
  # opens the file with restrictive sharing.
  $script:__EventsStream = [System.IO.File]::Open(
    $EventsLog,
    [System.IO.FileMode]::Append,
    [System.IO.FileAccess]::Write,
    [System.IO.FileShare]::ReadWrite
  )

  $utf8NoBom = New-Object System.Text.UTF8Encoding($false)
  $script:__EventsWriter = New-Object System.IO.StreamWriter($script:__EventsStream, $utf8NoBom)
  $script:__EventsWriter.AutoFlush = $true
}

function Close-EventsWriter {
  try {
    if ($script:__EventsWriter) { $script:__EventsWriter.Dispose() }
  } finally {
    $script:__EventsWriter = $null
    if ($script:__EventsStream) { $script:__EventsStream.Dispose() }
    $script:__EventsStream = $null
  }
}

function Write-EventJson {
  param(
    [Parameter(Mandatory=$true)][string]$Event,
    [hashtable]$Fields = @{},
    [ValidateSet("info","warning","error")][string]$Level = "info",
    [string]$Service = "dr_smoke"
  )

  $now = (Get-Date).ToUniversalTime()
  $dto = [DateTimeOffset]$now

  $obj = [ordered]@{
    ts      = $now.ToString("o")
    ts_unix = [int]$dto.ToUnixTimeSeconds()
    level   = $Level
    service = $Service
    event   = $Event
  }
  foreach ($k in $Fields.Keys) { $obj[$k] = $Fields[$k] }

  $json = ($obj | ConvertTo-Json -Compress -Depth 8)

  try {
    Open-EventsWriter
    $script:__EventsWriter.WriteLine($json)
  } catch {
    Write-Warning "Failed to write event log: $($_.Exception.Message)"
  }

  Write-Host $json
}

function Wait-ReadyJson([string]$url, [string]$name, [int]$tries=60, [int]$sleepSec=1) {
  for ($i=1; $i -le $tries; $i++) {
    try {
      $resp = Invoke-RestMethod $url
      if ($resp -and $resp.status -eq "ready") {
        Write-Host "OK: $name"
        return
      }
    } catch {
      # ignore
    }
    Start-Sleep -Seconds $sleepSec
  }
  throw "Timeout waiting for $name ($url)"
}


function Assert-LastExitCode([string]$context) {
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed ($context). ExitCode=$LASTEXITCODE"
  }
}

function Invoke-Step([string]$title, [scriptblock]$cmd) {
  Write-Host ">> $title"
  # IMPORTANT: external/native commands set $LASTEXITCODE; reset it to avoid false positives
  $global:LASTEXITCODE = 0
  & $cmd
  Assert-LastExitCode $title
}

function Wait-HttpOk([string]$url, [string]$name, [int]$tries=60, [int]$sleepSec=1) {
  for ($i=1; $i -le $tries; $i++) {
    try {
      Invoke-RestMethod $url | Out-Null
      Write-Host "OK: $name"
      return
    } catch {
      Start-Sleep -Seconds $sleepSec
    }
  }
  throw "Timeout waiting for $name ($url)"
}

function Get-DbScalar([string]$sql) {
  # -t -A => tuples-only + unaligned output, easy to parse as int
  $global:LASTEXITCODE = 0
  $out = Invoke-DC @__baseComposeArgs exec -T db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -t -A -c $sql
  Assert-LastExitCode "psql: $sql"
  $val = $out.Trim()
  if ($val -match '^\d+$') { return [int]$val }
  throw "Unexpected psql output for [$sql]: [$out]"
}

function Get-DbCounts() {
  return @{
    products        = Get-DbScalar "select count(*) from products;"
    product_prices  = Get-DbScalar "select count(*) from product_prices;"
    inventory       = Get-DbScalar "select count(*) from inventory;"
    bad_rows        = Get-DbScalar "select count(*) from products where price_list_rub is not null and price_final_rub is null;"
  }
}

function Print-DbCounts([string]$label, $counts) {
  Write-Host "=== $label ==="
  Write-Host ("products       : {0}" -f $counts.products)
  Write-Host ("product_prices : {0}" -f $counts.product_prices)
  Write-Host ("inventory      : {0}" -f $counts.inventory)
  Write-Host ("bad_rows       : {0}" -f $counts.bad_rows)
}

Write-Host "=== DR smoke test ==="
Write-Host ("Mode       : {0}" -f $Mode)
Write-Host ("BackupKeep : {0}" -f $BackupKeep)
Write-Host ("ManagePromtail : {0}" -f ([bool]$ManagePromtail))
Write-Host ("EventsLog  : {0}" -f $EventsLog)
Write-Host ""

$__promtailWasRunning = $false
try {
    $__promtailWasRunning = Maybe-ManagePromtailStop

    Write-EventJson -Event "dr_smoke_started" -Fields @{ mode=$Mode; backup_keep=$BackupKeep }

try {

# 0) Base stack
Invoke-Step "docker compose config" { Invoke-DC @__baseComposeArgs config | Out-Null }
Invoke-Step "docker compose up -d --build" { Invoke-DC @__baseComposeArgs up -d --build }
Wait-ReadyJson $ApiReadyUrl "API ready"

# 0b) Storage stack (MinIO)
Invoke-Step "docker compose (storage) config" { Invoke-DC @__storageComposeArgs config | Out-Null }
Invoke-Step "make storage-up" { make storage-up }
Wait-HttpOk $MinioLiveUrl "MinIO live"
Invoke-Step "MinIO bucket access (list)" { make backups-list-remote }

# 1) Fresh backup -> upload to MinIO -> prune keep=N
Invoke-Step ("make backup BACKUP_KEEP={0}" -f $BackupKeep) { make backup ("BACKUP_KEEP={0}" -f $BackupKeep) }
Invoke-Step "make backups-list-remote" { make backups-list-remote }

# 2) Control counts BEFORE
$before = Get-DbCounts
Print-DbCounts "Control counts (before)" $before
if ($before.bad_rows -ne 0) { throw "Data quality gate failed (before): bad_rows != 0" }

# 3) Simulate disaster
Write-Host ""
Write-Host "=== Simulating disaster ==="
if ($Mode -eq "truncate") {
  Invoke-Step "TRUNCATE TABLE inventory, product_prices, products" {
    Invoke-DC @__baseComposeArgs exec -T db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE inventory, product_prices, products RESTART IDENTITY CASCADE;"
  }
} else {
  Invoke-Step "docker compose down -v --remove-orphans" { Invoke-WithoutComposeIgnoreOrphans { Invoke-DC @__baseComposeArgs down -v --remove-orphans } }
  Invoke-Step "docker compose up -d --build" { Invoke-DC @__baseComposeArgs up -d --build }
  Wait-ReadyJson $ApiReadyUrl "API ready (recreate)"

  Invoke-Step "make storage-up" { make storage-up }
  Wait-HttpOk $MinioLiveUrl "MinIO live (recreate)"
}

# 4) Control counts AFTER disaster (informational; should be 0/0/0 after truncate)
$after_disaster = Get-DbCounts
Print-DbCounts "Control counts (after disaster)" $after_disaster

# 5) Restore from remote latest
Write-Host ""
Write-Host "=== Restoring from remote latest (MinIO) ==="
Invoke-Step "make restore-remote-latest" { make restore-remote-latest }
Wait-ReadyJson $ApiReadyUrl "API ready after restore"

# 6) Control counts AFTER restore + verify equals BEFORE
$after = Get-DbCounts
Print-DbCounts "Control counts (after restore)" $after

$diffs = @()
foreach ($k in @("products","product_prices","inventory","bad_rows")) {
  if ($before.$k -ne $after.$k) { $diffs += ("{0}: before={1} after={2}" -f $k, $before.$k, $after.$k) }
}
if ($diffs.Count -gt 0) {
  throw ("Restore verification failed. Diffs:`n- " + ($diffs -join "`n- "))
}

Write-EventJson -Event "dr_smoke_completed" -Fields @{ mode=$Mode; backup_keep=$BackupKeep }

Write-Host ""
Write-Host "DONE: DR smoke test completed successfully."
}
catch {
  Write-EventJson -Event "dr_smoke_failed" -Level "error" -Fields @{ mode=$Mode; backup_keep=$BackupKeep; error=$_.Exception.Message }
  throw
}
finally {
  if ($ComposeIgnoreOrphans) {
    if ($null -eq $__prevIgnoreOrphans) {
      Remove-Item env:COMPOSE_IGNORE_ORPHANS -ErrorAction SilentlyContinue
    } else {
      $env:COMPOSE_IGNORE_ORPHANS = $__prevIgnoreOrphans
    }
  }
}
}
finally {
    Close-EventsWriter
    Maybe-ManagePromtailStart -wasRunning $__promtailWasRunning
}
