#requires -Version 5.1

function Test-MentatPackagedRuntime([string]$RootDir) {
    return Test-Path (Join-Path $RootDir 'runtime-manifest.json')
}

function Get-MentatRuntimeManifest([string]$RootDir) {
    $manifestPath = Join-Path $RootDir 'runtime-manifest.json'
    if (-not (Test-Path $manifestPath)) {
        throw "Packaged runtime manifest was not found: $manifestPath"
    }
    try {
        return Get-Content -LiteralPath $manifestPath -Raw | ConvertFrom-Json
    } catch {
        throw "Packaged runtime manifest is invalid: $($_.Exception.Message)"
    }
}

function Get-MentatPnpmPath {
    foreach ($name in @('pnpm.cmd', 'pnpm.exe', 'pnpm')) {
        $command = Get-Command $name -ErrorAction SilentlyContinue
        if ($command) { return $command.Source }
    }
    throw 'pnpm is not installed or not on PATH. Rerun .\install.cmd.'
}

function Invoke-MentatOpenClaw(
    [string]$RootDir,
    [string[]]$ArgsList,
    [switch]$AllowFailure
) {
    Push-Location $RootDir
    try {
        if (Test-MentatPackagedRuntime $RootDir) {
            $node = Join-Path $RootDir 'node\node.exe'
            $entry = Join-Path $RootDir 'openclaw\node_modules\openclaw\openclaw.mjs'
            if (-not (Test-Path $node)) {
                throw "The packaged Node.js runtime was not found: $node"
            }
            if (-not (Test-Path $entry)) {
                throw "The packaged OpenClaw entry point was not found: $entry"
            }
            & $node $entry @ArgsList
        } else {
            $pnpm = Get-MentatPnpmPath
            & $pnpm openclaw @ArgsList
        }
        $code = $LASTEXITCODE
        if ($code -ne 0 -and -not $AllowFailure) {
            throw "OpenClaw command failed with exit code ${code}: $($ArgsList -join ' ')"
        }
        return $code
    } finally {
        Pop-Location
    }
}
