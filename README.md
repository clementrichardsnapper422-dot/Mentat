# Mentat

**A local AI control plane built on OpenClaw, with guarded inference and GPU infrastructure on Vast.ai.**

Mentat keeps the Gateway, tools, memory, repository access, approval gates, and user data on your computer. Its primary model can run remotely on a Vast.ai OpenAI-compatible endpoint and stream responses back to the local agent loop.

```text
Your computer
  └─ Mentat / OpenClaw
      ├─ tools, memory, approvals, GitHub, terminal
      └─ HTTPS inference request
           └─ Vast.ai endpoint
                └─ Kimi K2.7 Code
```

## Install in a few minutes

Supported by the easy installer:

- macOS
- Linux
- Windows through WSL2

Requirements:

- Git
- Node.js 24.15+ recommended, or 22.22.3+ / 25.9+
- Python 3.11+

Clone the repository and run the installer:

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

That is the normal installation path. You do not need to remember the underlying `pnpm`, OpenClaw, or Python script commands.

## What the installer does

`bash install.sh`:

1. checks Node.js, Python, Git, and the operating system
2. installs the pinned pnpm version into your user account when needed
3. installs repository dependencies
4. builds the local Control UI
5. installs the `mentat` command in `~/.local/bin`
6. creates a private local configuration file at `~/.config/mentat/env`
7. runs `mentat doctor`

It does not upload credentials or store secrets in GitHub.

Installer options:

```bash
bash install.sh --skip-ui
bash install.sh --skip-deps
bash install.sh --no-path
```

## First-time setup

Run the interactive setup wizard:

```bash
mentat setup
```

You can also select the provider directly:

```bash
mentat setup vast
mentat setup ollama-cloud
```

### Vast.ai

The wizard asks for:

- the Vast OpenAI-compatible endpoint ending in `/v1`
- the model ID, defaulting to `moonshotai/Kimi-K2.7-Code`
- a scoped Vast API key
- the Vast Serverless template hash, which may be left blank until endpoint creation

The credential is written only to:

```text
~/.config/mentat/env
```

The file is created with owner-only permissions.

### Ollama Cloud fallback

Install Ollama, sign in, then select the fallback provider:

```bash
ollama signin
mentat setup ollama-cloud
mentat start
```

This launches `kimi-k2.7-code:cloud` through Ollama Cloud. It is separate from the Vast inference route.

## Everyday use

```bash
mentat start                 # start the local Gateway in the background
mentat stop                  # stop it
mentat restart               # restart it
mentat status                # process and Gateway status
mentat chat                  # open the terminal UI
mentat chat "Review my repo" # send one message directly
mentat logs                  # follow Gateway logs
mentat doctor                # diagnose setup problems
```

Run in the foreground when debugging:

```bash
mentat start --foreground
```

## Configuration

```bash
mentat config path
mentat config show           # credentials are redacted
mentat config edit
```

The default Gateway port is `18789`.

## Vast endpoint lifecycle

Mentat includes guarded commands for the Kimi endpoint. These are explicit operator actions; the language model does not get unrestricted infrastructure control.

Estimate a session before spending:

```bash
mentat vast estimate --hourly-price 28 --hours 2
```

Create the endpoint and workergroup:

```bash
mentat vast create --accept-test-worker-cost
```

The acknowledgement is required because the initial profile may launch a complete 8×H200 worker cluster for benchmarking.

Inspect and test:

```bash
mentat vast status
mentat vast test
```

Keep one worker warm or allow scale-to-zero:

```bash
mentat vast warm
mentat vast cool
```

Destroy the endpoint and workergroup:

```bash
mentat vast destroy --confirm
```

The committed profile allows only one worker cluster and caps marketplace offers at `$32/hour`.

## Update Mentat

```bash
mentat update
```

This performs a fast-forward Git pull, installs dependencies, and rebuilds the Control UI. It refuses to update over uncommitted changes.

## Uninstall

Remove the installed command while keeping your local configuration:

```bash
mentat uninstall
```

Remove the command and local Mentat configuration:

```bash
mentat uninstall --purge
```

The source checkout is deliberately not deleted automatically.

## Troubleshooting

Start here:

```bash
mentat doctor
mentat status
mentat logs
```

Common fixes:

```bash
# The shell cannot find mentat
export PATH="$HOME/.local/bin:$PATH"

# Reinstall dependencies and the wrapper
bash install.sh

# Reconfigure the inference provider
mentat setup
```

Detailed Mentat documentation:

- [Architecture](docs/mentat/architecture.md)
- [Model runtime](docs/mentat/model-runtime.md)
- [Vast Kimi endpoint](infrastructure/vast/kimi-k2.7-code/README.md)

## Development from source

The repository is a pnpm workspace. Plain `npm install` at the repository root is not supported.

```bash
corepack enable
pnpm install
pnpm openclaw setup
pnpm gateway:watch
```

Build the distributable runtime and Control UI:

```bash
pnpm build
pnpm ui:build
```

Run the focused Mentat checks:

```bash
bash -n install.sh
bash -n scripts/mentat/install.sh
bash -n scripts/mentat/mentat.sh
bash -n scripts/mentat/doctor.sh
python3 -m py_compile scripts/mentat/vast_endpoint.py
```

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
