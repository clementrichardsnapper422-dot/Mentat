#requires -Version 5.1
[CmdletBinding()]
param([switch]$InstallCheck)

$ErrorActionPreference = 'Continue'
$RootDir = if ($env:MENTAT_HOME) { $env:MENTAT_HOME } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$BinDir = Join-Path $InstallRoot 'bin'
$ConfigPath = Join-Path $InstallRoot 'config\config.json'
$DesktopExe = Join-Path $env:LOCALAPPDATA 'Programs\Mentat\Mentat.exe'
$RegistryPath = Join-Path $RootDir 'config\model-registry.json'
$RuntimeHelpers = Join-Path $PSScriptRoot 'runtime.ps1'
$script:Failures = 0
$script:Warnings = 0

if (-not (Test-Path $RuntimeHelpers)) {
    Write-Error "Mentat runtime helpers were not found: $RuntimeHelpers"
    exit 1
}
. $RuntimeHelpers
$Packaged = Test-MentatPackagedRuntime $RootDir

function Report([string]$Status, [string]$Message) {
    $color = switch ($Status) {
        'OK' { 'Green' }
        'WARN' { 'Yellow' }
        'FAIL' { 'Red' }
        default { 'Gray' }
    }
    Write-Host ("[{0,-4}] {1}" -f $Status, $Message) -ForegroundColor $color
    if ($Status -eq 'FAIL') { $script:Failures++ }
    if ($Status -eq 'WARN') { $script:Warnings++ }
}

function Get-CommandPath([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function Test-NodeVersion([string]$NodePath) {
    try {
        $versionText = (& $NodePath --version).Trim().TrimStart('v')
        $parts = $versionText.Split('.')
        $major = [int]$parts[0]
        $minor = [int]$parts[1]
        $patch = [int]($parts[2] -replace '[^0-9].*$', '')
        return (($major -eq 22 -and ($minor -gt 22 -or ($minor -eq 22 -and $patch -ge 3))) -or
                ($major -eq 24 -and ($minor -gt 15 -or ($minor -eq 15 -and $patch -ge 0))) -or
                ($major -eq 25 -and ($minor -gt 9 -or ($minor -eq 9 -and $patch -ge 0))))
    } catch { return $false }
}

function Resolve-Python {
    $py = Get-CommandPath @('py.exe', 'py')
    if ($py) {
        & $py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return "$py -3" }
    }
    $python = Get-CommandPath @('python.exe', 'python')
    if ($python) {
        & $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return $python }
    }
    return $null
}

Write-Host 'Mentat Windows production doctor' -ForegroundColor Cyan
Write-Host "Runtime: $RootDir"
Write-Host "Config: $ConfigPath"
Write-Host "Desktop: $DesktopExe`n"

if ($env:OS -eq 'Windows_NT') { Report OK 'Native Windows detected.' } else { Report FAIL 'This doctor is for native Windows.' }
if ($PSVersionTable.PSVersion.Major -ge 5) { Report OK "PowerShell $($PSVersionTable.PSVersion)" } else { Report FAIL 'PowerShell 5.1 or newer is required.' }

if ($Packaged) {
    try {
        $manifest = Get-MentatRuntimeManifest $RootDir
        if ($manifest.schema_version -eq 1 -and $manifest.product -eq 'Mentat') {
            Report OK "Packaged Mentat runtime $($manifest.version) ($($manifest.source_commit.Substring(0, 12)))."
        } else {
            Report FAIL 'Packaged runtime manifest has an unsupported schema or product.'
        }
    } catch {
        Report FAIL $_.Exception.Message
    }

    $node = Join-Path $RootDir 'node\node.exe'
    if (Test-Path $node) {
        if (Test-NodeVersion $node) { Report OK "Bundled Node.js $(& $node --version)" }
        else { Report FAIL 'The bundled Node.js version is unsupported.' }
    } else {
        Report FAIL "Bundled Node.js was not found: $node"
    }

    foreach ($required in @(
        'openclaw\node_modules\openclaw\openclaw.mjs',
        'scripts\mentat\mentat.ps1',
        'scripts\mentat\launch.ps1',
        'scripts\mentat\broker.py',
        'scripts\mentat\testing\no_spend_acceptance.py',
        'services\model-broker\mentat_broker\__init__.py'
    )) {
        if (Test-Path (Join-Path $RootDir $required)) { Report OK "Runtime component: $required" }
        else { Report FAIL "Runtime component is missing: $required" }
    }
} else {
    foreach ($item in @(
        @{ Name = 'Git'; Commands = @('git.exe', 'git') },
        @{ Name = 'Node.js'; Commands = @('node.exe', 'node') },
        @{ Name = 'npm'; Commands = @('npm.cmd', 'npm.exe', 'npm') },
        @{ Name = 'pnpm'; Commands = @('pnpm.cmd', 'pnpm.exe', 'pnpm') }
    )) {
        $path = Get-CommandPath $item.Commands
        if ($path) { Report OK "$($item.Name): $path" } else { Report FAIL "$($item.Name) is not on PATH." }
    }
    $systemNode = Get-CommandPath @('node.exe', 'node')
    if ($systemNode) {
        if (Test-NodeVersion $systemNode) { Report OK "Supported Node.js $(& $systemNode --version)" }
        else { Report FAIL "Unsupported Node.js $(& $systemNode --version)." }
    }
    if (Test-Path (Join-Path $RootDir 'package.json')) { Report OK 'Mentat source checkout found.' }
    else { Report FAIL 'package.json was not found in the Mentat source directory.' }
    if (Test-Path (Join-Path $RootDir 'node_modules')) { Report OK 'Node dependencies are installed.' }
    else { Report WARN 'node_modules is missing; rerun .\install.cmd.' }
}

$python = Resolve-Python
if ($python) { Report OK "Python 3.11+: $python" } else { Report FAIL 'Python 3.11 or newer was not found.' }

if (Test-Path $RegistryPath) {
    try {
        $registry = Get-Content -LiteralPath $RegistryPath -Raw | ConvertFrom-Json
        if ($registry.policy.require_manual_approval -and $registry.policy.require_live_offer) {
            Report OK 'Production model registry requires live offers and manual approval.'
        } else { Report FAIL 'Model registry production approval gates are disabled.' }
    } catch { Report FAIL "Model registry is invalid JSON: $($_.Exception.Message)" }
} else { Report FAIL 'config\model-registry.json is missing.' }

if (Test-Path (Join-Path $BinDir 'mentat.cmd')) { Report OK "mentat command installed in $BinDir" }
else { Report FAIL 'mentat.cmd is not installed.' }
if (Test-Path $DesktopExe) { Report OK "Mentat desktop app installed: $DesktopExe" }
else { Report WARN 'Mentat.exe is not installed; repair the Mentat installation.' }

if (Test-Path $ConfigPath) {
    try {
        $config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
        Report OK "Provider configured: $($config.provider)"
        if ($config.provider -eq 'vast') {
            if ($config.baseUrl) { Report OK "Kimi endpoint identity: $($config.baseUrl)" } else { Report FAIL 'Kimi endpoint identity is missing.' }
            if ($config.encryptedVastApiKey) { Report OK 'Vast API key is encrypted with Windows DPAPI.' } else { Report FAIL 'Encrypted Vast API key is missing.' }
            $docker = Get-CommandPath @('docker.exe', 'docker')
            if (-not $docker) {
                Report FAIL 'Docker Desktop is required for production tool isolation.'
            } else {
                & $docker info *> $null
                if ($LASTEXITCODE -eq 0) { Report OK 'Docker sandbox runtime is available.' }
                else { Report FAIL 'Docker Desktop is installed but not running.' }
            }
        } elseif ($config.provider -eq 'ollama-cloud') {
            if (Get-CommandPath @('ollama.exe', 'ollama')) { Report OK 'Ollama is installed.' } else { Report WARN 'Ollama is not installed or not on PATH.' }
        }
    } catch {
        Report FAIL "Configuration is invalid JSON: $($_.Exception.Message)"
    }
} elseif ($InstallCheck -or $Packaged) {
    Report WARN 'Provider is not configured yet; run mentat setup after installation.'
} else {
    Report FAIL 'Provider is not configured; run mentat setup.'
}

Write-Host "`nResult: $script:Failures failure(s), $script:Warnings warning(s)."
if ($script:Failures -gt 0) { exit 1 }
exit 0
