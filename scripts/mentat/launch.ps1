#requires -Version 5.1
[CmdletBinding()]
param([switch]$ConfigOnly)

$ErrorActionPreference = 'Stop'
$RootDir = if ($env:MENTAT_HOME) { $env:MENTAT_HOME } else { Split-Path -Parent (Split-Path -Parent $PSScriptRoot) }
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Mentat'
$ConfigPath = if ($env:MENTAT_CONFIG_PATH) { $env:MENTAT_CONFIG_PATH } else { Join-Path $InstallRoot 'config\config.json' }

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
        if ($LASTEXITCODE -ne 0) { throw "pnpm command failed with exit code $LASTEXITCODE: $($ArgsList -join ' ')" }
    } finally { Pop-Location }
}

function Unprotect-Secret([string]$EncryptedValue) {
    if (-not $EncryptedValue) { throw 'The encrypted Vast API key is missing. Run: mentat setup vast' }
    $secure = ConvertTo-SecureString $EncryptedValue
    $pointer = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
    try { return [Runtime.InteropServices.Marshal]::PtrToStringBSTR($pointer) }
    finally { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($pointer) }
}

if (-not (Test-Path $ConfigPath)) { throw 'Mentat is not configured. Run: mentat setup' }
$config = Get-Content -LiteralPath $ConfigPath -Raw | ConvertFrom-Json
$provider = if ($config.provider) { [string]$config.provider } else { 'vast' }
$modelId = if ($config.modelId) { [string]$config.modelId } else { 'moonshotai/Kimi-K2.7-Code' }
$gatewayPort = if ($config.gatewayPort) { [int]$config.gatewayPort } else { 18789 }

switch ($provider) {
    'vast' {
        if (-not $config.baseUrl) { throw 'The Vast OpenAI-compatible /v1 base URL is missing. Run: mentat setup vast' }
        $apiKey = Unprotect-Secret ([string]$config.encryptedVastApiKey)
        $env:VLLM_API_KEY = $apiKey

        $providerConfig = [ordered]@{
            baseUrl = [string]$config.baseUrl
            apiKey = '${VLLM_API_KEY}'
            api = 'openai-completions'
            timeoutSeconds = 600
            models = @(
                [ordered]@{
                    id = $modelId
                    name = 'Kimi K2.7 Code on Vast'
                    reasoning = $true
                    input = @('text')
                    contextWindow = 256000
                    maxTokens = 16384
                }
            )
        }
        $providerJson = $providerConfig | ConvertTo-Json -Depth 8 -Compress
        $modelRef = "vllm/$modelId"
        $allowlist = [ordered]@{}
        $allowlist[$modelRef] = [ordered]@{ alias = 'Kimi Vast' }
        $allowlistJson = $allowlist | ConvertTo-Json -Depth 4 -Compress
        $primaryModelJson = $modelRef | ConvertTo-Json -Compress

        Write-Host 'Configuring local Mentat/OpenClaw to use Vast-hosted vLLM.' -ForegroundColor Cyan
        Write-Host "Model: $modelId"
        Write-Host "Endpoint: $($config.baseUrl)"

        Invoke-Pnpm @('openclaw', 'config', 'set', 'models.providers.vllm', $providerJson, '--strict-json', '--merge')
        Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.models', $allowlistJson, '--strict-json', '--merge')
        Invoke-Pnpm @('openclaw', 'config', 'set', 'agents.defaults.model.primary', $primaryModelJson, '--strict-json')
        Invoke-Pnpm @('openclaw', 'config', 'validate')
        Invoke-Pnpm @('openclaw', 'models', 'status')

        if ($ConfigOnly) { return }
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
