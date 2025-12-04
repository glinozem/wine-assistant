Param()

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------

function Write-Section {
    param(
        [Parameter(Mandatory = $true)][string]$Text
    )
    Write-Host ""
    Write-Host "=== $Text ===" -ForegroundColor Cyan
}

function Invoke-External {
    param(
        [Parameter(Mandatory = $true)][string[]]$Command,
        [string]$WorkingDirectory = $null
    )

    $display = $Command -join ' '
    Write-Host ">> $display"

    if ($WorkingDirectory) {
        Push-Location $WorkingDirectory
    }

    try {
        & $Command[0] @($Command[1..($Command.Length - 1)])
        $exitCode = $LASTEXITCODE
        if ($exitCode -ne 0) {
            Write-Error ("Command failed with exit code {0}: {1}" -f $exitCode, $display)
            throw "Command failed"
        }
    }
    finally {
        if ($WorkingDirectory) {
            Pop-Location
        }
    }
}

function Get-DateFromFilename {
    param(
        [Parameter(Mandatory = $true)][string]$FileName
    )
    # Ищем шаблон YYYY_MM_DD в имени (работает и для "Копия 2025_01_20 Прайс...")
    if ($FileName -match '(\d{4})_(\d{2})_(\d{2})') {
        $y = [int]$matches[1]
        $m = [int]$matches[2]
        $d = [int]$matches[3]
        return [datetime]::new($y, $m, $d)
    }
    else {
        # Если по какой-то причине дата не нашлась — отправляем в конец
        return [datetime]::MaxValue
    }
}

function Wait-ForApiReady {
    param(
        [string]$BaseUrl,
        [int]$MaxAttempts = 30,
        [int]$DelaySeconds = 2
    )

    Write-Section "Waiting for API to be alive/ready/healthy..."

    for ($i = 1; $i -le $MaxAttempts; $i++) {
        try {
            $live   = Invoke-RestMethod -Method GET -Uri "$BaseUrl/live"  -TimeoutSec 5
            $ready  = Invoke-RestMethod -Method GET -Uri "$BaseUrl/ready" -TimeoutSec 5
            $health = Invoke-RestMethod -Method GET -Uri "$BaseUrl/health" -TimeoutSec 5

            if ($live.status -eq "alive" -and $ready.status -eq "ready" -and $health.ok -eq $true) {
                Write-Host ("API is alive and ready (attempt {0})." -f $i)
                Write-Host "  /live  -> status = $($live.status)"
                Write-Host "  /ready -> status = $($ready.status)"
                Write-Host "  /health-> @{ok=$($health.ok)}"
                return
            }
        }
        catch {
            # Игнорируем, просто ждём дальше
        }

        Start-Sleep -Seconds $DelaySeconds
    }

    throw "API did not become ready after $MaxAttempts attempts."
}

# -----------------------------------------------------------------------------
# Setup: paths and config
# -----------------------------------------------------------------------------

Write-Section "manual_smoke_check.ps1: start"

# Определяем корень репо: ...\wine-assistant
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot  = Split-Path $ScriptDir -Parent

Set-Location $RepoRoot

# Base URL
$BaseUrl = $env:WINE_ASSISTANT_BASE_URL
if (-not $BaseUrl -or $BaseUrl.Trim() -eq "") {
    $BaseUrl = "http://localhost:18000"
}

# API key: берём из .env или из переменной окружения
$EnvFile = Join-Path $RepoRoot ".env"
$ApiKey = $null

if (Test-Path $EnvFile) {
    $line = Get-Content $EnvFile | Where-Object { $_ -match '^\s*API_KEY\s*=' } | Select-Object -First 1
    if ($line) {
        $ApiKey = $line.Split('=', 2)[1].Trim()
    }
}

if (-not $ApiKey -or $ApiKey.Trim() -eq "") {
    $ApiKey = $env:API_KEY
}

if (-not $ApiKey -or $ApiKey.Trim() -eq "") {
    throw "API key not found. Please set API_KEY in .env or environment."
}

Write-Host "BaseUrl = $BaseUrl"
Write-Host "API key = $ApiKey"
Write-Host ""
Write-Host "Repo root = $RepoRoot"
Write-Host ""

# -----------------------------------------------------------------------------
# STEP 1. Docker: down -v / build / up -d
# -----------------------------------------------------------------------------

Write-Section "STEP 1. Docker: down -v / build / up -d"

Invoke-External @("docker", "compose", "down", "-v")
Invoke-External @("docker", "compose", "build")
Invoke-External @("docker", "compose", "up", "-d")

Write-Host ""
Invoke-External @("docker", "compose", "ps")

# Ждем готовности API
Wait-ForApiReady -BaseUrl $BaseUrl

# -----------------------------------------------------------------------------
# STEP 2. Load Excel price lists (ETL) in chronological order
# -----------------------------------------------------------------------------

Write-Section "STEP 2. Load Excel price lists and enrich products"

$InboxDir = Join-Path $RepoRoot "data\inbox"

if (-not (Test-Path $InboxDir)) {
    throw "Inbox dir not found: $InboxDir"
}

$priceFiles = Get-ChildItem -Path $InboxDir -Filter "*.xlsx" | Sort-Object {
    Get-DateFromFilename $_.Name
}

$filesCount = $priceFiles.Count
Write-Host "Inbox dir: $InboxDir"
Write-Host ("Found {0} price file(s) (sorted oldest → newest by filename date):" -f $filesCount)

foreach ($file in $priceFiles) {
    $effDate = Get-DateFromFilename $file.Name
    $dateStr = if ($effDate -eq [datetime]::MaxValue) { "????-??-??" } else { $effDate.ToString("yyyy-MM-dd") }
    Write-Host ("  {0}  {1}" -f $dateStr, $file.FullName)
}

if ($filesCount -eq 0) {
    throw "No Excel files found in inbox directory."
}

foreach ($file in $priceFiles) {
    Write-Host ""
    Write-Host (">> load_csv: {0}" -f $file.FullName)

    $dockerPricePath = $file.Name  # только имя, без хостового пути

    Invoke-External @(
        "docker", "compose", "exec", "-T", "api",
        "python", "-m", "scripts.load_csv",
        "--excel", "/app/data/inbox/$dockerPricePath"
    )
}

# -----------------------------------------------------------------------------
# STEP 3. (Optional) Wineries & enrichment
# -----------------------------------------------------------------------------

Write-Section "STEP 3. (Optional) Wineries & enrichment"

$WineriesExcelPath = Join-Path $RepoRoot "data\catalog\wineries_enrichment_from_pdf_norm.xlsx"

if (Test-Path $WineriesExcelPath) {
    Write-Host "Found wineries catalog: $WineriesExcelPath"

    # 1) Загружаем/обновляем винодельни
    Write-Host ">> load_wineries (--apply)"
    Invoke-External @(
        "docker", "compose", "exec", "-T", "api",
        "python", "-m", "scripts.load_wineries",
        "--excel", "/app/data/catalog/wineries_enrichment_from_pdf_norm.xlsx",
        "--apply"
    )

    # 2) Обогащаем производителей по тем же данным
    Write-Host ">> enrich_producers (--apply)"
    Invoke-External @(
        "docker", "compose", "exec", "-T", "api",
        "python", "-m", "scripts.enrich_producers",
        "--excel", "/app/data/catalog/wineries_enrichment_from_pdf_norm.xlsx",
        "--apply"
    )
}
else {
    Write-Host "Wineries catalog not found, skipping STEP 3." -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# STEP 4. Manual API smoke checks
# -----------------------------------------------------------------------------

Write-Section "STEP 4. Manual API smoke checks"

$headers = @{
    "X-API-Key" = $ApiKey
}

Write-Host ">> /live /ready /health"
$live   = Invoke-RestMethod -Method GET -Uri "$BaseUrl/live"   -TimeoutSec 10
$ready  = Invoke-RestMethod -Method GET -Uri "$BaseUrl/ready"  -TimeoutSec 10
$health = Invoke-RestMethod -Method GET -Uri "$BaseUrl/health" -TimeoutSec 10

$live
$ready
$health

Write-Host ""
Write-Host ">> /api/v1/products/search?limit=5&in_stock=true"
$searchUrl = "$BaseUrl/api/v1/products/search?limit=5&in_stock=true"

$searchResponse = Invoke-RestMethod -Method GET -Uri $searchUrl -Headers $headers -TimeoutSec 30

$searchResponse | Format-List

Write-Host ""
Write-Host ">> Краткий список найденных SKU"
$searchResponse.items |
    Select-Object code, name, price_final_rub, stock_total |
    Format-Table -AutoSize

if (-not $searchResponse.items -or $searchResponse.items.Count -eq 0) {
    throw "Search returned no items; cannot continue with SKU checks."
}

# Берём первый код SKU для дальнейших проверок
$skuCode = $searchResponse.items[0].code
Write-Host ""
Write-Host "Выбран код для smoke-чека SKU: $skuCode"

Write-Host ""
Write-Host ">> /api/v1/sku/$skuCode"
$skuUrl = "$BaseUrl/api/v1/sku/$skuCode"
$skuResponse = Invoke-RestMethod -Method GET -Uri $skuUrl -Headers $headers -TimeoutSec 30
$skuResponse | ConvertTo-Json -Depth 10 | Write-Host

Write-Host ""
Write-Host ">> /api/v1/sku/$skuCode/price-history?from=2020-01-01&to=2030-12-31&limit=50"
$priceHistUrl = "$BaseUrl/api/v1/sku/$skuCode/price-history?from=2020-01-01&to=2030-12-31&limit=50"
$priceHist = Invoke-RestMethod -Method GET -Uri $priceHistUrl -Headers $headers -TimeoutSec 30
$priceHist | Format-List

Write-Host ""
Write-Host ">> /api/v1/sku/$skuCode/inventory-history?from=2020-01-01&to=2030-12-31&limit=50"
$invHistUrl = "$BaseUrl/api/v1/sku/$skuCode/inventory-history?from=2020-01-01&to=2030-12-31&limit=50"
$invHist = Invoke-RestMethod -Method GET -Uri $invHistUrl -Headers $headers -TimeoutSec 30
$invHist | Format-List


# -----------------------------------------------------------------------------
# STEP 5. Export endpoints (JSON/PDF/XLSX)
# -----------------------------------------------------------------------------

Write-Section "STEP 5. Export endpoints"
Write-Host ("Using SKU code for export: '{0}'" -f $skuCode)

# 5.1. Экспорт карточки SKU в JSON и PDF
$skuJsonUrl = "$BaseUrl/export/sku/${skuCode}?format=json"
$skuPdfUrl  = "$BaseUrl/export/sku/${skuCode}?format=pdf"

$skuJsonPath = Join-Path $RepoRoot "sku_${skuCode}.json"
$skuPdfPath  = Join-Path $RepoRoot "sku_${skuCode}.pdf"

Write-Host ">> $skuJsonUrl -> $skuJsonPath"
Invoke-WebRequest -Method GET -Uri $skuJsonUrl -Headers $headers -OutFile $skuJsonPath

Write-Host ">> $skuPdfUrl -> $skuPdfPath"
Invoke-WebRequest -Method GET -Uri $skuPdfUrl -Headers $headers -OutFile $skuPdfPath

# 5.2. Экспорт истории цен и остатков в XLSX
$priceHistXlsxUrl = "$BaseUrl/export/price-history/${skuCode}?format=xlsx&from=2020-01-01&to=2030-12-31&limit=20"
$invHistXlsxUrl   = "$BaseUrl/export/inventory-history/${skuCode}?format=xlsx&from=2020-01-01&to=2030-12-31&limit=20"

$priceHistXlsxPath = Join-Path $RepoRoot "price_history_${skuCode}.xlsx"
$invHistXlsxPath   = Join-Path $RepoRoot "inventory_history_${skuCode}.xlsx"

Write-Host ">> $priceHistXlsxUrl -> $priceHistXlsxPath"
Invoke-WebRequest -Method GET -Uri $priceHistXlsxUrl -Headers $headers -OutFile $priceHistXlsxPath

Write-Host ">> $invHistXlsxUrl -> $invHistXlsxPath"
Invoke-WebRequest -Method GET -Uri $invHistXlsxUrl -Headers $headers -OutFile $invHistXlsxPath

Write-Section "manual_smoke_check.ps1: done"
