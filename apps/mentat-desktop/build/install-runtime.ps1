#requires -Version 5.1
[CmdletBinding()]
param(
    [string]$PayloadRoot,
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$BinDir = Join-Path $InstallRoot 'bin'
$LegacyRuntimeRoot = Join-Path $InstallRoot 'runtime'

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
    Remove-Item -LiteralPath $BinDir, $LegacyRuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
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
    $endpointConfigs = @($manifest.endpoint_configs)
    if ($endpointConfigs.Count -eq 0) {
        throw 'Mentat runtime payload manifest does not declare endpoint configurations.'
    }
    $payloadPrefix = [IO.Path]::GetFullPath($PayloadRoot).TrimEnd('\') + '\'
    foreach ($endpointConfig in $endpointConfigs) {
        if (-not $endpointConfig -or [IO.Path]::IsPathRooted($endpointConfig)) {
            throw "Mentat runtime payload has an unsafe endpoint path: $endpointConfig"
        }
        $endpointPath = [IO.Path]::GetFullPath((Join-Path $PayloadRoot $endpointConfig))
        if (-not $endpointPath.StartsWith($payloadPrefix, [StringComparison]::OrdinalIgnoreCase)) {
            throw "Mentat runtime payload has an unsafe endpoint path: $endpointConfig"
        }
        if (-not (Test-Path -LiteralPath $endpointPath -PathType Leaf)) {
            throw "Mentat runtime payload is incomplete: $endpointConfig"
        }
    }
} catch {
    throw "Mentat runtime payload manifest is invalid: $($_.Exception.Message)"
}

New-Item -ItemType Directory -Force -Path $InstallRoot | Out-Null
$nonce = [Guid]::NewGuid().ToString('N')
$stagedBin = Join-Path $InstallRoot "bin-staging-$nonce"
$backupBin = Join-Path $InstallRoot "bin-backup-$nonce"
$binBackedUp = $false

try {
    New-Item -ItemType Directory -Force -Path $stagedBin | Out-Null
    $powerShellWrapper = @'
$runtimeRoot = Join-Path $env:LOCALAPPDATA 'Programs\Mentat\resources\mentat-runtime'
$env:MENTAT_HOME = $runtimeRoot
& (Join-Path $runtimeRoot 'scripts\mentat\mentat.ps1') @args
exit $LASTEXITCODE
'@
    Set-Content -LiteralPath (Join-Path $stagedBin 'mentat.ps1') -Value $powerShellWrapper -Encoding UTF8
    $cmdWrapper = @'
@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0mentat.ps1" %*
exit /b %ERRORLEVEL%
'@
    Set-Content -LiteralPath (Join-Path $stagedBin 'mentat.cmd') -Value $cmdWrapper -Encoding ASCII

    if (Test-Path -LiteralPath $BinDir) {
        Move-Item -LiteralPath $BinDir -Destination $backupBin
        $binBackedUp = $true
    }
    Move-Item -LiteralPath $stagedBin -Destination $BinDir
    Set-UserPath $BinDir $true
    Remove-Item -LiteralPath $backupBin, $LegacyRuntimeRoot -Recurse -Force -ErrorAction SilentlyContinue
} catch {
    Remove-Item -LiteralPath $stagedBin, $BinDir -Recurse -Force -ErrorAction SilentlyContinue
    if ($binBackedUp -and (Test-Path -LiteralPath $backupBin)) {
        Move-Item -LiteralPath $backupBin -Destination $BinDir
    }
    throw
}
