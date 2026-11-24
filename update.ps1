<#
.SYNOPSIS
    Windows runner for the LLMrank maintenance cycle.

.DESCRIPTION
    Same contract as daily_update.sh, but native PowerShell so it runs without
    WSL. Prints a machine-readable block an agent (or you) can act on:

      SUMMARY:      top-3 line from update_rankings.py
      MAPPING:      mapping audit result
      NEW_MODELS:   dual-board models not tracked yet
      RESULT:       ok | no-change | failed

.PARAMETER DryRun
    Compute everything, then undo the local commit this run produced.

.PARAMETER NoPull
    Work with the checkout as-is.

.PARAMETER Repo
    Repo path. Defaults to E:\LLMrank\repo.

.EXAMPLE
    .\update.ps1
    .\update.ps1 -DryRun
#>
[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NoPull,
    [string]$Repo = 'E:\LLMrank\repo'
)

$ErrorActionPreference = 'Stop'
# Native commands write notes to stderr; PS 5.1 would abort on that.
if (Get-Variable PSNativeCommandUseErrorActionPreference -ErrorAction SilentlyContinue) {
    $PSNativeCommandUseErrorActionPreference = $false
}
# Windows defaults to GBK for Python I/O; these files are UTF-8.
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

function Invoke-Py {
    param([string[]]$ArgList)
    $prev = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try { & python @ArgList 2>&1 } finally { $ErrorActionPreference = $prev }
}

function Fail {
    param([string]$Why, [int]$Code = 1)
    Write-Output 'RESULT: failed'
    Write-Output "REASON: $Why"
    exit $Code
}

if (-not (Test-Path (Join-Path $Repo '.git'))) { Fail "not a git checkout: $Repo" 2 }
Push-Location $Repo
try {
    if ($DryRun) { $env:LLMRANK_NO_PUSH = '1' }
    else { Remove-Item Env:LLMRANK_NO_PUSH -ErrorAction SilentlyContinue }

    # A crash mid-run must not brick the next one, but never discard work.
    $dirty = (git status --porcelain --untracked-files=no) -join ''
    if ($dirty) {
        $tag = 'llmrank-leftover-' + (Get-Date -Format 'yyyyMMddTHHmmssZ')
        $null = git stash push -q -m $tag
        Write-Output "NOTE: stashed leftover changes as '$tag'"
    }

    if (-not $NoPull) {
        $null = git pull --ff-only --quiet 2>$null
        if ($LASTEXITCODE -ne 0) {
            Write-Output 'NOTE: git pull failed; continuing on local checkout'
        }
    }

    Write-Output '=== audit_mappings.py ==='
    $audit = Invoke-Py @('audit_mappings.py')
    $auditCode = $LASTEXITCODE
    $audit | Where-Object { $_ -notmatch 'fetch ok|snapshot dated' } | ForEach-Object { Write-Output $_ }
    $auditVerdict = ($audit | Select-String -Pattern '^RESULT:').Line

    Write-Output ''
    Write-Output '=== update_rankings.py ==='
    $before = git rev-parse HEAD
    $update = Invoke-Py @('update_rankings.py')
    $updateCode = $LASTEXITCODE
    $update | Where-Object { $_ -notmatch 'fetch ok|snapshot dated' } | ForEach-Object { Write-Output $_ }
    if ($updateCode -ne 0) {
        Write-Output 'CHANGED:'
        git status --porcelain
        Fail "update_rankings.py exited $updateCode"
    }

    $summary = ($update | Select-String -Pattern 'rankings updated').Line
    if (-not $summary) { $summary = '(no summary line produced)' }

    Write-Output ''
    Write-Output '=== check_model.py --new ==='
    $new = Invoke-Py @('check_model.py', '--new')
    $new | Where-Object { $_ -notmatch 'fetch ok|snapshot dated' } | ForEach-Object { Write-Output $_ }

    Write-Output ''
    Write-Output "SUMMARY: $summary"
    if ($auditVerdict) { Write-Output "MAPPING: $auditVerdict" }

    if ($DryRun) {
        Write-Output 'CHANGED (dry-run, local commit undone):'
        $null = git reset --quiet --hard $before
        git status --porcelain
        Write-Output 'RESULT: ok'
        exit 0
    }

    Write-Output 'CHANGED:'
    $ahead = git log origin/main..HEAD --oneline 2>$null
    if ($ahead) {
        $ahead | ForEach-Object { Write-Output "  $_" }
        Write-Output 'RESULT: ok'
    }
    else {
        Write-Output '  (none)'
        Write-Output 'RESULT: no-change'
    }
}
finally {
    Pop-Location
}
