#requires -Version 5.1
[CmdletBinding()]
param(
    [switch]$SkipDeps,
    [switch]$SkipUI,
    [switch]$SkipDesktop,
    [switch]$NoPath,
    [Alias('h')][switch]$Help
)

$ErrorActionPreference = 'Stop'
$PnpmVersion = '11.2.2'
$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$BinDir = Join-Path $InstallRoot 'bin'
$ConfigDir = Join-Path $InstallRoot 'config'
$StateDir = Join-Path $InstallRoot 'state'
$NpmPrefix = Join-Path $InstallRoot 'npm'
$DesktopDir = Join-Path $RootDir 'apps\mentat-desktop'
$DesktopDistDir = Join-Path $DesktopDir 'dist'

function Show-Usage {
    @'
Install Mentat natively on Windows.

Usage:
  .\install.cmd [options]
  powershell -ExecutionPolicy Bypass -File .\install.ps1 [options]

Options:
  -SkipDeps      Do not run pnpm install
  -SkipUI        Do not build the local Control UI
  -SkipDesktop   Do not build or install Mentat.exe
  -NoPath        Do not add Mentat to the user PATH
  -Help          Show this help
'@ | Write-Host
}

function Write-Step([string]$Message) {
    Write-Host "`n==> $Message" -ForegroundColor Cyan
}

function Fail([string]$Message) {
    throw "Mentat install error: $Message"
}

function Get-CommandPath([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function Add-UserPath([string]$PathToAdd) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    $parts = @()
    if ($current) { $parts = $current -split ';' | Where-Object { $_ } }
    if (-not ($parts | Where-Object { $_.TrimEnd('\') -ieq $PathToAdd.TrimEnd('\') })) {
        $newValue = (($parts + $PathToAdd) -join ';')
        [Environment]::SetEnvironmentVariable('Path', $newValue, 'User')
    }
    if (-not (($env:Path -split ';') | Where-Object { $_.TrimEnd('\') -ieq $PathToAdd.TrimEnd('\') })) {
        $env:Path = "$PathToAdd;$env:Path"
    }
}

function Test-NodeVersion {
    $versionText = (& node --version).Trim().TrimStart('v')
    $parts = $versionText.Split('.')
    if ($parts.Count -lt 3) { return $false }
    $major = [int]$parts[0]
    $minor = [int]$parts[1]
    $patch = [int]($parts[2] -replace '[^0-9].*$', '')
    return (($major -eq 22 -and ($minor -gt 22 -or ($minor -eq 22 -and $patch -ge 3))) -or
            ($major -eq 24 -and ($minor -gt 15 -or ($minor -eq 15 -and $patch -ge 0))) -or
            ($major -eq 25 -and ($minor -gt 9 -or ($minor -eq 9 -and $patch -ge 0))))
}

function Resolve-Python {
    $py = Get-CommandPath @('py.exe', 'py')
    if ($py) {
        & $py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) { return @($py, '-3') }
    }
    $python = Get-CommandPath @('python.exe', 'python')
    if ($python) {
        & $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
        if ($LASTEXITCODE -eq 0) { return @($python) }
    }
    return $null
}

if ($Help) {
    Show-Usage
    exit 0
}

if ($env:OS -ne 'Windows_NT') {
    Fail 'This installer is for native Windows. Use bash install.sh on macOS or Linux.'
}

foreach ($required in @('git.exe', 'node.exe', 'npm.cmd')) {
    if (-not (Get-CommandPath @($required))) { Fail "$required is required and must be on PATH." }
}

if (-not (Test-NodeVersion)) {
    Fail "Unsupported Node.js $(& node --version). Use Node 24.15+ (recommended), 22.22.3+, or 25.9+."
}

$pythonCommand = Resolve-Python
if (-not $pythonCommand) {
    Fail 'Python 3.11 or newer is required. Install it from python.org and enable Add Python to PATH.'
}

$npm = Get-CommandPath @('npm.cmd', 'npm.exe', 'npm')
if (-not $npm) { Fail 'npm is required and must be on PATH.' }

New-Item -ItemType Directory -Force -Path $BinDir, $ConfigDir, $StateDir, $NpmPrefix | Out-Null
Add-UserPath $NpmPrefix

Write-Step "Preparing pnpm $PnpmVersion"
$pnpm = Get-CommandPath @('pnpm.cmd', 'pnpm.exe', 'pnpm')
if (-not $pnpm) {
    $corepack = Get-CommandPath @('corepack.cmd', 'corepack.exe', 'corepack')
    if ($corepack) {
        try {
            & $corepack prepare "pnpm@$PnpmVersion" --activate | Out-Null
        } catch {
            Write-Warning 'Corepack could not activate pnpm; using a user-local npm install instead.'
        }
        $pnpm = Get-CommandPath @('pnpm.cmd', 'pnpm.exe', 'pnpm')
    }
}
if (-not $pnpm) {
    & $npm install --global --prefix $NpmPrefix "pnpm@$PnpmVersion"
    if ($LASTEXITCODE -ne 0) { Fail 'pnpm installation failed.' }
    $pnpm = Get-CommandPath @('pnpm.cmd', 'pnpm.exe', 'pnpm')
}
if (-not $pnpm) { Fail "pnpm could not be installed into $NpmPrefix." }

if (-not $SkipDeps) {
    Write-Step 'Installing Mentat dependencies'
    Push-Location $RootDir
    try {
        & $pnpm install
        if ($LASTEXITCODE -ne 0) { Fail 'pnpm install failed.' }
    } finally { Pop-Location }
}

if (-not $SkipUI) {
    Write-Step 'Building the local Control UI'
    Push-Location $RootDir
    try {
        & $pnpm ui:build
        if ($LASTEXITCODE -ne 0) { Fail 'Control UI build failed.' }
    } finally { Pop-Location }
}

Write-Step 'Installing the mentat command'
$escapedRoot = $RootDir.Replace("'", "''")
$powerShellWrapper = @"
`$env:MENTAT_HOME = '$escapedRoot'
& "`$env:MENTAT_HOME\scripts\mentat\mentat.ps1" @args
exit `$LASTEXITCODE
"@
Set-Content -LiteralPath (Join-Path $BinDir 'mentat.ps1') -Value $powerShellWrapper -Encoding UTF8

$cmdWrapper = @'
@echo off
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0mentat.ps1" %*
exit /b %ERRORLEVEL%
'@
Set-Content -LiteralPath (Join-Path $BinDir 'mentat.cmd') -Value $cmdWrapper -Encoding ASCII

if (-not $NoPath) { Add-UserPath $BinDir }

if (-not $SkipDesktop) {
    if (-not (Test-Path (Join-Path $DesktopDir 'package.json'))) {
        Fail "Desktop package was not found at $DesktopDir."
    }

    Write-Step 'Installing Mentat desktop packaging dependencies'
    Push-Location $DesktopDir
    try {
        & $npm install --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { Fail 'Desktop npm install failed.' }

        & $npm run check
        if ($LASTEXITCODE -ne 0) { Fail 'Desktop syntax validation failed.' }

        Write-Step 'Building Mentat.exe and its Windows installer'
        & $npm run dist
        if ($LASTEXITCODE -ne 0) { Fail 'Mentat desktop build failed.' }
    } finally { Pop-Location }

    $desktopInstaller = Get-ChildItem -Path $DesktopDistDir -Filter 'Mentat-Setup-*.exe' -File |
        Sort-Object LastWriteTime -Descending |
        Select-Object -First 1
    if (-not $desktopInstaller) { Fail 'The Mentat desktop installer was not produced.' }

    Write-Step 'Installing the Mentat desktop application'
    $installerProcess = Start-Process -FilePath $desktopInstaller.FullName -ArgumentList '/S' -Wait -PassThru
    if ($installerProcess.ExitCode -ne 0) {
        Fail "Mentat desktop installer failed with exit code $($installerProcess.ExitCode)."
    }
}

Write-Step 'Checking the installation'
& powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $RootDir 'scripts\mentat\doctor.ps1') -InstallCheck

Write-Host @"

Mentat is installed natively on Windows. 🧠

Next:
  1. Open a new PowerShell window.
  2. Run: mentat setup
  3. Launch Mentat from the Desktop or Start Menu.

Command-line alternatives:
  mentat start
  mentat chat

Local encrypted settings are stored in:
  $ConfigDir

Useful commands:
  mentat doctor
  mentat help
"@
