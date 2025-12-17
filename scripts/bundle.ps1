[CmdletBinding()]
param(
  [switch]$IncludeStatic,
  [switch]$IncludePipFreeze,
  [string]$OutDir = ".\_bundles",
  [string[]]$ExtraPaths = @()
)

$ErrorActionPreference = "Stop"

function Ensure-Dir([string]$p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

function To-OsPath([string]$p) {
  if ($env:OS -eq "Windows_NT") { return ($p -replace '/', '\') }
  return $p
}

function Run-CmdUtf8([string]$cmd, [string]$outFile) {
  cmd /c "chcp 65001>nul & $cmd" | Out-File -Encoding utf8 $outFile
}

# --- Repo root ---
$root = (git rev-parse --show-toplevel).Trim()
Set-Location $root

Ensure-Dir $OutDir
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$zipName = Join-Path $OutDir "wine-assistant_analysis_bundle_$ts.zip"

# --- Staging (всё пишем/копируем сюда, чтобы не мусорить корень репо) ---
$staging = Join-Path $root "_analysis_bundle_staging"
Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $staging | Out-Null

function Copy-PreserveRelative([string]$relPath) {
  $relOs = To-OsPath $relPath
  $src = Join-Path $root $relOs
  if (-not (Test-Path $src)) { return }

  $dest = Join-Path $staging $relOs
  $destDir = Split-Path $dest -Parent
  if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
  Copy-Item -LiteralPath $src -Destination $dest -Force
}

# --- Git metadata (UTF-8) в корень staging ---
Run-CmdUtf8 "git status --porcelain=v1"          (Join-Path $staging "bundle_git_status.txt")
Run-CmdUtf8 "git diff"                           (Join-Path $staging "bundle_git_diff.txt")
Run-CmdUtf8 "git diff --staged"                  (Join-Path $staging "bundle_git_diff_staged.txt")
Run-CmdUtf8 "git diff --stat"                    (Join-Path $staging "bundle_git_diff_stat.txt")
Run-CmdUtf8 "git diff --staged --stat"           (Join-Path $staging "bundle_git_diff_staged_stat.txt")
Run-CmdUtf8 "git ls-files -o --exclude-standard" (Join-Path $staging "bundle_git_untracked.txt")
Run-CmdUtf8 "git log -n 80 --decorate --oneline" (Join-Path $staging "bundle_git_log.txt")
Run-CmdUtf8 "git rev-parse HEAD"                 (Join-Path $staging "bundle_git_head.txt")
Run-CmdUtf8 "git branch -vv"                     (Join-Path $staging "bundle_git_branches.txt")
Run-CmdUtf8 "git remote -v"                      (Join-Path $staging "bundle_git_remotes.txt")

try { (python -V 2>&1) | Out-File -Encoding utf8 (Join-Path $staging "bundle_python_version.txt") } catch {}
if ($IncludePipFreeze) {
  try { (pip freeze 2>&1) | Out-File -Encoding utf8 (Join-Path $staging "bundle_pip_freeze.txt") } catch {}
}

# --- Tracked files + exclusions ---
$tracked = git ls-files

$excludeRegex = @(
  '^\.venv/', '^\.pytest_cache/', '^\.ruff_cache/', '^htmlcov/', '^logs/', '^smoke_artifacts/', '^backups/',
  '^\.env$', '^\.env\..+',
  '\.(pem|key|pfx)$'
)
if (-not $IncludeStatic) { $excludeRegex += '^static/' }

function Is-Excluded([string]$p) {
  foreach ($rx in $excludeRegex) { if ($p -match $rx) { return $true } }
  return $false
}

$trackedFiltered = $tracked | Where-Object { -not (Is-Excluded $_) }

# --- Extras (если существуют) ---
$defaultExtras = @(
  "project-structure.txt",
  "project-structure-auto.txt",
  "project-files.tracked.txt",
  "ls_root.txt",
  "must-have-check.txt",
  "ls_api.txt","ls_api_templates.txt",
  "ls_db.txt","ls_db_migrations.txt",
  "ls_etl.txt","ls_scripts.txt",
  "ls_docs.txt","ls_docs_dev.txt",
  "ls_observability.txt","ls_github.txt","ls_tests.txt","ls_hooks.txt"
) | Where-Object { Test-Path (Join-Path $root (To-OsPath $_)) }

$extraUser = @()
foreach ($p in $ExtraPaths) {
  $pp = To-OsPath $p
  if (Test-Path (Join-Path $root $pp)) { $extraUser += $p }
}

# --- Copy files into staging ---
$all = @()
$all += $trackedFiltered
$all += $defaultExtras
$all += $extraUser
$all = $all | Sort-Object -Unique

# manifest
$all | Out-File -Encoding utf8 (Join-Path $staging "bundle_included_files.txt")

foreach ($p in $all) { Copy-PreserveRelative $p }

# --- Pack with tar if available (forward slashes inside zip) ---
$tar = Get-Command tar -ErrorAction SilentlyContinue
if ($null -ne $tar) {
  tar -a -c -f $zipName -C $staging .
} else {
  Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zipName -Force
}

# --- Cleanup ---
Remove-Item $staging -Recurse -Force

Write-Host "OK: $zipName"
