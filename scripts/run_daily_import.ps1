[CmdletBinding()]
param(
    [ValidateSet("auto", "files")]
    [string]$Mode = "auto",

    # Для режима files: можно передать либо массив, либо одну строку с разделителями
    [string[]]$Files = @()
)

$ErrorActionPreference = "Stop"

Write-Host "==========================================================="
Write-Host "Daily Import (Wine Assistant)"
Write-Host "Mode: $Mode"
Write-Host "==========================================================="
Write-Host ""

# Собираем args для docker-compose exec БЕЗ bash -c (меньше проблем с quoting)
$dcArgs = @("exec", "-T", "api", "python", "-m", "scripts.daily_import_ops", "--mode", $Mode)

if ($Mode -eq "files") {
    if (-not $Files -or $Files.Count -eq 0) {
        throw "Mode 'files' requires -Files file1.xlsx,file2.xlsx (or -Files file1.xlsx file2.xlsx)"
    }

    # Если передали одной строкой с запятыми — развернём
    if ($Files.Count -eq 1 -and $Files[0] -match ",") {
        $Files = $Files[0].Split(",") | ForEach-Object { $_.Trim() } | Where-Object { $_ }
    }

    $dcArgs += @("--files")
    $dcArgs += $Files
}

Write-Host "Executing in container 'api'..."
Write-Host ("docker-compose " + ($dcArgs -join " ")) -ForegroundColor DarkGray
Write-Host ""

# Выполняем и забираем stdout/stderr
$raw = & docker-compose @dcArgs 2>&1
$rawText = ($raw -join "`n").Trim()

# Пытаемся извлечь JSON более устойчиво:
# перебираем все позиции '{' и пытаемся распарсить JSON с каждой позиции
$result = $null
$jsonText = $null

$start = $rawText.IndexOf("{")
if ($start -lt 0) {
    Write-Host "ERROR: Orchestrator output does not contain JSON object start '{'." -ForegroundColor Red
    Write-Host $rawText
    exit 5
}

for ($i = $start; $i -ge 0; ) {
    $candidate = $rawText.Substring($i).Trim()

    try {
        $parsed = $candidate | ConvertFrom-Json -ErrorAction Stop
        $result = $parsed
        $jsonText = $candidate
        break
    } catch {
        $next = $rawText.IndexOf("{", $i + 1)
        if ($next -lt 0) { break }
        $i = $next
    }
}

if (-not $result) {
    Write-Host "ERROR: Failed to parse JSON output (no parseable JSON object found)." -ForegroundColor Red
    Write-Host $rawText
    exit 5
}
# Логика exit code по JSON
$exitCode = 0
$status = $result.status

$hasQuarantine = $false
if ($result.files) {
    $hasQuarantine = @($result.files | Where-Object { $_.status -eq "QUARANTINED" }).Count -gt 0
}

$noFiles = $false
if ($result.files -and $result.files.Count -eq 1) {
    if ($result.files[0].skip_reason -eq "NO_FILES_IN_INBOX") {
        $noFiles = $true
    }
}

if ($status -eq "FAILED" -or $status -eq "TIMEOUT") {
    $exitCode = 2
} elseif ($hasQuarantine) {
    $exitCode = 1
} elseif ($noFiles) {
    $exitCode = 4
} else {
    $exitCode = 0
}

Write-Host ""
Write-Host "run_id: $($result.run_id)"
Write-Host "status: $status"
Write-Host "exitCode: $exitCode"
Write-Host ""

# Выводим JSON (по желанию можно убрать)
Write-Host $jsonText

exit $exitCode
