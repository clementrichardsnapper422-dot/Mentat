#requires -Version 5.1
[CmdletBinding()]
param([switch]$ConfigOnly)

$ErrorActionPreference = 'Stop'
$RootDir = if ($env:MENTAT_HOME) { $env:MENTAT_HOME } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$ConfigPath = if ($env:MENTAT_CONFIG_PATH) { $env:MENTAT_CONFIG_PATH } else { Join-Path $InstallRoot 'config\config.json' }
$StateDir = Join-Path $InstallRoot 'state'
$BrokerDataDir = Join-Path $InstallRoot 'broker'
$BrokerOutLog = Join-Path $StateDir 'broker.out.log'
$BrokerErrorLog = Join-Path $StateDir 'broker.error.log'
$BrokerAdminTokenPath = Join-Path $StateDir 'broker-admin.token'

function Get-PnpmPath {
    foreach ($name in @('pnpm.cmd', 'pnpm.exe', 'pnpm')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw 'pnpm is not installed or not on PATH. Rerun .\install.cmd.'
}

function Invoke-Pnpm([string[]]$ArgsList) {
    $pnpm = Get-PnpmPath
    Push-Location $RootDir
    try {
        & $pnpm @ArgsList
        if ($LASTEXITCODE -ne 0) { throw "pnpm command failed with exit code ${LASTEXITCODE}: $($ArgsList -join ' ')" }
    } finally { Pop-Location }
}

function Resolve-Python {
    foreach ($candidate in @(
        @{ Name = 'py.exe'; Prefix = @('-3') },
        @{ Name = 'py'; Prefix = @('-3') },
        @{ Name = 'python.exe'; Prefix = @() },
        @{ Name = 'python'; Prefix = @() }
    )) {
        $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue
        if (-not $command) { continue }
        & $command.Source @($candidate.Prefix) -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)" 2>$null
        if ($LASTEXITCODE -eq 0) { return @($command.Source) + @($candidate.Prefix) }
    }
    throw 'Python 3.11 or newer is required for the Mentat broker.'
}

function New-RandomToken {
    $bytes = New-Object byte[] 32
    $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($bytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

function Protect-LocalFile([string]$Path) {
    try {
        $identity = [Security.Principal.WindowsIdentity]::GetCurrent().Name
        $acl = New-Object Security.AccessControl.FileSecurity
        $acl.SetAccessRuleProtection($true, $false)
        $rule = New-Object Security.AccessControl.FileSystemAccessRule(
            $identity,
            [Security.AccessControl.FileSystemRights]::FullControl,
            [Security.AccessControl.AccessControlType]::Allow
        )
        $acl.AddAccessRule($rule)
        Set-Acl -LiteralPath $Path -AclObject $acl
    } catch {
        Remove-Item -LiteralPath $Path -Force -ErrorAction SilentlyContinue
        throw 'Could not protect the local broker approval token with a user-only ACL.'
    }
}

function Unprotect-Secret([string]$EncryptedValue) {
    if (-not $EncryptedValue) { throw 'The encrypted Vast API key is missing. Run: mentat setup vast' }
    $secure = ConvertTo-SecureString $EncryptedValue
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Test-BrokerReady([int]$Port, [string]$ClientToken) {
    try {
        $headers = @{ Authorization = "Bearer $ClientToken" }
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/v1/models" -Headers $headers -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Start-Broker(
    [int]$Port,
    [string]$ClientToken,
    [string]$AdminToken,
    [string]$VastApiKey,
    [string]$PrimaryUpstream,
    [string]$TemplateHash
) {
    if (Test-BrokerReady $Port $ClientToken) { return }
    New-Item -ItemType Directory -Force -Path $StateDir, $BrokerDataDir | Out-Null
    Remove-Item $BrokerOutLog, $BrokerErrorLog -Force -ErrorAction SilentlyContinue
    $python = Resolve-Python
    $executable = $python[0]
    $prefix = if ($python.Count -gt 1) { @($python[1..($python.Count - 1)]) } else { @() }
    $brokerScript = Join-Path $RootDir 'scripts\mentat\broker.py'
    $parts = @($prefix) + @(
        "`"$brokerScript`"",
        '--root', "`"$RootDir`"",
        '--data-dir', "`"$BrokerDataDir`"",
        '--port', [string]$Port,
        '--parent-pid', [string]$PID
    )

    $names = @(
        'VAST_API_KEY',
        'VAST_TEMPLATE_HASH',
        'MENTAT_PRIMARY_UPSTREAM_URL',
        'MENTAT_BROKER_DATA_DIR',
        'MENTAT_BROKER_CLIENT_TOKEN',
        'MENTAT_BROKER_ADMIN_TOKEN'
    )
    $saved = @{}
    foreach ($name in $names) { $saved[$name] = [Environment]::GetEnvironmentVariable($name, 'Process') }
    try {
        $env:VAST_API_KEY = $VastApiKey
        if ($TemplateHash) { $env:VAST_TEMPLATE_HASH = $TemplateHash } else { Remove-Item Env:VAST_TEMPLATE_HASH -ErrorAction SilentlyContinue }
        $env:MENTAT_PRIMARY_UPSTREAM_URL = $PrimaryUpstream
        $env:MENTAT_BROKER_DATA_DIR = $BrokerDataDir
        $env:MENTAT_BROKER_CLIENT_TOKEN = $ClientToken
        $env:MENTAT_BROKER_ADMIN_TOKEN = $AdminToken
        $process = Start-Process -FilePath $executable -ArgumentList ($parts -join ' ') -WorkingDirectory $RootDir -WindowStyle Hidden -RedirectStandardOutput $BrokerOutLog -RedirectStandardError $BrokerErrorLog -PassThru
    } finally {
        foreach ($name in $names) {
            $old = $saved[$name]
            if ($null -eq $old) { Remove-Item "Env:$name" -ErrorAction SilentlyContinue }
            else { [Environment]::SetEnvironmentVariable($name, $old, 'Process') }
        }
    }

    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        if (Test-BrokerReady $Port $ClientToken) {
            Write-Host "Mentat broker ready on port $Port (PID $($process.Id))." -ForegroundColor Green
            return
        }
        if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Test-Path $BrokerErrorLog) { Get-Content $BrokerErrorLog -Tail 80 }
    throw 'The Mentat broker did not become ready.'
}

function Configure-ProductionSandbox {
    $sandbox = [ordered]@{
        mode = 'all'
        backend = 'docker'
        scope = 'session'
        workspaceAccess = 'rw'
        prune = [ordered]@{ idleHours = 24; maxAgeDays = 7 }
    } | ConvertTo-Json -Depth 6 -Compress
    Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.sandbox', $sandbox, '--strict-json')
    Invoke-Pnpm @('openclaw', 'config', 'set', 'tools.elevated.enabled', 'false', '--strict-json')
    Invoke-Pnpm @('openclaw', 'config', 'set', 'gateway.bind', ('loopback' | ConvertTo-Json -Compress), '--strict-json')
}

function Assert-SandboxRuntime {
    if ($env:MENTAT_PRODUCTION_MODE -eq '0') { return }
    $docker = Get-Command 'docker.exe' -ErrorAction SilentlyContinue
    if (-not $docker) { $docker = Get-Command 'docker' -ErrorAction SilentlyContinue }
    if (-not $docker) { throw 'Production mode requires Docker Desktop for OpenClaw tool isolation.' }
    & $docker.Source info *> $null
    if ($LASTEXITCODE -ne 0) { throw 'Docker Desktop is installed but not running.' }
}

if (-not (Test-Path $ConfigPath)) { throw 'Mentat is not configured. Run: mentat setup' }
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$provider = if ($config.provider) { [string]$config.provider } else { 'vast' }
$gatewayPort = if ($config.gatewayPort) { [int]$config.gatewayPort } else { 18789 }
$brokerPort = if ($config.brokerPort) { [int]$config.brokerPort } else { 18890 }

switch ($provider) {
    'vast' {
        if (-not $config.baseUrl) { throw 'The Kimi endpoint identity is missing. Run: mentat setup vast' }
        $apiKey = Unprotect-Secret ([string]$config.encryptedVastApiKey)
        $clientToken = if ($env:MENTAT_BROKER_CLIENT_TOKEN) { $env:MENTAT_BROKER_CLIENT_TOKEN } else { New-RandomToken }
        $adminToken = if ($env:MENTAT_BROKER_ADMIN_TOKEN) { $env:MENTAT_BROKER_ADMIN_TOKEN } else { New-RandomToken }
        New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
        Set-Content -LiteralPath $BrokerAdminTokenPath -Value $adminToken -Encoding ASCII -NoNewline
        Protect-LocalFile $BrokerAdminTokenPath

        $env:VLLM_API_KEY = $clientToken
        $brokerBaseUrl = "http://127.0.0.1:$brokerPort/v1"
        $providerConfig = [ordered]@{
            baseUrl = $brokerBaseUrl
            apiKey = '${VLLM_API_KEY}'
            api = 'openai-completions'
            timeoutSeconds = 2100
            models = @(
                [ordered]@{
                    id = 'mentat-auto'
                    name = 'Mentat Automatic Model Broker'
                    reasoning = $true
                    input = @('text')
                    contextWindow = 262144
                    maxTokens = 16384
                }
            )
        }
        $providerJson = $providerConfig | ConvertTo-Json -Depth 8 -Compress
        $modelRef = 'vllm/mentat-auto'
        $allowlist = [ordered]@{}
        $allowlist[$modelRef] = [ordered]@{ alias = 'Mentat Auto' }

        Write-Host 'Configuring local Mentat/OpenClaw to use the production model broker.' -ForegroundColor Cyan
        Invoke-Pnpm @('openclaw', 'config', 'set', 'models.providers.vllm', $providerJson, '--strict-json', '--merge')
        Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.models', ($allowlist | ConvertTo-Json -Depth 4 -Compress), '--strict-json', '--merge')
        Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.model.primary', ($modelRef | ConvertTo-Json -Compress), '--strict-json')
        Configure-ProductionSandbox
        Invoke-Pnpm @('openclaw', 'config', 'validate')
        Invoke-Pnpm @('openclaw', 'models', 'status')

        if ($ConfigOnly) {
            Remove-Item $BrokerAdminTokenPath -Force -ErrorAction SilentlyContinue
            return
        }

        Assert-SandboxRuntime
        Start-Broker $brokerPort $clientToken $adminToken $apiKey ([string]$config.baseUrl) ([string]$config.vastTemplateHash)

        # The Gateway and every tool process inherit only the non-spending broker client token.
        Remove-Item Env:VAST_API_KEY, Env:VAST_TEMPLATE_HASH, Env:MENTAT_PRIMARY_UPSTREAM_URL, Env:MENTAT_BROKER_ADMIN_TOKEN, Env:MENTAT_BROKER_CLIENT_TOKEN -ErrorAction SilentlyContinue
        $env:VLLM_API_KEY = $clientToken
        try {
            Invoke-Pnpm @('openclaw', 'gateway', '--port', [string]$gatewayPort, '--verbose')
        } finally {
            Remove-Item $BrokerAdminTokenPath -Force -ErrorAction SilentlyContinue
        }
    }
    'ollama-cloud' {
        Configure-ProductionSandbox
        if ($ConfigOnly) { return }
        Assert-SandboxRuntime
        $ollama = Get-Command 'ollama.exe' -ErrorAction SilentlyContinue
        if (-not $ollama) { $ollama = Get-Command 'ollama' -ErrorAction SilentlyContinue }
        if (-not $ollama) { throw 'Ollama is not installed or not on PATH.' }
        $ollamaModel = if ($config.ollamaModel) { [string]$config.ollamaModel } else { 'kimi-k2.7-code:cloud' }
        & $ollama.Source launch openclaw --model $ollamaModel
        if ($LASTEXITCODE -ne 0) { throw "Ollama exited with code $LASTEXITCODE." }
    }
    default { throw "Unsupported provider: $provider" }
}
