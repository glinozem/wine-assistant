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
  [string]$DockerCompose = "docker compose"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

function Assert-LastExitCode([string]$context) {
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed ($context). ExitCode=$LASTEXITCODE"
  }
}

function Invoke-Step([string]$title, [scriptblock]$cmd) {
  Write-Host ">> $title"
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
  $out = docker compose exec -T db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -t -A -c $sql
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
Write-Host ""

# 0) Base stack
Invoke-Step "docker compose config" { docker compose config | Out-Null }
Invoke-Step "docker compose up -d --build" { docker compose up -d --build }
Wait-HttpOk $ApiReadyUrl "API ready"

# 0b) Storage stack (MinIO)
Invoke-Step "docker compose (storage) config" { docker compose -f docker-compose.yml -f docker-compose.storage.yml config | Out-Null }
Invoke-Step "make storage-up" { make storage-up }
Wait-HttpOk $MinioLiveUrl "MinIO live"

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
    docker compose exec db psql -U postgres -d wine_db -v ON_ERROR_STOP=1 -c "TRUNCATE TABLE inventory, product_prices, products RESTART IDENTITY CASCADE;"
  }
} else {
  Invoke-Step "docker compose down -v --remove-orphans" { docker compose down -v --remove-orphans }
  Invoke-Step "docker compose up -d --build" { docker compose up -d --build }
  Wait-HttpOk $ApiReadyUrl "API ready (recreate)"

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
Wait-HttpOk $ApiReadyUrl "API ready after restore"

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

Write-Host ""
Write-Host "DONE: DR smoke test completed successfully."
