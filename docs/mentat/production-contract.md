# Mentat production contract

This document is the canonical definition of the product being built. A change that violates these rules is a regression even when it appears to work.

## Product definition

Mentat is a Windows-native desktop AI operator built on OpenClaw.

- `Mentat.exe` is the primary user interface.
- OpenClaw runs locally and owns conversations, tools, memory, approvals, repositories, and local integrations.
- A local deterministic broker evaluates each task before inference.
- Vast.ai supplies remote GPU compute for approved open-weight models.
- Kimi K2.7 Code is the dependable primary model until measured evidence proves a cheaper registered model is good enough for a task class.
- The broker selects the best eligible model and compatible Vast hardware within explicit quality, capability, reliability, context, time, and cost limits.
- The user sees the model, GPU requirements, live price ceiling, estimated duration, estimated cost, reasons, and fallback policy before new paid compute begins.
- Paid endpoints are reused when still approved, cooled when idle or expired, and reconciled after crashes.
- Quality, latency, throughput, success, and cost history are recorded locally and used to improve future routing.

## Non-negotiable invariants

### Spending authority

- A language model cannot create, warm, resize, or approve paid compute.
- Every new paid session requires an authenticated local user approval.
- The actual Vast worker price cannot exceed the approved hourly ceiling.
- Only one paid model session may be active by default.
- Fallback never starts a second paid endpoint silently.
- Session duration and total estimated cost remain within policy caps.

### Credential isolation

- The Vast API key exists only in the broker process.
- The OpenClaw Gateway and tool subprocesses receive only a non-spending broker client token.
- The desktop approval credential is separate from the inference credential.
- Approval credentials never appear in URLs, logs, Git, model prompts, or tool environments.
- Local credential files are protected for the current operating-system user.

### Local security boundary

- Broker and Gateway bind to loopback by default.
- Broker inference and administration endpoints require separate authentication.
- OpenClaw tools run in the Docker sandbox in production mode.
- Elevated host escape is disabled.
- The source workspace may be mounted read/write for coding tasks, but Mentat configuration and broker credentials remain outside the mounted workspace.
- External links open in the normal browser; the Electron renderer has no Node.js access.

### Routing correctness

- Routing is based on the latest user intent plus observable task requirements, not a weaker model's opinion.
- Short follow-ups such as `go` retain the prior user instruction.
- System prompts and advertised tool descriptions do not contaminate task classification.
- Full messages, tool schemas, and output reservation count toward context requirements.
- A fallback must independently satisfy the original task class, capabilities, context, risk, and quality tier.
- Vast Serverless is treated as text-only until a validated vision route is added.
- Bootstrap quality values are conservative priors, not benchmark claims.
- A cheaper model is not automatically promoted until it has the required number of rated local samples.

### Lifecycle correctness

- Endpoint creation is idempotent and reconciles exact-name resources after ambiguous network outcomes.
- Non-idempotent create requests are never blindly retried.
- Local endpoint state is written atomically.
- Duplicate or orphaned Vast resources cause a fail-closed error.
- A restarted broker cools saved endpoints before accepting new approvals.
- Idle, expired, or stale-warming endpoints are cooled.
- Broker shutdown attempts to cool every saved Vast endpoint.

### Data integrity

- Broker history is stored locally in SQLite with durable settings.
- Database corruption fails startup rather than silently discarding history.
- Runtime measurements and human/test quality ratings are separate.
- Unrated runs never count toward model quality promotion.
- Vast billing remains the final source of truth; Mentat's task cost is an estimate.

## Supported initial model registry

1. **Kimi K2.7 Code** — primary for high-risk, tool-heavy, long-context, and repository-scale work.
2. **Qwen3 Coder 30B A3B** — candidate lower-cost coding model after sufficient rated evidence.
3. **DeepSeek Coder V2 Lite** — candidate inexpensive model for simple and general text/code tasks after sufficient rated evidence.

Adding a model requires:

- a versioned registry entry
- a validated endpoint profile
- explicit capability and context declarations
- compatible hardware requirements
- a price cap
- a benchmark plan
- fallback tests
- no regression of the spending and credential boundaries

## Release gates

Mentat must not be described as production-ready until every gate below passes.

### Gate 0 — repository and supply chain

- repository is private and detached from the public fork network
- protected `main` branch and required checks are enabled
- dependency versions and installer artifacts are reproducible
- Windows installer is Authenticode signed
- release artifacts include checksums and provenance

### Gate 1 — no-spend local integration

- clean Windows installation succeeds
- `mentat doctor` is green
- Docker sandbox is verified from inside an actual tool execution
- Gateway environment is proven not to contain Vast or admin credentials
- broker client/admin authentication is tested end to end
- fake Vast and fake OpenAI-compatible upstream complete a full chat and tool loop
- reject, approval timeout, malformed request, restart, and shutdown paths pass

### Gate 2 — low-cost canary

- a capped inexpensive endpoint is approved through `Mentat.exe`
- actual billed rate does not exceed the displayed ceiling
- endpoint reuse works without another approval during the approved session
- rejection starts no compute
- idle and manual cooling reach zero paid workers
- forced broker/Gateway termination is recovered safely

### Gate 3 — Kimi canary

- official Kimi endpoint profile starts successfully
- tool calling and reasoning parser behavior pass
- long-context request fits the declared limit
- streaming survives normal completion and interruption
- actual latency, throughput, and billing are recorded
- four-hour and total-dollar caps are enforced

### Gate 4 — soak and failure testing

- repeated sessions run without leaked processes or stale workers
- network loss during create, warm, stream, and cool is reconciled
- disk-full and SQLite corruption behavior fail safely
- concurrent chats respect the request and paid-session limits
- Windows restart and user logoff do not leave paid workers warm
- update and rollback procedures are demonstrated

### Gate 5 — release

- all security findings are closed or explicitly accepted
- operator runbook and incident procedure are complete
- backups and recovery are tested
- release is signed, checksummed, versioned, and installed from the release artifact rather than a development checkout

## Current release blockers

At the time this contract was introduced:

- the GitHub repository is still public
- the Windows installer is unsigned
- no live Vast canary has been completed
- no full Windows no-spend integration run has been completed on the owner's machine
- no Kimi soak or billing reconciliation has been completed

Those are intentional stop signs, not documentation trivia.
