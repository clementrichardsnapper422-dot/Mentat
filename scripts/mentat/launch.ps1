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

function Unprotect-Secret([string]$EncryptedValue) {
    if (-not $EncryptedValue) { throw 'The encrypted Vast API key is missing. Run: mentat setup vast' }
    $secure = ConvertTo-SecureString $EncryptedValue
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

function Test-BrokerReady([int]$Port) {
    try {
        $response = Invoke-WebRequest -UseBasicParsing -Uri "http://127.0.0.1:$Port/health" -TimeoutSec 2
        return $response.StatusCode -eq 200
    } catch { return $false }
}

function Start-Broker([int]$Port) {
    if (Test-BrokerReady $Port) { return }
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
    $process = Start-Process -FilePath $executable -ArgumentList ($parts -join ' ') -WorkingDirectory $RootDir -WindowStyle Hidden -RedirectStandardOutput $BrokerOutLog -RedirectStandardError $BrokerErrorLog -PassThru
    for ($attempt = 0; $attempt -lt 40; $attempt++) {
        if (Test-BrokerReady $Port) {
            Write-Host "Mentat broker ready on port $Port (PID $($process.Id))." -ForegroundColor Green
            return
        }
        if (-not (Get-Process -Id $process.Id -ErrorAction SilentlyContinue)) { break }
        Start-Sleep -Milliseconds 500
    }
    if (Test-Path $BrokerErrorLog) { Get-Content $BrokerErrorLog -Tail 50 }
    throw 'The Mentat broker did not become ready.'
}

if (-not (Test-Path $ConfigPath)) { throw 'Mentat is not configured. Run: mentat setup' }
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$provider = if ($config.provider) { [string]$config.provider } else { 'vast' }
$gatewayPort = if ($config.gatewayPort) { [int]$config.gatewayPort } else { 18789 }
$brokerPort = if ($config.brokerPort) { [int]$config.brokerPort } else { 18890 }

switch ($provider) {
    'vast' {
        if (-not $config.baseUrl) { throw 'The Vast OpenAI-compatible /v1 base URL is missing. Run: mentat setup vast' }
        $apiKey = Unprotect-Secret ([string]$config.encryptedVastApiKey)
        $env:VAST_API_KEY = $apiKey
        $env:VLLM_API_KEY = 'mentat-local-broker'
        $env:MENTAT_PRIMARY_UPSTREAM_URL = [string]$config.baseUrl
        $env:MENTAT_BROKER_DATA_DIR = $BrokerDataDir
        if ($config.vastTemplateHash) { $env:VAST_TEMPLATE_HASH = [string]$config.vastTemplateHash }

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
                    input = @('text', 'image')
                    contextWindow = 262144
                    maxTokens = 16384
                }
            )
        }
        $providerJson = $providerConfig | ConvertTo-Json -Depth 8 -Compress
        $modelRef = 'vllm/mentat-auto'
        $allowlist = [ordered]@{}
        $allowlist[$modelRef] = [ordered]@{ alias = 'Mentat Auto' }
        $allowlistJson = $allowlist | ConvertTo-Json -Depth 4 -Compress
        $primaryModelJson = $modelRef | ConvertTo-Json -Compress

        Write-Host 'Configuring local Mentat/OpenClaw to use the model and compute broker.' -ForegroundColor Cyan
        Write-Host "Broker: $brokerBaseUrl"
        Write-Host "Primary upstream: $($config.baseUrl)"

        Invoke-Pnpm @('openclaw', 'config', 'set', 'models.providers.vllm', $providerJson, '--strict-json', '--merge')
        Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.models', $allowlistJson, '--strict-json', '--merge')
        Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.model.primary', $primaryModelJson, '--strict-json')
        Invoke-Pnpm @('openclaw', 'config', 'validate')
        Invoke-Pnpm @('openclaw', 'models', 'status')

        if ($ConfigOnly) { return }
        Start-Broker $brokerPort
        Invoke-Pnpm @('openclaw', 'gateway', '--port', [string]$gatewayPort, '--verbose')
    }
    'ollama-cloud' {
        if ($ConfigOnly) { return }
        $ollama = Get-Command 'ollama.exe' -ErrorAction SilentlyContinue
        if (-not $ollama) { $ollama = Get-Command 'ollama' -ErrorAction SilentlyContinue }
        if (-not $ollama) { throw 'Ollama is not installed or not on PATH.' }
        $ollamaModel = if ($config.ollamaModel) { [string]$config.ollamaModel } else { 'kimi-k2.7-code:cloud' }
        Write-Host "Launching Ollama Cloud fallback: $ollamaModel" -ForegroundColor Cyan
        & $ollama.Source launch openclaw --model $ollamaModel
        if ($LASTEXITCODE -ne 0) { throw "Ollama exited with code $LASTEXITCODE." }
    }
    default { throw "Unsupported provider: $provider" }
}
