# Mentat architecture

Mentat starts as an OpenClaw fork and adds a guarded compute control plane for temporary GPU workloads.

## First production boundary

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

1. **The model requests capabilities, not arbitrary infrastructure.** The plugin accepts a named workload profile instead of a Docker image or shell command.
2. **Spending limits are enforced outside the prompt.** Hourly price, lifetime, concurrency, and disk limits live in the Compute Manager.
3. **Every paid resource has an expiry.** The cleanup watchdog destroys expired allocations even if OpenClaw crashes or forgets.
4. **Search is low risk; rental is high risk.** Offer search and status checks may be automatic. Instance creation remains an optional OpenClaw tool and must be explicitly allowlisted.
5. **Provider credentials stay out of GitHub and OpenClaw context.** Secrets are supplied at runtime through environment variables or a secret manager.
6. **No arbitrary remote execution in milestone 1.** The first release supports search, rent, inspect, and destroy only.
7. **Vast is an adapter, not the architecture.** The internal contract is provider-neutral so RunPod, local GPUs, or another backend can be added later.

## Milestone 1

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

- `VAST_API_KEY`
- `MENTAT_COMPUTE_TOKEN`
- future model or registry credentials

A scoped Vast key for the initial service should contain only `misc`, `user_read`, `instance_read`, and `instance_write`. Billing and account-write permissions are not required for the first milestone.

## Initial workload profiles

`pytorch-smoke`
: Starts a pinned PyTorch CUDA runtime and runs `nvidia-smi`. Used only to prove the instance lifecycle.

`qwen3-8b-vllm`
: Reserved for the next milestone. It will launch an approved Vast vLLM image configured for OpenAI-compatible tool calling.

## Deliberately excluded for now

- arbitrary Docker images
- arbitrary `onstart` commands
- arbitrary SSH commands
- credit transfers
- API-key management
- automatic multi-instance scaling
- unattended rentals without an operator-defined approval policy
