# Mentat model runtime

## Current default

Mentat uses this model until a compatible Kimi K3 release is available and validated:

```text
kimi-k2.7-code:cloud
```

The standard launcher command is:

```bash
ollama launch openclaw --model kimi-k2.7-code:cloud
```

Kimi K2.7 Code is hosted by Ollama Cloud. It is not downloaded as a 1.04-trillion-parameter local model and it does not require Mentat to rent a Vast.ai GPU.

## First-time setup

1. Install Ollama on the machine that will run the Mentat gateway.
2. Sign in to Ollama so the local Ollama service can access cloud models:

```bash
ollama signin
```

3. Launch and configure OpenClaw with Mentat's current model:

```bash
ollama launch openclaw --model kimi-k2.7-code:cloud
```

For non-interactive setup:

```bash
ollama launch openclaw --model kimi-k2.7-code:cloud --yes
```

The launcher configures the Ollama provider, selects the model, enables the bundled Ollama web-search integration, starts the gateway, and opens the OpenClaw interface.

## Developing the Mentat source checkout

The Ollama launcher configures the user's OpenClaw state under the normal OpenClaw data directory. After that initial configuration, stop the packaged gateway and run the gateway from this repository so code changes come from the Mentat fork:

```bash
openclaw gateway stop
corepack enable
pnpm install
pnpm openclaw setup
pnpm gateway:watch
```

Verify the model selected by the source checkout:

```bash
pnpm openclaw models status
```

If it is not selected, set the full provider-qualified model reference:

```bash
pnpm openclaw models set ollama/kimi-k2.7-code:cloud
```

Then start or restart the source gateway:

```bash
pnpm gateway:watch
```

## Repository helper

Run:

```bash
scripts/mentat/launch.sh
```

Set `MENTAT_HEADLESS=1` for non-interactive setup:

```bash
MENTAT_HEADLESS=1 scripts/mentat/launch.sh
```

The default can be overridden deliberately for testing:

```bash
MENTAT_MODEL=another-model:cloud scripts/mentat/launch.sh
```

The production default must remain `kimi-k2.7-code:cloud` until the replacement passes Mentat's validation suite.

## Secrets

Never commit Ollama credentials or `OLLAMA_API_KEY` to GitHub. Interactive `ollama signin` is preferred for a developer machine. A direct Ollama Cloud API key may be supplied through the runtime environment or a secret manager for headless deployments.

## Kimi K3 upgrade gate

Do not change the default based only on an announcement or catalog entry. The Kimi K3 migration should require:

- an exact Ollama model identifier that can be resolved by OpenClaw
- successful basic chat and streaming tests
- successful tool-calling tests
- successful repository read, edit, test, and review workflows
- acceptable latency and usage cost
- no regression in permission-gate behavior
- an explicit versioned pull request changing the default

Until those checks pass, Kimi K2.7 Code remains the stable Mentat model.