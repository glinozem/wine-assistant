param(
    [string]$BaseUrl = "http://localhost:18000",
    [string]$ApiKey  = $env:API_KEY
)

if (-not $ApiKey -or $ApiKey.Trim() -eq "") {
    Write-Host "[ERROR] API key is not set. Please set API_KEY env var or pass -ApiKey." -ForegroundColor Red
    exit 1
}

$headers = @{ "X-API-Key" = $ApiKey }

$results = @()

function Test-Endpoint {
    param(
        [string]$Name,
        [string]$Url,
        [hashtable]$Headers = $null,
        [switch]$Optional,
        [scriptblock]$Validate = $null
    )

    Write-Host ("==> Checking {0}: {1}" -f $Name, $Url)

    $success = $false
    $message = ""
    $status  = $null

    try {
        if ($Headers) {
            $resp = Invoke-RestMethod -Uri $Url -Headers $Headers -TimeoutSec 10
        } else {
            $resp = Invoke-RestMethod -Uri $Url -TimeoutSec 10
        }

        $success = $true
        $status  = 200

        if ($Validate) {
            $validationResult = & $Validate $resp
            if (-not $validationResult.Success) {
                $success = $false
                $message = $validationResult.Message
            }
        }

        if ($success) {
            Write-Host "   OK" -ForegroundColor Green
        } else {
            Write-Host ("   FAIL: {0}" -f $message) -ForegroundColor Yellow
        }
    }
    catch {
        $success = $false
        $message = $_.Exception.Message
        if ($_.Exception.Response -and $_.Exception.Response.StatusCode) {
            $status = [int]$_.Exception.Response.StatusCode
        }
        Write-Host ("   ERROR: {0}" -f $message) -ForegroundColor Red
    }

    $results += [pscustomobject]@{
        Name     = $Name
        Url      = $Url
        Success  = $success
        Optional = [bool]$Optional
        Message  = $message
        Status   = $status
    }
}

# 1. Health / liveness / readiness
Test-Endpoint -Name "live"  -Url "$BaseUrl/live"  -Validate {
    param($resp)
    $ok = $resp.status -eq "alive"
    if ($ok) {
        return [pscustomobject]@{ Success = $true;  Message = "" }
    } else {
        return [pscustomobject]@{ Success = $false; Message = ("status is '{0}'" -f $resp.status) }
    }
}

Test-Endpoint -Name "ready" -Url "$BaseUrl/ready" -Validate {
    param($resp)
    $ok = $resp.status -eq "ready"
    if ($ok) {
        return [pscustomobject]@{ Success = $true;  Message = "" }
    } else {
        return [pscustomobject]@{ Success = $false; Message = ("status is '{0}'" -f $resp.status) }
    }
}

Test-Endpoint -Name "health" -Url "$BaseUrl/health" -Validate {
    param($resp)
    $ok = ($resp -eq $true) -or ("$resp" -match "ok")
    if ($ok) {
        return [pscustomobject]@{ Success = $true;  Message = "" }
    } else {
        return [pscustomobject]@{ Success = $false; Message = ("unexpected health response '{0}'" -f $resp) }
    }
}

# 2. Search
Test-Endpoint -Name "products.search" -Url "$BaseUrl/api/v1/products/search?limit=3" -Headers $headers -Validate {
    param($resp)
    $hasItems = $resp.items -and $resp.items.Count -gt 0
    if ($hasItems) {
        return [pscustomobject]@{ Success = $true;  Message = "" }
    } else {
        return [pscustomobject]@{ Success = $false; Message = "no items returned" }
    }
}

# 3. SKU + history (using first code from search)
$skuCode = $null
try {
    $search = Invoke-RestMethod -Uri "$BaseUrl/api/v1/products/search?limit=3" -Headers $headers -TimeoutSec 10
    if ($search.items -and $search.items.Count -gt 0) {
        $skuCode = $search.items[0].code
        Write-Host ("Using SKU code from search: {0}" -f $skuCode)
    } else {
        Write-Host "[WARN] Search returned no items, skipping SKU/history checks." -ForegroundColor Yellow
    }
}
catch {
    Write-Host ("[WARN] Could not perform initial search for SKU, skipping SKU/history checks: {0}" -f $_.Exception.Message) -ForegroundColor Yellow
}

if ($skuCode) {
    Test-Endpoint -Name "sku" -Url "$BaseUrl/api/v1/sku/$skuCode" -Headers $headers

    Test-Endpoint -Name "price-history" -Url "$BaseUrl/api/v1/sku/$skuCode/price-history?from=2025-01-01&to=2025-12-31&limit=50" -Headers $headers -Optional

    Test-Endpoint -Name "inventory-history" -Url "$BaseUrl/api/v1/sku/$skuCode/inventory-history?from=2025-01-01&to=2025-12-31&limit=50" -Headers $headers -Optional
}

# 4. Export (JSON mode)
Test-Endpoint -Name "export.search.json" -Url "$BaseUrl/export/search?format=json&limit=3" -Headers $headers

if ($skuCode) {
    # Export SKU card as JSON (required)
    $exportSkuUrl = "$BaseUrl/export/sku/$($skuCode)?format=json"
    Test-Endpoint -Name "export.sku.json" -Url $exportSkuUrl -Headers $headers

    # Export price history as JSON (optional)
    $exportPriceHistoryUrl = "$BaseUrl/export/price-history/$($skuCode)?format=json"
    Test-Endpoint -Name "export.price-history.json" -Url $exportPriceHistoryUrl -Headers $headers -Optional
}


Write-Host ""
Write-Host "==== SMOKE SUMMARY ===="

$results | Format-Table Name, Success, Optional, Status, Message -AutoSize

$hardFailures = $results | Where-Object { -not $_.Success -and -not $_.Optional }

if ($hardFailures.Count -gt 0) {
    Write-Host ""
    Write-Host "[FAIL] Smoke-check finished with errors (required endpoints failed)." -ForegroundColor Red
    exit 1
} else {
    Write-Host ""
    Write-Host "[OK] Smoke-check passed (all required endpoints are healthy)." -ForegroundColor Green
    exit 0
}
