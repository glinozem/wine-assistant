param(
  [switch]$StartDb = $false,
  [int]$ReadyTimeoutSec = 60
)

$ErrorActionPreference = "Stop"

function Info($m){ Write-Host $m -ForegroundColor Cyan }
function Warn($m){ Write-Host $m -ForegroundColor Yellow }
function Err ($m){ Write-Host $m -ForegroundColor Red }

# Defaults (match docker-compose)
if (-not $env:PGUSER)     { $env:PGUSER     = "postgres" }
if (-not $env:PGPASSWORD) { $env:PGPASSWORD = "dev_local_pw" } # not used inside container
if (-not $env:PGDATABASE) { $env:PGDATABASE = "wine_db" }

function HasCmd($name){ try { [bool](Get-Command $name -ErrorAction Stop) } catch { $false } }

if (-not (HasCmd "docker")) { Err "Docker is required."; exit 1 }

if ($StartDb) {
  Info "Starting db container..."
  docker compose up -d db | Out-Null
}

function Get-DbCid {
  try {
    $cid = (docker compose ps -q db).Trim()
    if ($cid) { return $cid } else { return $null }
  } catch { return $null }
}

$cid = Get-DbCid
if (-not $cid) { Err "Container 'db' not found. Run: docker compose up -d db"; exit 1 }

function Wait-Pg([int]$timeoutSec){
  $deadline = (Get-Date).AddSeconds($timeoutSec)
  Info "Waiting for Postgres readiness..."
  while ((Get-Date) -lt $deadline) {
    $ok = $false
    try {
      docker exec -i $cid pg_isready -U $env:PGUSER -d $env:PGDATABASE -h localhost -p 5432 | Out-Null
      if ($LASTEXITCODE -eq 0) { $ok = $true }
    } catch { $ok = $false }
    if ($ok) { return $true }
    Start-Sleep -Seconds 1
  }
  return $false
}

if (-not (Wait-Pg -timeoutSec $ReadyTimeoutSec)) {
  Err "Postgres did not become ready within $ReadyTimeoutSec seconds."
  exit 1
}

# Execute single SQL command (-c)
function ExecSql([string]$sql){
  docker compose exec -T db psql -U $env:PGUSER -d $env:PGDATABASE -v ON_ERROR_STOP=1 -c $sql | Out-Null
}

# Execute SQL file: copy into container then psql -f
function ExecSqlFile([string]$file){
  $leaf = [System.IO.Path]::GetFileName($file)
  $dst = "/tmp/$leaf"
  # IMPORTANT: use $($cid) to avoid scope parsing of colon
  docker cp $file "$($cid):$dst" | Out-Null
  try {
    docker exec -i $cid psql -U $env:PGUSER -d $env:PGDATABASE -v ON_ERROR_STOP=1 -f $dst
  } finally {
    docker exec -i $cid rm -f $dst | Out-Null
  }
}

# Bootstrap: extensions + migrations registry
ExecSql 'CREATE EXTENSION IF NOT EXISTS pg_trgm;'
ExecSql 'CREATE EXTENSION IF NOT EXISTS vector;'
ExecSql 'CREATE EXTENSION IF NOT EXISTS pgcrypto;'
ExecSql 'CREATE TABLE IF NOT EXISTS public.schema_migrations (filename text PRIMARY KEY, sha256 char(64), applied_at timestamptz NOT NULL DEFAULT now());'

# Locate migrations
$scriptRoot    = Split-Path -Parent $MyInvocation.MyCommand.Path
$migrationsDir = Join-Path $scriptRoot "migrations"
if (-not (Test-Path $migrationsDir)) { Err ("Migrations dir not found: " + $migrationsDir); exit 1 }

$files = Get-ChildItem $migrationsDir -Filter *.sql | Sort-Object Name
if (-not $files) { Warn "No *.sql in db/migrations"; exit 0 }

# Read stored sha256 for a migration
function GetSha([string]$fname){
  $q = "SELECT sha256 FROM public.schema_migrations WHERE filename = '$fname' LIMIT 1;"
  $out = docker compose exec -T db psql -U $env:PGUSER -d $env:PGDATABASE -At -c $q 2>$null
  return ($out | Out-String).Trim()
}

foreach ($f in $files) {
  $name = $f.Name
  $full = $f.FullName
  $hash = (Get-FileHash -Algorithm SHA256 $full).Hash.ToLower()

  $dbSha = GetSha $name
  if ($dbSha) {
    if ($dbSha -eq $hash) {
      Info (">> SKIP " + $name + " (already applied)")
      continue
    } else {
      Err (">> Migration " + $name + " recorded with a different checksum!")
      Err ("   DB : " + $dbSha)
      Err ("   FS : " + $hash)
      exit 1
    }
  }

  Info (">> Applying " + $name)
  ExecSqlFile $full
  ExecSql ("INSERT INTO public.schema_migrations(filename, sha256) VALUES ('$name', '$hash') ON CONFLICT (filename) DO NOTHING;")
}

# Helper view
ExecSql 'CREATE OR REPLACE VIEW public.schema_migrations_recent AS SELECT split_part(filename, ''_'', 1) AS version, filename, sha256 AS checksum, applied_at FROM public.schema_migrations ORDER BY applied_at DESC;'

# Summary
Info ""
Info "=== Recent migrations ==="
docker compose exec -T db psql -U $env:PGUSER -d $env:PGDATABASE -c "SELECT version, filename, checksum, applied_at, (applied_at AT TIME ZONE 'Europe/Moscow') AS applied_msk FROM public.schema_migrations_recent LIMIT 10;"
Info "All migrations applied."
