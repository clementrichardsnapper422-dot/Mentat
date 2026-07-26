#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PayloadRoot,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$RuntimeRoot = Join-Path $InstallRoot 'runtime'
$BinDir = Join-Path $InstallRoot 'bin'

function Set-UserPath([string]$PathValue, [bool]$Present) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($current) {
        $parts = @($current -split ';' | Where-Object {
            $_ -and $_.TrimEnd('\') -ine $PathValue.TrimEnd('\')
        })
    }
    if ($Present) { $parts += $PathValue }
    [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

if ($Uninstall) {
    Remove-Item -LiteralPath $RuntimeRoot, $BinDir -Recurse -Force -ErrorAction SilentlyContinue
    Set-UserPath $BinDir $false
    exit 0
}

if (-not $PayloadRoot -or -not (Test-Path -LiteralPath $PayloadRoot -PathType Container)) {
    throw "Mentat runtime payload was not found: $PayloadRoot"
}

foreach ($required in @(
    'runtime-manifest.json',
    'node\node.exe',
    'openclaw\node_modules\openclaw\openclaw.mjs',
    'scripts\mentat\runtime.ps1',
    'scripts\mentat\mentat.ps1',
    'scripts\mentat\doctor.ps1',
    'scripts\mentat\testing\no_spend_acceptance.py',
    'services\model-broker\mentat_broker\__init__.py',
    'config\model-registry.json'
)) {
    if (-not (Test-Path -LiteralPath (Join-Path $PayloadRoot $required) -PathType Leaf)) {
        throw "Mentat runtime payload is incomplete: $required"
    }
}

try {
    $manifest = Get-Content -LiteralPath (Join-Path $PayloadRoot 'runtime-manifest.json') -Raw |
        ConvertFrom-Json
    if ($manifest.schema_version -ne 1 -or $manifest.product -ne 'Mentat') {
        throw 'Mentat runtime payload manifest is unsupported.'
    }
} catch {
    throw "Mentat runtime payload manifest is invalid: $($_.Exception.Message)"
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$nonce = [Guid]::NewGuid().ToString('N')
$stagedRuntime = Join-Path $InstallRoot "runtime-staging-$nonce"
$backupRuntime = Join-Path $InstallRoot "runtime-backup-$nonce"
$runtimeBackedUp = $false

try {
    New-Item -ItemType Directory -Force -Path $stagedRuntime | Out-Null
    Get-ChildItem -LiteralPath $PayloadRoot -Force | Copy-Item -Destination $stagedRuntime -Recurse -Force
    if (Test-Path -LiteralPath $RuntimeRoot) {
        Move-Item -LiteralPath $RuntimeRoot -Destination $backupRuntime
        $runtimeBackedUp = $true
    }
    Move-Item -LiteralPath $stagedRuntime -Destination $RuntimeRoot

    New-Item -ItemType Directory -Force -Path $BinDir | Out-Null
    $powerShellWrapper = @'
$runtimeRoot = Join-Path (Split-Path -Parent $PSScriptRoot) 'runtime'
$env:MENTAT_HOME = $runtimeRoot
& (Join-Path $runtimeRoot 'scripts\mentat\mentat.ps1') @args
exit $LASTEXITCODE
'@
    Set-Content -LiteralPath (Join-Path $BinDir 'mentat.ps1') -Value $powerShellWrapper -Encoding UTF8
    $cmdWrapper = @'
@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0mentat.ps1" %*
exit /b %ERRORLEVEL%
'@
    Set-Content -LiteralPath (Join-Path $BinDir 'mentat.cmd') -Value $cmdWrapper -Encoding ASCII
    Set-UserPath $BinDir $true

    Remove-Item -LiteralPath $backupRuntime -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Remove-Item -LiteralPath $stagedRuntime -Recurse -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $RuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
    if ($runtimeBackedUp -and (Test-Path -LiteralPath $backupRuntime)) {
        Move-Item -LiteralPath $backupRuntime -Destination $RuntimeRoot
    }
    throw
}
