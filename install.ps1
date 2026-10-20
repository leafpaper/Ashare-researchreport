# ==============================================================
#  company-analysis skill - Windows installer (v8.13)
#  Mirrors install.sh. Run from the cloned repo root:
#    powershell -ExecutionPolicy Bypass -File .\install.ps1               # auto-detect CLIs on PATH
#    powershell -ExecutionPolicy Bypass -File .\install.ps1 -Target codex  # claude | codex | opencode | all
#
#  Where things go:
#    Claude Code : ~\.claude\skills\company-analysis  +  ~\.claude\agents\company-analysis\*.md
#    Codex       : ~\.agents\skills\company-analysis  +  ~\.codex\agents\*.toml
#    OpenCode    : ~\.agents\skills\company-analysis  +  ~\.config\opencode\agents\*.md
#    (Codex and OpenCode share the ~\.agents\skills copy of the skill body)
#
#  NOTE: kept ASCII-only on purpose. Windows PowerShell 5.1 reads .ps1 as the
#  system ANSI codepage unless a UTF-8 BOM is present, so non-ASCII here would
#  corrupt parsing. Keep it ASCII.
# ==============================================================
param([string]$Target = "auto")
$ErrorActionPreference = "Stop"

$Src  = $PSScriptRoot
$Home_ = $env:USERPROFILE

function Install-Body([string]$dst) {
  if (Test-Path $dst) { Remove-Item $dst -Recurse -Force }
  New-Item -ItemType Directory -Force -Path $dst | Out-Null
  foreach ($f in @("SKILL.md", "README.md", "CHANGELOG.md", "LICENSE", ".env.sample")) {
    Copy-Item (Join-Path $Src $f) -Destination $dst -Force
  }
  foreach ($dir in @("phases", "references", "assets", "scripts", "agents")) {
    Copy-Item (Join-Path $Src $dir) -Destination $dst -Recurse -Force
  }
  Get-ChildItem $dst -Recurse -Directory -Filter "__pycache__" | Remove-Item -Recurse -Force
  # verify counts against the source (never a hard-coded list)
  foreach ($pair in @(@("phases","*.md"), @("references","*.md"), @("agents","*.md"), @("scripts","*.py"), @("scripts\schemas","*.schema.json"))) {
    $want = (Get-ChildItem (Join-Path $Src $pair[0]) -Filter $pair[1]).Count
    $got  = (Get-ChildItem (Join-Path $dst $pair[0]) -Filter $pair[1]).Count
    if ($want -ne $got) { throw "copy incomplete for $($pair[0]): expected $want got $got" }
  }
  Write-Host "  skill body -> $dst"
}

switch ($Target) {
  "auto" {
    $Targets = @()
    if (Get-Command claude   -ErrorAction SilentlyContinue) { $Targets += "claude" }
    if (Get-Command codex    -ErrorAction SilentlyContinue) { $Targets += "codex" }
    if (Get-Command opencode -ErrorAction SilentlyContinue) { $Targets += "opencode" }
    if ($Targets.Count -eq 0) { $Targets = @("claude") }
  }
  "all"      { $Targets = @("claude", "codex", "opencode") }
  "claude"   { $Targets = @("claude") }
  "codex"    { $Targets = @("codex") }
  "opencode" { $Targets = @("opencode") }
  default    { throw "unknown target '$Target' (claude | codex | opencode | all)" }
}

Write-Host "================================================"
Write-Host "  company-analysis skill (Windows v8.13)"
Write-Host "  Source : $Src"
Write-Host "  Targets: $($Targets -join ', ')"
Write-Host "================================================"

$Shared = Join-Path $Home_ ".agents\skills\company-analysis"
$sharedDone = $false
foreach ($t in $Targets) {
  switch ($t) {
    "claude" {
      Install-Body (Join-Path $Home_ ".claude\skills\company-analysis")
      $a = Join-Path $Home_ ".claude\agents\company-analysis"
      New-Item -ItemType Directory -Force -Path $a | Out-Null
      Copy-Item (Join-Path $Src "agents\*.md") -Destination $a -Force
      Write-Host "  sub-agents (Claude Code) -> $a ($((Get-ChildItem $a -Filter *.md).Count))"
    }
    "codex" {
      if (-not $sharedDone) { Install-Body $Shared; $sharedDone = $true }
      $a = Join-Path $Home_ ".codex\agents"
      New-Item -ItemType Directory -Force -Path $a | Out-Null
      Copy-Item (Join-Path $Src "adapters\codex\agents\*.toml") -Destination $a -Force
      Write-Host "  sub-agents (Codex) -> $a\*.toml"
    }
    "opencode" {
      if (-not $sharedDone) { Install-Body $Shared; $sharedDone = $true }
      $a = Join-Path $Home_ ".config\opencode\agents"
      New-Item -ItemType Directory -Force -Path $a | Out-Null
      Copy-Item (Join-Path $Src "adapters\opencode\agents\*.md") -Destination $a -Force
      Write-Host "  sub-agents (OpenCode) -> $a\*.md"
    }
  }
}

Write-Host ""
Write-Host "Next steps:"
Write-Host "  1. Install deps (real Python 3.11+, NOT the Microsoft Store stub):"
Write-Host "       py -3 -m pip install --user -r <skill dir>\scripts\requirements.txt"
Write-Host "  2. Set Tushare token (A-share / HK):"
Write-Host "       [Environment]::SetEnvironmentVariable('TUSHARE_TOKEN','your_token','User')"
Write-Host "  3. Restart your agent, then:"
Write-Host "       Claude Code : /company-analysis <company> <ticker>"
Write-Host "       OpenCode    : /company-analysis <company> <ticker>   (DeepSeek: /connect deepseek first)"
Write-Host "       Codex       : `$company-analysis <company> <ticker>   (multi-agent mode must be enabled)"
Write-Host ""
Write-Host "  To pin one interpreter (e.g. a venv python.exe), set env CA_PYBIN to its full path."
Write-Host "  Per-harness notes and known limits: references\harness.md"
