#requires -Version 5.1
[CmdletBinding()]
param(
  [Parameter(Mandatory = $true)]
  [string]$Supplier,

  [string]$BaseUrl = 'http://localhost:18000',

  [string[]]$ComposeFiles = @('docker-compose.yml'),

  [switch]$Fresh,
  [switch]$Build,

  [ValidateSet('skip', 'whatif', 'run')]
  [string]$StaleDetectorMode = 'whatif',

  [string]$DbUser = 'postgres',
  [string]$DbName = 'wine_db',

  [int]$ReadyTimeoutSec = 180,

  [switch]$RunApiSmoke
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'

$DQ = [char]34
$DQs = [string]$DQ

function Is-VerboseEnabled { return ($VerbosePreference -ne 'SilentlyContinue') }

function Fail([string]$Message, [int]$Code = 1) {
  Write-Error $Message
  exit $Code
}

function Normalize-OneLine([string]$s) {
  if ($null -eq $s) { return '' }
  return (($s -replace '(\r\n|\r|\n)', ' ').Trim())
}

function Format-LogArg([object]$Value) {
  if ($null -eq $Value) { return ($DQs + $DQs) }

  $s = [string]$Value
  $needQuote = ($s -match '\s') -or ($s.IndexOf($DQ) -ge 0)

  if (-not $needQuote) { return $s }

  $pattern = [regex]::Escape($DQs)
  $repl = '\' + $DQs   # => \"
  $escaped = ($s -replace $pattern, $repl)

  return ($DQs + $escaped + $DQs)
}

function Write-Section([string]$Text) {
  Write-Host ''
  Write-Host ('=== {0} ===' -f $Text) -ForegroundColor Cyan
}

function Resolve-RepoRoot {
  try {
    $root = (& git rev-parse --show-toplevel 2>$null)
    if ($LASTEXITCODE -eq 0 -and $root) { return $root.Trim() }
  } catch { }
  $here = Split-Path -Parent $PSCommandPath
  return (Resolve-Path (Join-Path $here '..')).Path
}

function Compose-FileArgs([string[]]$Files) {
  $a = @()
  foreach ($f in $Files) { $a += @('-f', $f) }
  return $a
}

function Invoke-External([string[]]$CmdArgs, [string]$ErrorContext = 'command failed') {
  if (-not $CmdArgs -or $CmdArgs.Count -lt 1) { throw 'Invoke-External: empty args' }

  $cmdStr = Normalize-OneLine(($CmdArgs | ForEach-Object { Format-LogArg $_ }) -join ' ')
  if (Is-VerboseEnabled) { Write-Host ('VERBOSE: Command: {0}' -f $cmdStr) }
  else { Write-Verbose ('Command: {0}' -f $cmdStr) }

  $exe = $CmdArgs[0]
  $rest = @()
  if ($CmdArgs.Count -gt 1) { $rest = $CmdArgs[1..($CmdArgs.Count-1)] }

  & $exe @rest
  if ($LASTEXITCODE -ne 0) {
    Fail ('{0}: exit code {1}. Command: {2}' -f $ErrorContext, $LASTEXITCODE, $cmdStr) $LASTEXITCODE
  }
}

function Wait-Ready([string]$Url, [int]$TimeoutSec) {
  Write-Section ('Waiting for /ready (timeout {0}s)...' -f $TimeoutSec)
  $deadline = (Get-Date).AddSeconds($TimeoutSec)
  $readyUrl = ($Url.TrimEnd('/') + '/ready')

  while ((Get-Date) -lt $deadline) {
    try {
      $resp = Invoke-RestMethod -Method GET -Uri $readyUrl -TimeoutSec 5
      if ($null -ne $resp -and ($resp.PSObject.Properties.Name -contains 'status') -and $resp.status -eq 'ready') {
        $ver = $null
        if ($resp.PSObject.Properties.Name -contains 'version') { $ver = $resp.version }
        Write-Host ('OK: ready (version={0})' -f $ver) -ForegroundColor Green
        return
      }
      $st = $null
      if ($null -ne $resp -and ($resp.PSObject.Properties.Name -contains 'status')) { $st = $resp.status }
      Write-Host ('INFO: not ready yet (status={0})' -f $st)
    } catch {
      Write-Host ('INFO: /ready not available yet: {0}' -f $_.Exception.Message)
    }
    Start-Sleep -Seconds 2
  }

  Fail ('Timeout waiting for API readiness: {0}' -f $readyUrl)
}

function Sql-Scalar([string]$Sql) {
  $composeArgs = Compose-FileArgs $ComposeFiles
  $dockerArgs = @('docker', 'compose') + $composeArgs + @(
    'exec', '-T', 'db',
    'psql', '-U', $DbUser, '-d', $DbName,
    '-tA', '-c', $Sql
  )

  if (Is-VerboseEnabled) { Write-Host ('VERBOSE: SQL: {0}' -f (Normalize-OneLine $Sql)) }
  else { Write-Verbose ('SQL: {0}' -f (Normalize-OneLine $Sql)) }

  $out = & $dockerArgs[0] @($dockerArgs[1..($dockerArgs.Count-1)])
  if ($LASTEXITCODE -ne 0) {
    $cmdStr = Normalize-OneLine(($args | ForEach-Object { Format-LogArg $_ }) -join ' ')
    Fail ('SQL check failed (exit {0}). SQL={1}. Command: {2}' -f $LASTEXITCODE, $Sql, $cmdStr) $LASTEXITCODE
  }

  return ([string]$out).Trim()
}

function Assert-AtLeast([string]$Name, [string]$Sql, [int]$Min) {
  $raw = Sql-Scalar $Sql
  [int]$val = 0
  if (-not [int]::TryParse($raw, [ref]$val)) {
    Fail ('SQL check ''{0}'' returned non-integer: ''{1}''. SQL={2}' -f $Name, $raw, $Sql)
  }
  if ($val -lt $Min) {
    Fail ('SQL check ''{0}'' failed: expected >= {1}, got {2}. SQL={3}' -f $Name, $Min, $val, $Sql)
  }
  Write-Host ('OK: {0} = {1} (>= {2})' -f $Name, $val, $Min) -ForegroundColor Green
}

function Pass-CommonVerbose([string[]]$BaseArgs) {
  if (Is-VerboseEnabled) { return $BaseArgs + @('-Verbose') }
  return $BaseArgs
}

try {
  $repoRoot = Resolve-RepoRoot
  Set-Location -LiteralPath $repoRoot

  Write-Section 'Smoke E2E: context'
  Write-Host ('RepoRoot: {0}' -f $repoRoot)
  Write-Host ('Supplier: {0}' -f $Supplier)
  Write-Host ('BaseUrl : {0}' -f $BaseUrl)
  Write-Host ('Compose : {0}' -f (($ComposeFiles | ForEach-Object { $_ }) -join ', '))
  Write-Host ('Fresh   : {0}' -f [bool]$Fresh)
  Write-Host ('Build   : {0}' -f [bool]$Build)
  Write-Host ('Stale   : {0}' -f $StaleDetectorMode)

  $composeArgs = Compose-FileArgs $ComposeFiles

  Write-Section 'STEP 1. docker compose up'
  if ($Fresh) {
    Write-Host 'WARNING: -Fresh runs docker compose down -v (will wipe local volumes).' -ForegroundColor Yellow
    Invoke-External (@('docker', 'compose') + $composeArgs + @('down', '-v', '--remove-orphans')) 'docker compose down -v failed'
    Invoke-External (@('docker', 'compose') + $composeArgs + @('build')) 'docker compose build failed'
    Invoke-External (@('docker', 'compose') + $composeArgs + @('up', '-d', '--remove-orphans')) 'docker compose up failed'
  } else {
    if ($Build) { Invoke-External (@('docker', 'compose') + $composeArgs + @('build')) 'docker compose build failed' }
    Invoke-External (@('docker', 'compose') + $composeArgs + @('up', '-d', '--remove-orphans')) 'docker compose up failed'
  }

  Write-Section 'STEP 2. wait /ready'
  Wait-Ready $BaseUrl $ReadyTimeoutSec

  $psExe = 'powershell.exe'

  Write-Section 'STEP 3. run_daily_import.ps1 -WhatIf (file selection check)'
  $dryArgs = Pass-CommonVerbose @($psExe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/run_daily_import.ps1', '-Supplier', $Supplier, '-WhatIf')
  Invoke-External $dryArgs 'run_daily_import.ps1 -WhatIf failed'

  Write-Section 'STEP 4. run_daily_import.ps1 (real import)'
  $runArgs = Pass-CommonVerbose @($psExe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/run_daily_import.ps1', '-Supplier', $Supplier)
  Invoke-External $runArgs 'run_daily_import.ps1 failed'

  if ($StaleDetectorMode -ne 'skip') {
    Write-Section ('STEP 5. run_stale_detector.ps1 ({0})' -f $StaleDetectorMode)
    $sd = @($psExe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/run_stale_detector.ps1')
    if ($StaleDetectorMode -eq 'whatif') { $sd += @('-WhatIf') }
    $sd = Pass-CommonVerbose $sd
    Invoke-External $sd 'run_stale_detector.ps1 failed'
  } else {
    Write-Section 'STEP 5. run_stale_detector.ps1 (skipped)'
  }

  Write-Section 'STEP 6. SQL checks (fail-fast)'
  Assert-AtLeast 'products'          'select count(*) from products;' 1
  Assert-AtLeast 'product_prices'    'select count(*) from product_prices;' 1
  Assert-AtLeast 'inventory'         'select count(*) from inventory;' 0
  Assert-AtLeast 'inventory_history' 'select count(*) from inventory_history;' 0

  if ($RunApiSmoke) {
    Write-Section 'STEP 7. quick_smoke_check.ps1 (optional)'
    if (-not $env:API_KEY) { Fail 'RunApiSmoke specified, but API_KEY is not set in environment.' }
    $apiSmoke = Pass-CommonVerbose @($psExe, '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', 'scripts/quick_smoke_check.ps1', '-BaseUrl', $BaseUrl)
    Invoke-External $apiSmoke 'quick_smoke_check.ps1 failed'
  }

  Write-Section 'DONE'
  Write-Host 'Smoke E2E: completed successfully.' -ForegroundColor Cyan
  exit 0
}
catch {
  Fail ('Unhandled error: {0}' -f $_.Exception.Message)
}
