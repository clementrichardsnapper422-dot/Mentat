#requires -Version 5.1
$ErrorActionPreference = 'Stop'

$RootDir = if ($env:MENTAT_HOME) { $env:MENTAT_HOME } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$BinDir = Join-Path $InstallRoot 'bin'
$ConfigDir = Join-Path $InstallRoot 'config'
$StateDir = Join-Path $InstallRoot 'state'
$BrokerDir = Join-Path $InstallRoot 'broker'
$ConfigPath = Join-Path $ConfigDir 'config.json'
$PidPath = Join-Path $StateDir 'gateway.pid'
$BrokerPidPath = Join-Path $BrokerDir 'broker.pid'
$BrokerAdminTokenPath = Join-Path $StateDir 'broker-admin.token'
$OutLog = Join-Path $StateDir 'gateway.out.log'
$ErrorLog = Join-Path $StateDir 'gateway.error.log'
$LaunchScript = Join-Path $RootDir 'scripts\mentat\launch.ps1'
$DoctorScript = Join-Path $RootDir 'scripts\mentat\doctor.ps1'
$VastScript = Join-Path $RootDir 'scripts\mentat\vast_endpoint.py'
$BrokerShutdownScript = Join-Path $RootDir 'scripts\mentat\broker_shutdown.py'

New-Item -ItemType Directory -Force -Path $ConfigDir, $StateDir, $BrokerDir | Out-Null

function Get-CommandPath([string[]]$Names) {
    foreach ($name in $Names) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    return $null
}

function Get-PnpmPath {
    $path = Get-CommandPath @('pnpm.cmd', 'pnpm.exe', 'pnpm')
    if (-not $path) { throw 'pnpm is not installed or not on PATH. Rerun .\install.cmd.' }
    return $path
}

function Invoke-Pnpm([string[]]$ArgsList, [switch]$AllowFailure) {
    $pnpm = Get-PnpmPath
    Push-Location $RootDir
    try {
        & $pnpm @ArgsList
        $code = $LASTEXITCODE
        if ($code -ne 0 -and -not $AllowFailure) {
            throw "pnpm command failed with exit code ${code}: $($ArgsList -join ' ')"
        }
        return $code
    } finally {
        Pop-Location
    }
}

function Resolve-Python {
    $py = Get-CommandPath @('py.exe', 'py')
    if ($py) {
        & $py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return @($py, '-3') }
    }
    $python = Get-CommandPath @('python.exe', 'python')
    if ($python) {
        & $python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return @($python) }
    }
    throw 'Python 3.11 or newer is required for Vast endpoint commands.'
}

function Invoke-Python([string[]]$ArgsList) {
    $python = Resolve-Python
    $executable = $python[0]
    $prefix = @()
    if ($python.Count -gt 1) { $prefix = $python[1..($python.Count - 1)] }
    Push-Location $RootDir
    try {
        & $executable @prefix @ArgsList
        if ($LASTEXITCODE -ne 0) { throw "Python command failed with exit code $LASTEXITCODE." }
    } finally {
        Pop-Location
    }
}

function Read-Config {
    if (-not (Test-Path $ConfigPath)) { return $null }
    return Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
}

function Save-Config($Config) {
    New-Item -ItemType Directory -Force -Path $ConfigDir | Out-Null
    $Config | ConvertTo-Json -Depth 8 | Set-Content -LiteralPath $ConfigPath -Encoding UTF8
}

function Protect-Secret([Security.SecureString]$Secret) {
    return ConvertFrom-SecureString $Secret
}

function Unprotect-Secret([string]$EncryptedValue) {
    if (-not $EncryptedValue) { throw 'The encrypted Vast API key is missing. Run: mentat setup vast' }
    $secure = ConvertTo-SecureString $EncryptedValue
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Read-Value([string]$Label, [string]$Current = '') {
    if ($Current) {
        $answer = Read-Host "$Label [$Current]"
        if (-not $answer) { return $Current }
        return $answer
    }
    return Read-Host $Label
}

function New-BaseConfig($Existing) {
    return [ordered]@{
        provider = if ($Existing -and $Existing.provider) { [string]$Existing.provider } else { 'vast' }
        baseUrl = if ($Existing -and $Existing.baseUrl) { [string]$Existing.baseUrl } else { '' }
        modelId = if ($Existing -and $Existing.modelId) { [string]$Existing.modelId } else { 'moonshotai/Kimi-K2.7-Code' }
        encryptedVastApiKey = if ($Existing -and $Existing.encryptedVastApiKey) { [string]$Existing.encryptedVastApiKey } else { '' }
        vastTemplateHash = if ($Existing -and $Existing.vastTemplateHash) { [string]$Existing.vastTemplateHash } else { '' }
        gatewayPort = if ($Existing -and $Existing.gatewayPort) { [int]$Existing.gatewayPort } else { 18789 }
        brokerPort = if ($Existing -and $Existing.brokerPort) { [int]$Existing.brokerPort } else { 18890 }
        maxHourlyUsd = if ($Existing -and $Existing.maxHourlyUsd) { [double]$Existing.maxHourlyUsd } else { 32 }
        maxSessionHours = if ($Existing -and $Existing.maxSessionHours) { [double]$Existing.maxSessionHours } else { 4 }
        ollamaModel = if ($Existing -and $Existing.ollamaModel) { [string]$Existing.ollamaModel } else { 'kimi-k2.7-code:cloud' }
    }
}

function Setup-Vast {
    $existing = Read-Config
    $config = New-BaseConfig $existing
    $config.provider = 'vast'
    $defaultBaseUrl = if ($config.baseUrl) { $config.baseUrl } else { 'https://openai.vast.ai/mentat-kimi-k2-7-code/v1' }
    $config.baseUrl = Read-Value 'Kimi endpoint identity (created only after approval)' $defaultBaseUrl
    if (-not $config.baseUrl) { throw 'A Kimi endpoint identity is required.' }
    $config.baseUrl = $config.baseUrl.TrimEnd('/')
    if (-not $config.baseUrl.EndsWith('/v1')) { $config.baseUrl = "$($config.baseUrl)/v1" }
    $config.modelId = 'moonshotai/Kimi-K2.7-Code'
    $config.vastTemplateHash = Read-Value 'Vast Serverless template hash (optional until endpoint creation)' $config.vastTemplateHash

    $replaceKey = -not $config.encryptedVastApiKey
    if ($config.encryptedVastApiKey) {
        $answer = Read-Host 'Replace the saved Vast API key? [y/N]'
        $replaceKey = $answer -match '^(y|yes)$'
    }
    if ($replaceKey) {
        $secureKey = Read-Host 'Vast API key (input hidden)' -AsSecureString
        if ($secureKey.Length -eq 0) { throw 'A Vast API key is required.' }
        $config.encryptedVastApiKey = Protect-Secret $secureKey
    }

    Save-Config $config
    $env:MENTAT_HOME = $RootDir
    $env:MENTAT_CONFIG_PATH = $ConfigPath
    & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $LaunchScript -ConfigOnly
    if ($LASTEXITCODE -ne 0) { throw 'OpenClaw provider configuration failed.' }
    Write-Host 'Mentat broker is configured. No paid endpoint was started.' -ForegroundColor Green
}

function Setup-Ollama {
    if (-not (Get-CommandPath @('ollama.exe', 'ollama'))) { throw 'Ollama is not installed or not on PATH.' }
    $config = New-BaseConfig (Read-Config)
    $config.provider = 'ollama-cloud'
    Save-Config $config
    Write-Host 'Ollama Cloud is selected. Run ollama signin if needed.' -ForegroundColor Green
}

function Command-Setup([string[]]$CommandArgs) {
    $provider = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { '' }
    if (-not $provider) {
        Write-Host 'Choose the inference provider:' -ForegroundColor Cyan
        Write-Host '  1) Mentat broker with guarded Vast.ai compute'
        Write-Host '  2) Ollama Cloud (fallback)'
        $selection = Read-Host 'Selection [1]'
        if (-not $selection) { $selection = '1' }
        $provider = if ($selection -eq '2') { 'ollama-cloud' } else { 'vast' }
    }
    switch ($provider.ToLowerInvariant()) {
        'vast' { Setup-Vast }
        'ollama' { Setup-Ollama }
        'ollama-cloud' { Setup-Ollama }
        default { throw "Unknown provider: $provider" }
    }
}

function Test-GatewayProcess {
    if (-not (Test-Path $PidPath)) { return $false }
    $processId = (Get-Content -LiteralPath $PidPath -Raw).Trim()
    if (-not $processId) { return $false }
    return [bool](Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue)
}

function Test-BrokerProcess {
    if (-not (Test-Path $BrokerPidPath)) { return $false }
    $processId = (Get-Content -LiteralPath $BrokerPidPath -Raw).Trim()
    if (-not $processId) { return $false }
    return [bool](Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue)
}

function Stop-BrokerGracefully {
    $config = Read-Config
    if (-not $config -or $config.provider -ne 'vast') { return $true }
    $brokerPort = if ($config.brokerPort) { [int]$config.brokerPort } else { 18890 }
    try {
        Invoke-Python @(
            $BrokerShutdownScript,
            '--port', [string]$brokerPort,
            '--token-file', $BrokerAdminTokenPath,
            '--pid-file', $BrokerPidPath,
            '--timeout', '120'
        ) | Out-Null
        return $true
    } catch {
        Write-Warning "Graceful broker shutdown failed: $($_.Exception.Message)"
        return $false
    }
}

function Command-Start([string[]]$CommandArgs) {
    $config = Read-Config
    if (-not $config) { Command-Setup @(); $config = Read-Config }
    $foreground = ($CommandArgs -contains '--foreground') -or ($config.provider -eq 'ollama-cloud')
    $env:MENTAT_HOME = $RootDir
    $env:MENTAT_CONFIG_PATH = $ConfigPath

    if ($foreground) {
        & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $LaunchScript
        exit $LASTEXITCODE
    }
    if (Test-GatewayProcess) {
        Write-Host "Mentat is already running with PID $((Get-Content $PidPath -Raw).Trim())."
        return
    }

    Remove-Item $OutLog, $ErrorLog -Force -ErrorAction SilentlyContinue
    $powerShellExe = Get-CommandPath @('pwsh.exe', 'powershell.exe')
    if (-not $powerShellExe) { throw 'PowerShell executable was not found.' }
    $argumentLine = "-NoLogo -NoProfile -ExecutionPolicy Bypass -File `"$LaunchScript`""
    $process = Start-Process -FilePath $powerShellExe -ArgumentList $argumentLine -WorkingDirectory $RootDir -WindowStyle Hidden -RedirectStandardOutput $OutLog -RedirectStandardError $ErrorLog -PassThru
    Set-Content -LiteralPath $PidPath -Value $process.Id -Encoding ASCII
    Start-Sleep -Seconds 3
    if (Get-Process -Id $process.Id -ErrorAction SilentlyContinue) {
        Write-Host "Mentat started in the background (PID $($process.Id))." -ForegroundColor Green
        Write-Host "Logs: $OutLog"
        return
    }
    if (Test-Path $ErrorLog) { Get-Content $ErrorLog -Tail 40 }
    Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    throw 'Mentat exited during startup.'
}

function Command-Stop {
    $brokerStopped = Stop-BrokerGracefully
    Invoke-Pnpm @('openclaw', 'gateway', 'stop') -AllowFailure | Out-Null
    if (Test-Path $PidPath) {
        $processId = (Get-Content -LiteralPath $PidPath -Raw).Trim()
        if ($processId -and (Get-Process -Id ([int]$processId) -ErrorAction SilentlyContinue)) {
            & taskkill.exe /PID $processId /T /F | Out-Null
        }
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    }
    Remove-Item $BrokerAdminTokenPath -Force -ErrorAction SilentlyContinue
    if ($brokerStopped) { Write-Host 'Mentat broker cooled and stopped cleanly.' -ForegroundColor Green }
    else { Write-Warning 'The broker required forced process cleanup; verify Vast has zero warm workers.' }
    Write-Host 'Mentat stopped.'
}

function Command-Status {
    $config = Read-Config
    if (Test-GatewayProcess) {
        Write-Host "Mentat process: running (PID $((Get-Content $PidPath -Raw).Trim()))" -ForegroundColor Green
    } else {
        Write-Host 'Mentat process: not running through the Windows wrapper' -ForegroundColor Yellow
        Remove-Item $PidPath -Force -ErrorAction SilentlyContinue
    }
    if (Test-BrokerProcess) {
        Write-Host "Broker process: running (PID $((Get-Content $BrokerPidPath -Raw).Trim()))" -ForegroundColor Green
    } else {
        Write-Host 'Broker process: not running' -ForegroundColor Yellow
        Remove-Item $BrokerPidPath -Force -ErrorAction SilentlyContinue
    }
    $providerName = if ($config) { $config.provider } else { 'not configured' }
    $gatewayPort = if ($config -and $config.gatewayPort) { $config.gatewayPort } else { 18789 }
    Write-Host "Provider: $providerName"
    Write-Host "Gateway port: $gatewayPort"
    Invoke-Pnpm @('openclaw', 'gateway', 'status') -AllowFailure | Out-Null
}

function Command-Chat([string[]]$CommandArgs) {
    if ($CommandArgs.Count -gt 0) {
        Invoke-Pnpm @('openclaw', 'agent', '--message', ($CommandArgs -join ' '), '--thinking', 'high') | Out-Null
    } else {
        Invoke-Pnpm @('tui') | Out-Null
    }
}

function Command-Logs([string[]]$CommandArgs) {
    if (Test-Path $ErrorLog) {
        Write-Host '--- recent errors ---' -ForegroundColor Yellow
        Get-Content -LiteralPath $ErrorLog -Tail 40
    }
    if (-not (Test-Path $OutLog)) { New-Item -ItemType File -Path $OutLog -Force | Out-Null }
    Write-Host '--- gateway output ---' -ForegroundColor Cyan
    if ($CommandArgs -contains '--no-follow') { Get-Content -LiteralPath $OutLog -Tail 80 }
    else { Get-Content -LiteralPath $OutLog -Tail 80 -Wait }
}

function Command-Vast([string[]]$CommandArgs) {
    $config = Read-Config
    if (-not $config) { throw 'Mentat is not configured. Run: mentat setup vast' }
    $env:VAST_API_KEY = Unprotect-Secret ([string]$config.encryptedVastApiKey)
    $env:VAST_TEMPLATE_HASH = [string]$config.vastTemplateHash
    try { Invoke-Python (@($VastScript) + $CommandArgs) }
    finally {
        Remove-Item Env:VAST_API_KEY, Env:VAST_TEMPLATE_HASH -ErrorAction SilentlyContinue
    }
}

function Command-Config([string[]]$CommandArgs) {
    $action = if ($CommandArgs.Count -gt 0) { $CommandArgs[0] } else { 'path' }
    switch ($action) {
        'path' { Write-Host $ConfigPath }
        'show' {
            $config = Read-Config
            if (-not $config) { throw 'No configuration exists. Run: mentat setup' }
            if ($config.encryptedVastApiKey) { $config.encryptedVastApiKey = '*** DPAPI encrypted and redacted ***' }
            $config | ConvertTo-Json -Depth 8
        }
        'edit' {
            if (-not (Test-Path $ConfigPath)) { throw 'No configuration exists. Run: mentat setup' }
            Start-Process notepad.exe -ArgumentList "`"$ConfigPath`""
        }
        'reset' {
            Remove-Item $ConfigPath -Force -ErrorAction SilentlyContinue
            Write-Host 'Mentat configuration removed. Run: mentat setup'
        }
        default { throw 'Usage: mentat config [path|show|edit|reset]' }
    }
}

function Command-Update {
    $changes = & git.exe -C $RootDir status --porcelain
    if ($changes) { throw 'The Mentat checkout has uncommitted changes. Commit or stash them before updating.' }
    & git.exe -C $RootDir pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'git pull failed.' }
    Invoke-Pnpm @('install') | Out-Null
    Invoke-Pnpm @('ui:build') | Out-Null
    Write-Host 'Mentat is updated. Run mentat doctor to verify it.' -ForegroundColor Green
}

function Remove-UserPath([string]$PathToRemove) {
    $current = [Environment]::GetEnvironmentVariable('Path', 'User')
    if (-not $current) { return }
    $parts = $current -split ';' | Where-Object { $_ -and $_.TrimEnd('\') -ine $PathToRemove.TrimEnd('\') }
    [Environment]::SetEnvironmentVariable('Path', ($parts -join ';'), 'User')
}

function Command-Uninstall([string[]]$CommandArgs) {
    Command-Stop
    Remove-Item (Join-Path $BinDir 'mentat.cmd'), (Join-Path $BinDir 'mentat.ps1') -Force -ErrorAction SilentlyContinue
    Remove-UserPath $BinDir
    if ($CommandArgs -contains '--purge') {
        Remove-Item $ConfigDir, $StateDir, $BrokerDir -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host 'Mentat command, encrypted configuration, and local state removed.'
    } else {
        Write-Host "Mentat command removed. Configuration was kept at $ConfigDir"
    }
    Write-Host "The source checkout was not deleted: $RootDir"
}

function Command-Version {
    $package = Get-Content -LiteralPath (Join-Path $RootDir 'package.json') -Raw | ConvertFrom-Json
    $commit = (& git.exe -C $RootDir rev-parse --short HEAD 2>$null)
    Write-Host "Mentat $($package.version) ($commit)"
}

function Show-Help {
    @'
Mentat — native Windows control plane with guarded Vast inference

Usage:
  mentat <command> [options]

First run:
  mentat doctor
  mentat setup [vast|ollama-cloud]
  mentat start
  mentat chat

Everyday commands:
  mentat start [--foreground]
  mentat stop
  mentat restart
  mentat status
  mentat chat [message]
  mentat logs [--no-follow]
  mentat config [path|show|edit|reset]
  mentat doctor
  mentat update

Vast endpoint commands:
  mentat vast estimate --hourly-price 28 --hours 2
  mentat vast create --accept-test-worker-cost
  mentat vast status
  mentat vast test
  mentat vast warm
  mentat vast cool
  mentat vast destroy --confirm

Maintenance:
  mentat version
  mentat uninstall [--purge]
  mentat help
'@ | Write-Host
}

$command = if ($args.Count -gt 0) { [string]$args[0] } else { 'help' }
$commandArgs = if ($args.Count -gt 1) { @($args[1..($args.Count - 1)]) } else { @() }

try {
    switch ($command.ToLowerInvariant()) {
        'setup' { Command-Setup $commandArgs }
        'start' { Command-Start $commandArgs }
        'foreground' { Command-Start @('--foreground') }
        'stop' { Command-Stop }
        'restart' { Command-Stop; Command-Start @() }
        'status' { Command-Status }
        'chat' { Command-Chat $commandArgs }
        'logs' { Command-Logs $commandArgs }
        'vast' { Command-Vast $commandArgs }
        'config' { Command-Config $commandArgs }
        'doctor' { & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File $DoctorScript; exit $LASTEXITCODE }
        'update' { Command-Update }
        'uninstall' { Command-Uninstall $commandArgs }
        'version' { Command-Version }
        'help' { Show-Help }
        '--help' { Show-Help }
        '-h' { Show-Help }
        default { Write-Error "Unknown command: $command"; Show-Help; exit 2 }
    }
} catch {
    Write-Error $_.Exception.Message
    exit 1
}
