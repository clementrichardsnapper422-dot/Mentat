# Mentat model runtime

## Production topology

Mentat runs the OpenClaw Gateway, tools, memory, repository access, and approval system on the operator's local PC. Model inference runs remotely on a Vast.ai vLLM endpoint.

```text
Local PC
  Mentat/OpenClaw Gateway
      -> HTTPS OpenAI-compatible request
      -> Vast.ai endpoint
      -> vLLM or SGLang workers
      -> moonshotai/Kimi-K2.7-Code
      -> streamed response tokens
      -> local Mentat agent loop
```

The Vast API key authenticates requests and infrastructure operations. Vast does not sell a separate bundle of Kimi tokens. The rented or serverless GPUs generate the tokens by running the model.

## Current model

Until Kimi K3 is available and passes the Mentat validation suite, the intended self-hosted model is:

```text
moonshotai/Kimi-K2.7-Code
```

This is distinct from Ollama's hosted alias:

```text
kimi-k2.7-code:cloud
```

The `:cloud` alias sends inference to Ollama Cloud. It does not use the Vast endpoint.

## Hardware reality

Kimi K2.7 Code is a very large mixture-of-experts model with about 1 trillion total parameters and 32 billion activated parameters. The official Moonshot deployment example uses one node with eight H200 GPUs and tensor parallelism 8. It also requires the Kimi tool-call and reasoning parsers.

Official deployment guidance:

```bash
vllm serve "$MODEL_PATH" \
  -tp 8 \
  --mm-encoder-tp-mode data \
  --trust-remote-code \
  --tool-call-parser kimi_k2 \
  --reasoning-parser kimi_k2
```

This should not be treated like a cheap single-RTX-4090 workload. Before making it Mentat's always-on endpoint, benchmark startup time, tokens per second, context limits, and hourly cost.

## Configure the local Mentat checkout

Create the Vast vLLM endpoint first, then set the runtime values locally. Never commit the actual key.

```bash
export MENTAT_PROVIDER=vast
export MENTAT_VLLM_BASE_URL="https://openai.vast.ai/<ENDPOINT_NAME>"
export VAST_API_KEY="<YOUR_SCOPED_VAST_KEY>"
export MENTAT_MODEL_ID="moonshotai/Kimi-K2.7-Code"

bash scripts/mentat/launch.sh
```

The launcher:

1. keeps the Gateway and agent runtime on the local PC
2. configures OpenClaw's bundled `vllm` provider
3. points that provider at the Vast OpenAI-compatible base URL
4. stores the model route as `vllm/moonshotai/Kimi-K2.7-Code`
5. verifies model status
6. starts the local Gateway

For configuration without starting the Gateway:

```bash
MENTAT_CONFIG_ONLY=1 bash scripts/mentat/launch.sh
```

## Ollama Cloud fallback

Ollama Cloud remains useful while the Vast Kimi endpoint is being built or when the cluster cost is not justified.

```bash
ollama signin
MENTAT_PROVIDER=ollama-cloud bash scripts/mentat/launch.sh
```

That fallback launches:

```bash
ollama launch openclaw --model kimi-k2.7-code:cloud
```

It should not be confused with the Vast production route.

## Verify connectivity

After configuration:

```bash
openclaw models list --provider vllm
openclaw models status
```

For a source checkout without a global OpenClaw installation:

```bash
corepack enable
pnpm install
pnpm openclaw models list --provider vllm
pnpm openclaw models status
pnpm gateway:watch
```

## Secrets

Never commit:

- `VAST_API_KEY`
- Hugging Face download tokens
- endpoint-specific credentials
- Ollama credentials or `OLLAMA_API_KEY`
- `MENTAT_COMPUTE_TOKEN`

Use the narrowest Vast key that supports the chosen inference path. The compute-provisioning service and model-inference client should use separate scoped credentials when Vast permissions allow that separation.

## Kimi K3 upgrade gate

Do not change the default based only on a release announcement. The migration requires:

- an exact model repository or provider identifier
- a verified deployment recipe
- successful chat and streaming tests
- successful tool-calling and preserved-thinking tests
- successful repository read, edit, test, and review workflows
- acceptable latency and total serving cost
- no regression in permission-gate behavior
- an explicit versioned pull request changing the default

Until those checks pass, Kimi K2.7 Code remains the target model and Ollama Cloud remains the fallback route.
