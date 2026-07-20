# Mentat model and compute broker

Mentat does not send every task directly to a fixed Kimi endpoint anymore. OpenClaw talks to a local OpenAI-compatible broker at `http://127.0.0.1:18890/v1`.

```text
Mentat.exe / OpenClaw
        |
        v
Local Mentat broker
  - classify task deterministically
  - read model registry
  - read local benchmark history
  - search live Vast offers
  - calculate estimated session cost
  - require approval before new paid compute
  - reuse an approved session
  - cool idle endpoints
  - fail over to an already-approved fallback
        |
        v
Selected model endpoint on Vast.ai
```

## Safety rule

A language model never receives unrestricted authority to rent GPUs. A new paid endpoint or warm worker requires a local decision with explicit approval. Automatic reuse is allowed only while an approved session is active and inside the configured time and cost caps.

## Registry

`config/model-registry.json` is the versioned policy registry. It defines:

- model identity and display name
- supported task classes and capabilities
- context length
- minimum GPU count and VRAM
- per-model hourly cap
- endpoint profile and local state file
- deterministic fallback chain
- conservative bootstrap quality prior
- minimum benchmark samples before measured quality replaces the prior

The bootstrap quality values are routing priors. They are not represented as external benchmark results.

The initial registry contains:

- Kimi K2.7 Code as the quality-first model for high-risk, visual, and repository-scale work
- Qwen3 Coder 30B A3B as the value coding model
- DeepSeek Coder V2 Lite as a low-cost candidate for simple or general tasks that do not require tool calling

## Deterministic routing

The router uses observable inputs rather than asking a weaker model to decide:

- image attachment present
- tool calling required
- estimated context size
- code/repository language in the request
- production, credential, financial, or security risk terms
- configured quality tier
- local measured quality
- live compatible GPU price
- reliability threshold
- hourly and total cost limits

Selection works in two stages:

1. filter out models that do not satisfy capability, context, quality-tier, and budget requirements
2. choose the lowest estimated-cost model within the task-class quality gap from the best eligible model

For high-risk and visual tasks the allowed quality gap is zero. Mentat therefore stays on the strongest eligible model unless another model has equally strong measured results.

## Vast offer discovery

The broker searches verified, rentable, currently available on-demand offers. It filters by:

- GPU count
- per-GPU VRAM
- approved GPU names when the model requires them
- reliability
- model-specific hourly cap
- global hourly cap

Offer results are cached briefly so one prompt does not hammer the Vast API.

## Benchmarks

The broker stores decisions, runtime measurements, user-supplied quality ratings, and endpoint sessions in a local SQLite database:

```text
Windows: %LOCALAPPDATA%\Mentat\broker\broker.sqlite3
Unix:   ~/.config/mentat/broker/broker.sqlite3
```

Automatic records include success, latency, tokens per second when reported, hourly price, and estimated task cost. Quality remains empty until a test or user rating supplies it.

Post a rated benchmark locally:

```json
POST /v1/benchmarks
{
  "model_id": "qwen3-coder-30b",
  "task_class": "code",
  "success": true,
  "latency_ms": 4200,
  "tokens_per_second": 31.5,
  "hourly_usd": 2.40,
  "total_cost_usd": 0.62,
  "quality_score": 0.93,
  "notes": "Completed repository test suite without correction"
}
```

After the configured minimum sample count, the measured average quality replaces the bootstrap prior for that model and task class.

## Approval and reuse

When no approved session exists, the original chat request waits while the decision is shown inside Mentat. Approving it creates or warms the selected endpoint. The request continues when the endpoint is ready.

An approved endpoint is reused until either:

- the maximum session window expires
- it remains idle longer than the configured idle timeout
- the user explicitly stops Mentat
- the endpoint fails

The default idle timeout is 30 minutes. Vast endpoints are cooled to scale-to-zero rather than left warm indefinitely.

## Fallbacks

Fallbacks are deterministic and registry-defined. The broker only falls back to an endpoint that already has an approved active session. It does not silently launch a second paid cluster because the first model failed.

## Desktop decision center

The Windows app polls the local broker for pending approvals. A new pending decision opens **Mentat Compute Decisions**, showing:

- task preview and classification
- selected model
- quality score and whether it is provisional or measured
- live GPU offer and reliability
- hourly price
- estimated duration and total cost
- reasons for selection
- fallback chain
- Approve and Reject controls

Open it manually with **Mentat → Compute Decisions** or `Ctrl+Shift+D`.

## Local endpoints

- `GET /health`
- `GET /v1/registry`
- `GET /v1/models`
- `POST /v1/plan`
- `GET /v1/decisions`
- `POST /v1/decisions/{id}/approve`
- `POST /v1/decisions/{id}/reject`
- `GET /v1/offers?model=qwen3-coder-30b`
- `GET /v1/benchmarks`
- `POST /v1/benchmarks`
- `GET /v1/sessions`
- `POST /v1/chat/completions`
- `GET /ui/decisions`

The server binds to `127.0.0.1` only. It is not intended to be exposed to the public internet.
