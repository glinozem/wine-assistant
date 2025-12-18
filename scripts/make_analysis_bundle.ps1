[CmdletBinding()]
param(
  [switch]$IncludeStatic,
  [switch]$IncludePipFreeze,
  [string]$OutDir = ".",
  [string[]]$ExtraPaths = @()
)

$ErrorActionPreference = "Stop"

function Write-Utf8File([string]$path, [string]$content) {
  $content | Out-File -Encoding utf8 -FilePath $path
}

function Run-CmdUtf8([string]$cmd, [string]$outFile) {
  cmd /c "chcp 65001>nul & $cmd" | Out-File -Encoding utf8 $outFile
}

function Ensure-Dir([string]$p) {
  if (-not (Test-Path $p)) { New-Item -ItemType Directory -Path $p | Out-Null }
}

# --- Repo root ---
$root = (git rev-parse --show-toplevel).Trim()
Set-Location $root

# --- Output ---
Ensure-Dir $OutDir
$ts = Get-Date -Format "yyyyMMdd_HHmmss"
$zipName = Join-Path $OutDir "wine-assistant_analysis_bundle_$ts.zip"

# --- Git metadata (UTF-8) ---
Run-CmdUtf8 "git status --porcelain=v1"          "bundle_git_status.txt"
Run-CmdUtf8 "git diff"                           "bundle_git_diff.txt"
Run-CmdUtf8 "git diff --staged"                  "bundle_git_diff_staged.txt"
Run-CmdUtf8 "git diff --stat"                    "bundle_git_diff_stat.txt"
Run-CmdUtf8 "git diff --staged --stat"           "bundle_git_diff_staged_stat.txt"
Run-CmdUtf8 "git ls-files -o --exclude-standard" "bundle_git_untracked.txt"
Run-CmdUtf8 "git log -n 80 --decorate --oneline" "bundle_git_log.txt"
Run-CmdUtf8 "git rev-parse HEAD"                 "bundle_git_head.txt"
Run-CmdUtf8 "git branch -vv"                     "bundle_git_branches.txt"
Run-CmdUtf8 "git remote -v"                      "bundle_git_remotes.txt"

# --- Python environment (optional but useful) ---
# python -V writes to stderr in some builds; capture both
try { (python -V 2>&1) | Out-File -Encoding utf8 "bundle_python_version.txt" } catch {}
if ($IncludePipFreeze) {
  try { (pip freeze 2>&1) | Out-File -Encoding utf8 "bundle_pip_freeze.txt" } catch {}
}

# --- Tracked files ---
$tracked = git ls-files

# Exclusions (relative POSIX-style paths from git ls-files)
$excludeRegex = @(
  '^\.venv/', '^\.pytest_cache/', '^\.ruff_cache/', '^htmlcov/', '^logs/', '^smoke_artifacts/', '^backups/',
  '^\.env$', '^\.env\..+'
  '\.(pem|key|pfx)$'
)

if (-not $IncludeStatic) {
  $excludeRegex += '^static/'
}

function Is-Excluded([string]$p) {
  foreach ($rx in $excludeRegex) { if ($p -match $rx) { return $true } }
  return $false
}

$trackedFiltered = $tracked | Where-Object { -not (Is-Excluded $_) }

# --- Optional “snapshot” artifacts if exist ---
$extra = @(
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
) | Where-Object { Test-Path $_ }

# Add user-specified extras (only those that exist)
$extraUser = @()
foreach ($p in $ExtraPaths) {
  if (Test-Path $p) { $extraUser += $p }
}

# --- Meta files to include ---
$meta = @(
  "bundle_git_status.txt",
  "bundle_git_diff.txt",
  "bundle_git_diff_staged.txt",
  "bundle_git_diff_stat.txt",
  "bundle_git_diff_staged_stat.txt",
  "bundle_git_untracked.txt",
  "bundle_git_log.txt",
  "bundle_git_head.txt",
  "bundle_git_branches.txt",
  "bundle_git_remotes.txt",
  "bundle_python_version.txt"
)

if ($IncludePipFreeze) {
  $meta += "bundle_pip_freeze.txt"
}

# --- Final list + manifest ---
$all = @()
$all += $trackedFiltered
$all += $extra
$all += $extraUser
$all += $meta

$all = $all | Sort-Object -Unique

# Save the inclusion list for reproducibility
$all | Out-File -Encoding utf8 "bundle_included_files.txt"
$meta += "bundle_included_files.txt"

# --- Staging folder ---
$staging = Join-Path $root "_analysis_bundle_staging"
Remove-Item $staging -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $staging | Out-Null

function Copy-PreserveRelative([string]$relPath) {
  $dest = Join-Path $staging $relPath
  $destDir = Split-Path $dest -Parent
  if (-not (Test-Path $destDir)) { New-Item -ItemType Directory -Path $destDir -Force | Out-Null }
  Copy-Item -LiteralPath $relPath -Destination $dest -Force
}

foreach ($p in $all) {
  if (Test-Path $p) { Copy-PreserveRelative $p }
}

# --- Pack ---
$tar = Get-Command tar -ErrorAction SilentlyContinue
if ($null -ne $tar) {
  # Best option: produces ZIP with forward slashes in paths
  tar -a -c -f $zipName -C $staging .
} else {
  # Fallback: works, but paths inside ZIP may contain backslashes
  Compress-Archive -Path (Join-Path $staging '*') -DestinationPath $zipName -Force
}

# --- Cleanup (staging + meta temp files created in root) ---
Remove-Item $staging -Recurse -Force
Remove-Item $meta -Force -ErrorAction SilentlyContinue

Write-Host "OK: $zipName"
