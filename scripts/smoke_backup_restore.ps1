$ErrorActionPreference = "Stop"

function Wait-HttpOk($url, $name, $tries=30, $sleepSec=1) {
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

# 1) Base stack
docker compose config | Out-Null
docker compose up -d --build
Wait-HttpOk "http://localhost:18000/ready" "API ready"

# 2) Storage stack (MinIO)
docker compose -f docker-compose.yml -f docker-compose.storage.yml config | Out-Null
make storage-up
Wait-HttpOk "http://localhost:19000/minio/health/live" "MinIO live"

# 3) Restore from latest remote (скачает при необходимости)
make restore-remote-latest
Wait-HttpOk "http://localhost:18000/ready" "API ready after restore"

# 4) DB checks
docker compose exec db psql -U postgres -d wine_db -c "select count(*) products from products;"
docker compose exec db psql -U postgres -d wine_db -c "select count(*) price_rows from product_prices;"
docker compose exec db psql -U postgres -d wine_db -c "select count(*) inventory_rows from inventory;"
docker compose exec db psql -U postgres -d wine_db -c "select count(*) as bad from products where price_list_rub is not null and price_final_rub is null;"

# 5) Backup + prune + list remote
make backup BACKUP_KEEP=2
make backups-list-remote
Get-ChildItem .\backups\*.dump
