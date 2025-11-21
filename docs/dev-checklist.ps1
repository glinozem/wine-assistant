[CmdletBinding()]
param(
  # Можно переопределить: powershell ... -ApiUrl http://localhost:18000
  [string]$ApiUrl = $env:API_URL
)

$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

if (-not $ApiUrl) { $ApiUrl = 'http://127.0.0.1:18000' }

# Имена сервисов и БД (можно переопределить через .env)
$DbService = 'db'
$DbUser   = if ($env:DB_USER) { $env:DB_USER } else { 'postgres' }
$DbName   = if ($env:DB_NAME) { $env:DB_NAME } else { 'wine_db' }

function Write-Title([string]$text) {
  Write-Host "`n=== $text ===" -ForegroundColor Cyan
}

function Invoke-Http200([string]$url, [int]$Retry = 30, [int]$DelaySec = 2) {
  for ($i = 0; $i -lt $Retry; $i++) {
    try {
      $r = Invoke-WebRequest -UseBasicParsing -TimeoutSec 10 -Uri $url
      if ($r.StatusCode -eq 200) {
        if ($r.Content) { Write-Host $r.Content }
        return $true
      }
    } catch {
      Start-Sleep -Seconds $DelaySec
      continue
    }
    Start-Sleep -Seconds $DelaySec
  }
  return $false
}

function Wait-ComposeHealthy([int]$TimeoutSec = 180) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $ps = docker compose ps
      $apiOK = $ps -match 'wine-assistant-api\s+.*\(healthy\)'
      $dbOK  = $ps -match 'wine-assistant-db\s+.*\(healthy\)'
      if ($apiOK -and $dbOK) { return $true }
    } catch {
      # ignore and retry
    }
    Start-Sleep -Seconds 2
  }
  return $false
}

# 1) Поднять стенд (если уже поднят — просто убедимся что всё ок)
Write-Title "Compose up"
docker compose up -d | Out-Host

# 2) Дождаться healthy статусов по compose ps
Write-Title "Waiting for services (compose ps -> healthy)"
if (-not (Wait-ComposeHealthy 180)) {
  docker compose ps | Out-Host
  throw "Services aren't healthy by 'docker compose ps' timeout"
}

# 3) API проверки
Write-Title "API /live"
if (-not (Invoke-Http200 "$ApiUrl/live")) { throw "GET /live failed" }

Write-Title "API /ready"
if (-not (Invoke-Http200 "$ApiUrl/ready")) { throw "GET /ready failed" }

Write-Title "API /version"
if (-not (Invoke-Http200 "$ApiUrl/version")) { throw "GET /version failed" }

# 4) База: psql-проверки из контейнера
Write-Title "DB: extensions"
docker compose exec -T $DbService psql -U $DbUser -d $DbName -c "SELECT extname FROM pg_extension ORDER BY 1;" | Out-Host

Write-Title "DB: time & timezone"
docker compose exec -T $DbService psql -U $DbUser -d $DbName -c "SELECT now(), current_setting('TimeZone');" | Out-Host

Write-Title "DB: migrations count"
docker compose exec -T $DbService psql -U $DbUser -d $DbName -c "SELECT COUNT(*) AS files FROM schema_migrations;" | Out-Host

Write-Title "DB: last 10 migrations"
docker compose exec -T $DbService psql -U $DbUser -d $DbName -c "SELECT version, filename, applied_at FROM schema_migrations_view ORDER BY applied_at DESC LIMIT 10;" | Out-Host

Write-Title "Done ✅"
exit 0
