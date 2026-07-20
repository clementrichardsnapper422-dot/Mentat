# Mentat

**A local AI control plane built on OpenClaw, with guarded inference and GPU infrastructure on Vast.ai.**

Mentat keeps the Gateway, tools, memory, repository access, approval gates, and user data on your computer. Its primary model can run remotely on a Vast.ai OpenAI-compatible endpoint and stream responses back to the local agent loop.

```text
Your computer
  └─ Mentat / OpenClaw
      ├─ tools, memory, approvals, GitHub, terminal
      ├─ Mentat.exe desktop window
      └─ HTTPS inference request
           └─ Vast.ai endpoint
                └─ Kimi K2.7 Code
```

## Install in a few minutes

First-class installers support:

- Windows 10/11 natively through PowerShell — no WSL required
- macOS
- Linux

Requirements:

- Git
- Node.js 24.15+ recommended, or 22.22.3+ / 25.9+
- Python 3.11+

## Windows — native desktop application

Open PowerShell:

```powershell
git clone https://github.com/clementrichardsnapper422-dot/Mentat.git
cd Mentat
.\install.cmd
```

The Windows installer:

1. installs Mentat's local runtime and command-line tools
2. builds the local Control UI
3. builds a native `Mentat.exe` desktop application
4. installs it per-user
5. creates Desktop and Start Menu shortcuts

`install.cmd` uses a process-only execution-policy bypass. It does not alter the permanent Windows execution policy and does not use WSL, Git Bash, or Cygwin.

Open a new PowerShell window and configure the model provider:

```powershell
mentat setup
```

Then launch **Mentat** from the Desktop or Start Menu. The application starts the local Gateway when necessary and opens the Control UI in its own native window.

Command-line chat remains available:

```powershell
mentat start
mentat chat
```

Windows installer options:

```powershell
.\install.cmd -SkipUI
.\install.cmd -SkipDeps
.\install.cmd -SkipDesktop
.\install.cmd -NoPath
```

`-SkipDesktop` keeps the native command-line installation but skips building and installing `Mentat.exe`.

The locally built Windows installer is unsigned until a code-signing certificate is configured. Windows may display an unknown-publisher notice.

See the [native Windows guide](docs/mentat/windows.md) for paths, DPAPI protection, desktop-app behavior, and troubleshooting.

## macOS and Linux

```bash
git clone https://github.com/clementrichardsnapper422-dot/Mentat.git
cd Mentat
bash install.sh
```

Open a new terminal, then run:

```bash
mentat setup
mentat start
mentat chat
```

Unix installer options:

```bash
bash install.sh --skip-ui
bash install.sh --skip-deps
bash install.sh --no-path
```

## What the installers do

The installers:

1. check Node.js, Python, Git, and the operating system
2. install the pinned pnpm version into the user account when needed
3. install repository dependencies
4. build the local Control UI
5. install one `mentat` command
6. create per-user configuration and state directories
7. run `mentat doctor`

The Windows installer additionally builds and installs the Electron desktop application unless `-SkipDesktop` is supplied.

They do not upload credentials or store secrets in GitHub.

### Local files

macOS and Linux:

```text
~/.local/bin/mentat
~/.config/mentat/
```

Windows runtime:

```text
%LOCALAPPDATA%\Mentat\bin
%LOCALAPPDATA%\Mentat\config
%LOCALAPPDATA%\Mentat\state
```

Windows desktop application:

```text
%LOCALAPPDATA%\Programs\Mentat\Mentat.exe
```

The native Windows setup encrypts the Vast API key with Windows DPAPI. The saved value can only be decrypted by the same Windows user profile on that Windows installation.

## First-time setup

Run the interactive setup wizard:

```text
mentat setup
```

Select a provider directly:

```text
mentat setup vast
mentat setup ollama-cloud
```

### Vast.ai

The wizard asks for:

- the Vast OpenAI-compatible endpoint ending in `/v1`
- the model ID, defaulting to `moonshotai/Kimi-K2.7-Code`
- a scoped Vast API key
- the Vast Serverless template hash, which may be left blank until endpoint creation

On Windows, the key is DPAPI-encrypted in `%LOCALAPPDATA%\Mentat\config\config.json`. On macOS and Linux, the local environment file is created with owner-only permissions.

### Ollama Cloud fallback

Install Ollama and sign in, then select the fallback provider:

```text
ollama signin
mentat setup ollama-cloud
mentat start
```

This launches `kimi-k2.7-code:cloud` through Ollama Cloud. It is separate from the Vast inference route.

## Desktop application behavior

The Windows `Mentat.exe` application:

- opens the local Control UI in a dedicated desktop window
- starts the local Gateway when it is not already running
- leaves an already-running Gateway alone
- stops the Gateway on exit only when the desktop app started it
- permits only the configured local Gateway origin inside the window
- opens outside links in the default browser
- disables Node.js and Electron APIs inside the web interface
- allows only one Mentat desktop instance at a time
- includes menu commands for reload, Gateway restart, logs, zoom, full screen, and developer tools

The desktop app is a secure shell around the same local Mentat Gateway. It is not a hosted website and does not move your tools or data to Electron.

## Everyday command-line use

```text
mentat start                   start the local Gateway in the background
mentat stop                    stop it
mentat restart                 restart it
mentat status                  process and Gateway status
mentat chat                    open the terminal UI
mentat chat "Review my repo"  send one message directly
mentat logs                    follow Gateway logs
mentat doctor                  diagnose setup problems
```

Run in the foreground when debugging:

```text
mentat start --foreground
```

## Configuration

```text
mentat config path
mentat config show
mentat config edit
```

Credentials are redacted from `mentat config show`. The default Gateway port is `18789`.

## Vast endpoint lifecycle

Mentat includes guarded commands for the Kimi endpoint. These are explicit operator actions; the language model does not receive unrestricted infrastructure control.

```text
mentat vast estimate --hourly-price 28 --hours 2
mentat vast create --accept-test-worker-cost
mentat vast status
mentat vast test
mentat vast warm
mentat vast cool
mentat vast destroy --confirm
```

The acknowledgement is required because the initial profile may launch a complete 8×H200 worker cluster for benchmarking. The committed profile allows only one worker cluster and caps marketplace offers at `$32/hour`.

## Update Mentat

```text
mentat update
```

This performs a fast-forward Git pull, installs dependencies, and rebuilds the Control UI. Run `install.cmd` again when desktop application code or packaging changes.

## Uninstall

Remove the command while preserving configuration:

```text
mentat uninstall
```

Remove command-line configuration and state:

```text
mentat uninstall --purge
```

The Windows desktop application is uninstalled separately from **Windows Settings → Apps → Installed apps → Mentat**. The source checkout is deliberately not deleted automatically.

## Troubleshooting

Start here:

```text
mentat doctor
mentat status
mentat logs
```

Reinstall on Windows:

```powershell
.\install.cmd
```

Reinstall on macOS or Linux:

```bash
bash install.sh
```

Detailed documentation:

- [Native Windows installation and desktop app](docs/mentat/windows.md)
- [Desktop packaging](apps/mentat-desktop/README.md)
- [Architecture](docs/mentat/architecture.md)
- [Model runtime](docs/mentat/model-runtime.md)
- [Vast Kimi endpoint](infrastructure/vast/kimi-k2.7-code/README.md)

## Development from source

The main repository is a pnpm workspace. Plain `npm install` at the repository root is not supported.

```text
corepack enable
pnpm install
pnpm openclaw setup
pnpm gateway:watch
```

Build the runtime and Control UI:

```text
pnpm build
pnpm ui:build
```

Build only the Windows desktop installer:

```powershell
cd apps\mentat-desktop
npm install
npm run dist
```

The generated installer is placed in `apps\mentat-desktop\dist`.

## Security

Mentat can execute local tools and access real repositories and accounts. Treat inbound messages as untrusted input, keep approval gates enabled for destructive or paid actions, and do not expose the Gateway publicly without following OpenClaw's security guidance.

Never commit:

- Vast API keys
- endpoint credentials
- Hugging Face tokens
- Ollama credentials
- `MENTAT_COMPUTE_TOKEN`

## OpenClaw foundation

Mentat is built from the open-source [OpenClaw](https://github.com/openclaw/openclaw) project and retains its local Gateway, tools, channels, memory, apps, plugin system, and security model.

Useful upstream documentation:

- [Getting started](https://docs.openclaw.ai/start/getting-started)
- [Gateway](https://docs.openclaw.ai/gateway)
- [Models](https://docs.openclaw.ai/concepts/models)
- [Tools](https://docs.openclaw.ai/tools)
- [Security](https://docs.openclaw.ai/gateway/security)
- [Channels](https://docs.openclaw.ai/channels)

## License

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
