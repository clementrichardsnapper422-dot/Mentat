# Mentat architecture

Mentat starts as an OpenClaw fork. The Gateway, agent loop, tools, memory, repository access, and approval system run on the operator's local PC. Vast.ai provides remote GPU inference and separate temporary compute capacity.

## Primary model path

```text
Local Mentat source checkout
    -> OpenClaw Gateway and agent runtime
    -> vLLM provider
    -> Vast.ai OpenAI-compatible endpoint
    -> Kimi K2.7 Code workers
    -> streamed response tokens
    -> local tools and agent loop
```

The intended model is:

```text
moonshotai/Kimi-K2.7-Code
```

The Vast API key authenticates the endpoint. Vast does not provide a separate Kimi token allowance; the endpoint's GPUs run the model and generate response tokens.

The Ollama model `kimi-k2.7-code:cloud` is retained only as a bootstrap and fallback route. Requests made through that alias are processed by Ollama Cloud, not Vast.

## Temporary compute boundary

```text
Local OpenClaw agent
    -> vast-compute tool plugin
    -> authenticated local Compute Manager
    -> policy and budget checks
    -> Vast.ai Python SDK
    -> temporary GPU instance or job
```

The model-facing Vast route and the infrastructure-control route are separate:

- **Inference route:** OpenClaw sends OpenAI-compatible chat requests to an approved Vast endpoint.
- **Compute route:** the local Compute Manager searches, rents, inspects, and destroys Vast resources under hard policy limits.

The OpenClaw agent must never receive unrestricted infrastructure credentials. The Compute Manager owns provisioning credentials, re-checks marketplace prices before rental, records allocations, and destroys expired resources independently of the language model.

## Design rules

1. **The control plane stays local.** User data, approvals, tools, and business logic remain on the operator's PC unless an explicit tool sends data elsewhere.
2. **Inference is remote and replaceable.** Vast is the first production backend, but the OpenAI-compatible contract allows another vLLM, SGLang, or hosted provider later.
3. **Inference credentials and provisioning credentials are separate concerns.** Use separate scoped keys when the provider supports it.
4. **The model requests capabilities, not arbitrary infrastructure.** The compute plugin accepts named workload profiles instead of agent-supplied images or shell commands.
5. **Spending limits are enforced outside the prompt.** Hourly price, lifetime, concurrency, and disk limits live in the Compute Manager.
6. **Every paid compute resource has an expiry.** A deterministic watchdog destroys expired allocations even if OpenClaw crashes or forgets.
7. **Search is lower risk; rental is high risk.** Offer search and status checks may be automatic. Instance creation must be explicitly allowlisted and policy checked.
8. **Provider credentials stay out of GitHub and model context.** Secrets are supplied through local environment variables, credential files, or a secret manager.
9. **No arbitrary remote execution in the first compute milestone.** The first release supports search, rent, inspect, and destroy only.
10. **Model upgrades require validation.** Kimi K3 does not become the default merely because it appears in a catalog.

## Model milestone

- Run Mentat/OpenClaw locally.
- Configure the bundled `vllm` provider against a Vast OpenAI-compatible endpoint.
- Serve `moonshotai/Kimi-K2.7-Code` on Vast when the required cluster and budget are approved.
- Use `kimi-k2.7-code:cloud` through Ollama Cloud only as a fallback while the Vast endpoint is unavailable or uneconomical.
- Verify streaming, tool calling, preserved thinking, repository workflows, latency, and cost.
- Replace the target with Kimi K3 only after a versioned migration pull request passes the same suite.

## Kimi deployment constraint

Kimi K2.7 Code is a roughly 1-trillion-parameter mixture-of-experts model with 32 billion activated parameters. Moonshot's reference vLLM deployment uses eight H200 GPUs with tensor parallelism 8 and requires the `kimi_k2` tool-call and reasoning parsers. It is not a single-4090 deployment.

## Compute milestone 1

- Search verified, rentable Vast offers.
- Filter by GPU count and maximum hourly price.
- Revalidate the selected offer before rental.
- Launch only an approved workload profile.
- Persist the allocation and expiry locally.
- Report instance state.
- Destroy instances manually or automatically on expiry.
- Validate the Python policy layer and OpenClaw integration in CI.

## Runtime secrets

The following values must never be committed:

- `VAST_API_KEY`
- Hugging Face model-download tokens
- endpoint-specific credentials
- Ollama credentials or `OLLAMA_API_KEY`
- `MENTAT_COMPUTE_TOKEN`
- future registry or deployment credentials

## Initial workload profiles

`pytorch-smoke`
: Starts a pinned PyTorch CUDA runtime and runs `nvidia-smi`. Used only to prove the Vast instance lifecycle.

Future model-serving profiles must use pinned, approved images and fixed startup commands. They must not accept an agent-supplied Docker image or arbitrary startup command.

## Deliberately excluded for now

- arbitrary Docker images
- arbitrary `onstart` commands
- arbitrary SSH commands
- credit transfers
- API-key management
- automatic multi-instance scaling
- unattended rentals without an operator-defined approval policy
- automatic model upgrades without validation
