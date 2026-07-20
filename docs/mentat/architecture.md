# Mentat architecture

Mentat starts as an OpenClaw fork. Its first primary model is Kimi K2.7 Code through Ollama Cloud, while a separate guarded compute control plane handles temporary GPU workloads on Vast.ai.

## Primary model path

```text
Mentat source checkout
    -> OpenClaw Gateway and agent runtime
    -> Ollama provider
    -> Ollama Cloud
    -> kimi-k2.7-code:cloud
```

The initial model is configured with:

```bash
ollama launch openclaw --model kimi-k2.7-code:cloud
```

This is a hosted cloud model. It does not run on a Vast.ai instance and does not consume the Vast compute budget. Vast remains available for future self-hosted models, isolated GPU jobs, evaluation workloads, and a possible Kimi K3 deployment.

## Temporary compute boundary

```text
OpenClaw agent
    -> vast-compute tool plugin
    -> authenticated localhost Compute Manager
    -> policy and budget checks
    -> Vast.ai Python SDK
    -> temporary GPU instance
```

The OpenClaw plugin never receives the Vast API key. The Python Compute Manager owns provider credentials, validates every request, re-checks marketplace prices immediately before rental, records allocations, and destroys expired instances independently of the language model.

## Design rules

1. **The primary model and GPU compute are separate systems.** Kimi K2.7 Code is reached through Ollama Cloud. Vast is used only when a task explicitly needs rented GPU infrastructure.
2. **The model requests capabilities, not arbitrary infrastructure.** The compute plugin accepts a named workload profile instead of a Docker image or shell command.
3. **Spending limits are enforced outside the prompt.** Hourly price, lifetime, concurrency, and disk limits live in the Compute Manager.
4. **Every paid compute resource has an expiry.** The cleanup watchdog destroys expired allocations even if OpenClaw crashes or forgets.
5. **Search is low risk; rental is high risk.** Offer search and status checks may be automatic. Instance creation remains an optional OpenClaw tool and must be explicitly allowlisted.
6. **Provider credentials stay out of GitHub and OpenClaw context.** Secrets are supplied at runtime through local credential stores, environment variables, or a secret manager.
7. **No arbitrary remote execution in the first compute milestone.** The first release supports search, rent, inspect, and destroy only.
8. **Vast is an adapter, not the architecture.** The internal contract is provider-neutral so RunPod, local GPUs, or another backend can be added later.

## Model milestone

- Use `kimi-k2.7-code:cloud` as Mentat's default coding and agentic model.
- Keep the model identifier in one documented runtime setting so it can be replaced cleanly.
- Verify the selected model with OpenClaw before beginning long-running agent work.
- Replace the model with Kimi K3 when a compatible Ollama model identifier becomes available and passes Mentat's tool-use tests.
- Do not automatically switch models merely because a new name appears in a provider catalog.

## Compute milestone 1

- Search verified, rentable Vast offers.
- Filter by GPU count and maximum hourly price.
- Revalidate the selected offer before rental.
- Launch only an approved workload profile.
- Persist the allocation and expiry locally.
- Report instance state.
- Destroy instances manually or automatically on expiry.
- Validate the Python policy layer and OpenClaw plugin in CI.

## Runtime secrets

The following values must never be committed:

- Ollama sign-in credentials or `OLLAMA_API_KEY`
- `VAST_API_KEY`
- `MENTAT_COMPUTE_TOKEN`
- future model or registry credentials

A scoped Vast key for the initial service should contain only `misc`, `user_read`, `instance_read`, and `instance_write`. Billing and account-write permissions are not required for the first compute milestone.

## Initial workload profiles

`pytorch-smoke`
: Starts a pinned PyTorch CUDA runtime and runs `nvidia-smi`. Used only to prove the Vast instance lifecycle.

Future model-serving profiles must use pinned, approved images and must not accept an agent-supplied Docker image or startup command.

## Deliberately excluded for now

- arbitrary Docker images
- arbitrary `onstart` commands
- arbitrary SSH commands
- credit transfers
- API-key management
- automatic multi-instance scaling
- unattended rentals without an operator-defined approval policy
- automatic model upgrades without validation