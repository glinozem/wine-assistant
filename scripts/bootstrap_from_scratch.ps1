param(
  [string]$BaseUrl = "http://localhost:18000",
  [string]$InboxDir = ".\data\inbox",
  [string]$WineriesPdfNorm = ".\data\catalog\wineries_enrichment_from_pdf_norm.xlsx",
  [string]$WineriesEnrichment = ".\data\catalog\wineries_enrichment.xlsx",
  [switch]$RebuildImages,
  [switch]$SyncInventoryHistoryDryRunFirst = $true
)

$ErrorActionPreference = "Stop"

$composeFiles = @("-f","docker-compose.yml","-f","docker-compose.observability.yml")

function Assert-LastExitCode([string]$Step) {
  if ($LASTEXITCODE -ne 0) {
    throw "Step failed ($Step), exit code: $LASTEXITCODE"
  }
}

function Wait-ApiReady([string]$Url, [int]$TimeoutSec = 180) {
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  while ((Get-Date) -lt $deadline) {
    try {
      $r = Invoke-RestMethod "$Url/ready" -TimeoutSec 5
      if ($null -ne $r -and $r.status -eq "ready") {
        Write-Host "[ready] OK: status=ready"
        return
      }
    } catch { }
    Start-Sleep -Seconds 2
  }
  throw "API is not ready after $TimeoutSec seconds: $Url/ready"
}

function Get-EffectiveDateFromName([string]$Name) {
  # ловим YYYY_MM_DD в имени
  if ($Name -match '(\d{4})_(\d{2})_(\d{2})') {
    return [datetime]::ParseExact("$($Matches[1])-$($Matches[2])-$($Matches[3])", "yyyy-MM-dd", $null)
  }
  return [datetime]::MaxValue
}

Write-Host "=== DOWN (wipe volumes) ==="
docker compose @composeFiles down -v --remove-orphans
Assert-LastExitCode "compose down"

Write-Host "=== BUILD ==="
docker compose @composeFiles build
Assert-LastExitCode "compose build"

Write-Host "=== UP ==="
docker compose @composeFiles up -d
Assert-LastExitCode "compose up"

Wait-ApiReady $BaseUrl

Write-Host "=== IMPORT PRICE LISTS (load_csv) ==="
if (!(Test-Path $InboxDir)) { throw "InboxDir not found: $InboxDir" }

$files = Get-ChildItem -Path $InboxDir -File -Filter "*.xlsx" |
  Sort-Object @{ Expression = { Get-EffectiveDateFromName $_.Name } }, Name

if ($files.Count -eq 0) { throw "No .xlsx files found in $InboxDir" }

foreach ($f in $files) {
  Write-Host ">>> Import: $($f.FullName)"
  python -m scripts.load_csv --excel "$($f.FullName)"
  Assert-LastExitCode "load_csv $($f.Name)"
}

Write-Host "=== LOAD WINERIES CATALOG (wineries table) ==="
python -m scripts.load_wineries --excel "$WineriesPdfNorm" --apply
Assert-LastExitCode "load_wineries"

Write-Host "=== ENRICH PRODUCTS (region/site) ==="
python -m scripts.enrich_producers --excel "$WineriesEnrichment" --apply
Assert-LastExitCode "enrich_producers"

Write-Host "=== BACKFILL products.region from wineries.region where NULL ==="
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "
  UPDATE products p
  SET region = w.region
  FROM wineries w
  WHERE p.supplier = w.supplier
    AND p.region IS NULL
    AND w.region IS NOT NULL;
"
Assert-LastExitCode "backfill region"

Write-Host "=== BACKFILL products.producer_site from wineries.producer_site where invalid/NULL ==="
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "
  UPDATE products p
  SET producer_site = regexp_replace(w.producer_site, '\s+', '', 'g')
  FROM wineries w
  WHERE p.supplier = w.supplier
    AND (p.producer_site IS NULL OR p.producer_site ~ '[^ -~]' OR p.producer_site ~ '\s')
    AND w.producer_site IS NOT NULL;
"
Assert-LastExitCode "backfill producer_site"


Write-Host "=== INVENTORY HISTORY SNAPSHOT ==="
if ($SyncInventoryHistoryDryRunFirst) {
  docker compose @composeFiles exec api python -m scripts.sync_inventory_history --dry-run
  Assert-LastExitCode "sync_inventory_history --dry-run"
}
docker compose @composeFiles exec api python -m scripts.sync_inventory_history
Assert-LastExitCode "sync_inventory_history"

Write-Host "=== CHECKS ==="
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "SELECT COUNT(*) AS products FROM products;"
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "SELECT COUNT(*) AS price_rows FROM product_prices;"
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "SELECT COUNT(*) AS inventory_rows FROM inventory;"
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "SELECT COUNT(*) AS inventory_history_rows FROM inventory_history;"
docker compose @composeFiles exec db psql -U postgres -d wine_db -c "
  SELECT supplier, producer_site
  FROM products
  WHERE producer_site IS NOT NULL
    AND (producer_site ~ '[^ -~]' OR producer_site ~ '\s');
"
Write-Host "DONE."
