# Mentat production contract

This document is the canonical definition of the product being built. A change that violates these rules is a regression even when it appears to work.

## Product definition

Mentat is a Windows-native desktop AI operator built on OpenClaw.

- `Mentat.exe` is the primary user interface.
- OpenClaw runs locally and owns conversations, tools, memory, approvals, repositories, and local integrations.
- A local deterministic broker evaluates each task before inference.
- Vast.ai supplies remote GPU compute through broker-controlled compute backends for approved open-weight models.
- The current Mentat 1.0 compute path is guarded Vast Serverless. Direct Vast instances are an additional target backend and are not production-eligible unless their implementation, lifecycle, security, billing, and validation gates are explicitly completed.
- Kimi K2.7 Code is the dependable primary model until measured evidence proves a cheaper registered model is good enough for a task class.
- The broker selects the best eligible model and compatible Vast hardware within explicit quality, capability, reliability, context, time, and cost limits.
- The user sees the model, GPU requirements, live price ceiling, estimated duration, estimated cost, reasons, and fallback policy before new paid compute begins.
- Paid resources are reused when still approved, cooled/stopped when policy allows, destroyed when appropriate, and reconciled after crashes according to the backend's validated lifecycle semantics.
- Quality, latency, throughput, success, and cost history are recorded locally and used to improve future routing.

## Compute backend scope and extensibility

Mentat's broker must reason through a stable backend boundary rather than hard-coding provider lifecycle logic into task classification, model quality logic, or user policy.

For Mentat 1.0:

- Vast Serverless remains the current release-path backend.
- Adding the backend abstraction itself is allowed when it preserves all existing behavior and invariants.
- Direct Vast instance support remains `PLANNED`/`EXPERIMENTAL` until explicitly implemented and validated.
- Direct-instance work must not silently expand the frozen Mentat 1.0 release scope. Making it a Mentat 1.0 release blocker requires an explicit owner-approved scope change in the frozen scope document and work backlog.

Any future compute backend, including a direct Vast instance backend, must satisfy the same broker-facing security and spending contract:

- only the local broker holds the provider credential that can authorize spending;
- provider SDK/API calls occur behind the broker boundary;
- raw provider objects are normalized into Mentat's own typed candidate/resource records;
- paid acquisition is impossible without a valid authenticated approval lease;
- resource identity is durably recorded as soon as creation succeeds;
- ambiguous create outcomes are reconciled before any retry;
- readiness polling is bounded and handles terminal/error states instead of looping forever;
- stop, cool, delete/destroy, storage, bandwidth, and other billing semantics are modeled explicitly rather than guessed;
- actual provider billing remains the source of truth and is reconciled against Mentat's estimates;
- a backend is not production-eligible until no-spend tests and the required live validation gates for that backend pass.

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
- Future Vast SDK integration must receive the credential explicitly from Mentat's broker-owned protected credential path; it must not rely on ambient CLI credential discovery as the production authority boundary.

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

- Endpoint/resource creation is idempotent where the provider supports it and otherwise reconciles exact remote identity after ambiguous network outcomes.
- Non-idempotent create requests are never blindly retried.
- Local endpoint/resource state is written atomically.
- Duplicate or orphaned Vast resources cause a fail-closed error.
- A restarted broker cools or safely reconciles saved paid resources before accepting new approvals.
- Idle, expired, or stale-warming resources are cooled/stopped/destroyed according to validated backend policy.
- Broker shutdown attempts the safest validated no-spend lifecycle action for every saved paid resource.
- Direct-instance polling, when implemented, must use explicit timeout/error handling for states such as `exited`, `unknown`, or `offline`; it must never wait forever while storage charges continue.

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

At the time this contract was introduced and last reconciled:

- the GitHub repository is still public
- the Windows installer is unsigned
- no live Vast canary has been completed
- no full Windows no-spend integration run has been completed on the owner's machine
- no Kimi soak or billing reconciliation has been completed
- direct Vast instance support is not production-validated and is not a Mentat 1.0 release claim unless the frozen scope is explicitly changed

Those are intentional stop signs, not documentation trivia.
