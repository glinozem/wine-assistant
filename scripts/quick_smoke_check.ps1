param(
    [string]$BaseUrl = "http://localhost:18000",
    [string]$ApiKey  = $env:API_KEY
)

Write-Host "=== quick_smoke_check.ps1: старт ===" -ForegroundColor Cyan

if (-not $ApiKey) {
    Write-Error "API key не задан. Перед запуском установи переменную окружения API_KEY или передай -ApiKey."
    Write-Host 'Пример:'
    Write-Host '$env:API_KEY = "..."'
    Write-Host '.\scripts\quick_smoke_check.ps1'
    exit 1
}

$headers = @{ "X-API-Key" = $ApiKey }

Write-Host "BaseUrl = $BaseUrl"
Write-Host "API key  = $ApiKey`n"

# Определим корень репозитория относительно расположения скрипта
$scriptDir = $PSScriptRoot
$repoRoot  = Split-Path $scriptDir -Parent

Write-Host "Repo root = $repoRoot`n"

# =====================================================================
# ШАГ 4. Ручной прогон API (search, SKU, history)
# =====================================================================

Write-Host "=== ШАГ 4. Ручной прогон API ===" -ForegroundColor Yellow

Write-Host ">> /live /ready /health" -ForegroundColor Green
Invoke-RestMethod "$BaseUrl/live"
Invoke-RestMethod "$BaseUrl/ready"
Invoke-RestMethod "$BaseUrl/health"
Write-Host ""

Write-Host ">> /api/v1/products/search?limit=5&in_stock=true" -ForegroundColor Green
$search = Invoke-RestMethod `
  "$BaseUrl/api/v1/products/search?limit=5&in_stock=true" `
  -Headers $headers

$search
Write-Host ""

if (-not $search.items -or $search.items.Count -eq 0) {
    Write-Warning "Поиск не вернул ни одного товара — дальше SKU-тесты пропускаем."
    exit 0
}

Write-Host ">> Краткий список найденных SKU" -ForegroundColor Green
$search.items | Select-Object code, name, price_final_rub, stock_total | Format-Table
Write-Host ""

$code = $search.items[0].code
Write-Host "Выбран код для smoke-чека SKU: $code`n"

Write-Host ">> /api/v1/sku/$code" -ForegroundColor Green
$sku = Invoke-RestMethod `
  "$BaseUrl/api/v1/sku/$code" `
  -Headers $headers

$sku | ConvertTo-Json -Depth 5
Write-Host ""

Write-Host ">> /api/v1/sku/$code/price-history (...)" -ForegroundColor Green
$priceHistory = Invoke-RestMethod `
  "$BaseUrl/api/v1/sku/$code/price-history?from=2020-01-01&to=2030-12-31&limit=50" `
  -Headers $headers

$priceHistory
Write-Host ""

Write-Host ">> /api/v1/sku/$code/inventory-history (...)" -ForegroundColor Green
$invHistory = Invoke-RestMethod `
  "$BaseUrl/api/v1/sku/$code/inventory-history?from=2020-01-01&to=2030-12-31&limit=50" `
  -Headers $headers

$invHistory
Write-Host ""

# =====================================================================
# ШАГ 5. Экспортные эндпоинты (SKU, price-history, inventory-history)
# =====================================================================

Write-Host "=== ШАГ 5. Экспортные эндпоинты ===" -ForegroundColor Yellow

# --- SKU JSON ---
$skuJsonUrl = "$BaseUrl/export/sku/$($code)?format=json"
Write-Host ">> $skuJsonUrl" -ForegroundColor Green
$skuExportJson = Invoke-RestMethod $skuJsonUrl -Headers $headers
$skuExportJson | ConvertTo-Json -Depth 5
Write-Host ""

# --- SKU PDF ---
$skuPdfUrl = "$BaseUrl/export/sku/$($code)?format=pdf"
$skuPdfPath = Join-Path $repoRoot "sku_$code.pdf"

Write-Host ">> $skuPdfUrl -> $skuPdfPath" -ForegroundColor Green
Invoke-WebRequest `
  $skuPdfUrl `
  -Headers $headers `
  -OutFile $skuPdfPath
Write-Host ""

# --- Price history XLSX ---
$priceFrom  = "2020-01-01"
$priceTo    = "2030-12-31"
$priceLimit = 20

$priceXlsxUrl  = "$BaseUrl/export/price-history/$($code)?format=xlsx&from=$priceFrom&to=$priceTo&limit=$priceLimit"
$priceXlsxPath = Join-Path $repoRoot "price_history_$code.xlsx"

Write-Host ">> $priceXlsxUrl -> $priceXlsxPath" -ForegroundColor Green
Invoke-WebRequest `
  $priceXlsxUrl `
  -Headers $headers `
  -OutFile $priceXlsxPath
Write-Host ""

# --- Inventory history XLSX ---
$invFrom   = "2020-01-01"
$invTo     = "2030-12-31"
$invLimit  = 20

$invXlsxUrl  = "$BaseUrl/export/inventory-history/$($code)?format=xlsx&from=$invFrom&to=$invTo&limit=$invLimit"
$invXlsxPath = Join-Path $repoRoot "inventory_history_$code.xlsx"

Write-Host ">> $invXlsxUrl -> $invXlsxPath" -ForegroundColor Green
Invoke-WebRequest `
  $invXlsxUrl `
  -Headers $headers `
  -OutFile $invXlsxPath
Write-Host ""

Write-Host "=== quick_smoke_check.ps1: успешно завершён ===" -ForegroundColor Cyan
