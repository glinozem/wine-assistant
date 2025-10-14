Param(
  [string]$Service = "db",
  [string]$Database = "wine_db",
  [string]$User = "postgres"
)
$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

if (-not (Test-Path "db\migrations")) {
  Write-Error "Папка db\migrations не найдена."
  exit 1
}

Get-ChildItem -Path "db\migrations" -Filter "*.sql" | Sort-Object Name | ForEach-Object {
  $name = $_.Name
  $full = $_.FullName
  Write-Host "==> Applying $name"
  Get-Content $full -Raw |
    docker compose exec -T $Service psql -U $User -d $Database -v ON_ERROR_STOP=1 -f - |
    Write-Host
  if ($LASTEXITCODE -ne 0) {
    throw "psql failed on $name (exit $LASTEXITCODE)"
  }
}
Write-Host "✅ All migrations applied."
