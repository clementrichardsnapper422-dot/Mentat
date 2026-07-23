# Mentat 1.0 scope

This document freezes the supported Mentat 1.0 product boundary. A feature not listed under **Required for 1.0** is not a release blocker unless the product owner explicitly amends this document.

## Product promise

Mentat 1.0 is a Windows-native personal AI operator that keeps OpenClaw conversations, memory, approvals, integrations, and sandboxed tools local while using an authenticated deterministic broker to select approved remote models and Vast.ai compute. It explains new paid compute before spending, enforces user-approved limits, records outcomes, and improves routing from verified evidence.

## Supported user

- One local Windows user per installation.
- User owns and controls the Windows PC, Vast account, repositories, and connected services.
- Mentat is not a hosted multi-tenant service in version 1.0.

## Supported platform

- Windows 11 x64 is the primary supported platform.
- Windows 10 may work but is not a release requirement unless explicitly tested and approved.
- Docker Desktop is required for production tool isolation.
- A compatible internet connection is required for Vast.ai and remote model inference.

## Required for Mentat 1.0

### Installation and setup

- Signed Windows installer.
- Clean installation without a source checkout.
- First-run requirements check.
- Docker Desktop detection and status.
- Secure Vast API-key entry and validation.
- Configurable hourly, per-session, daily, and monthly spending limits.
- Workspace selection.
- No-spend local diagnostic test.
- Repair, update, rollback, and uninstall paths.

### Desktop application

- `Mentat.exe` is the normal operating interface.
- Chat with streaming and cancellation.
- Visible Broker, Gateway, Docker, and endpoint status.
- Compute decision before new paid compute.
- Approve and reject controls.
- Active-compute status and emergency stop.
- Decision, model, benchmark, rating, failure, and cost history.
- Routing and budget settings.
- Diagnostics and safe repair actions.

### OpenClaw local control plane

- Conversations and memory remain local.
- File, repository, shell, browser, and supported integration tools are controlled locally.
- Production tools execute inside the Docker sandbox.
- Elevated host escape is disabled.
- Tool actions are classified by risk and consequential actions require approval.
- The model and tool processes cannot access Vast infrastructure or Broker administration credentials.

### Broker

- Deterministic, explainable task analysis.
- Versioned model and endpoint-profile registry.
- Live Vast offer discovery.
- Hardware and price eligibility filtering.
- Kimi as the dependable primary until evidence supports alternatives.
- Quality, success, latency, cost, reuse, cold-start, evidence, uncertainty, and risk-aware candidate scoring.
- Best, Balanced, Economy, and Manual routing modes.
- Explicit approval before new paid compute.
- One paid model session by default.
- No silent paid fallback.
- Endpoint creation, exact-name reconciliation, reuse, zero-floor operation, cooling, expiry, crash recovery, and emergency stop.
- Failure-specific retry and fallback policy.
- Full decision explanation and audit history.

### Learning system

- Canonical benchmark corpus for simple, general, coding, repository, tool, and high-risk tasks.
- Automatic grading where feasible.
- One authenticated human rating per completed decision.
- Runtime telemetry separate from human quality evidence.
- Model/version/profile/hardware-specific evidence.
- Quality, success, latency, and total-cost predictions with confidence bounds.
- Conservative promotion and automatic demotion.
- Opt-in safe exploration limited to low-risk, verifiable, capped tasks.
- Routing-regret and Kimi-only savings reporting.
- Actual Vast billing reconciliation.

### Security and reliability

- Broker and Gateway bind to loopback by default.
- Separate inference and administration authentication.
- Credential redaction and process-inheritance tests.
- Threat model and adversarial sandbox tests.
- Failure-injection tests for network loss, ambiguous create, context overflow, cancellation, disk full, database corruption, and budget exhaustion.
- Clean Windows restart and user-logoff recovery.
- 100-session, 24-hour, and multi-day soak validation.
- Signed release, checksums, provenance, and SBOM.
- Backup, restore, incident, credential-rotation, emergency-stop, and endpoint-cleanup runbooks.

## Initial supported model set

- Kimi K2.7 Code — primary high-quality route.
- Qwen3 Coder 30B A3B — candidate lower-cost coding route after evidence thresholds.
- DeepSeek Coder V2 Lite — candidate lower-cost simple/general route after evidence thresholds.

Adding or replacing a model does not change the product scope, but every model must pass the registry, benchmark, security, cost, and canary gates.

## Explicitly deferred from Mentat 1.0

- Native mobile applications.
- Hosted multi-user or multi-tenant service.
- Unattended approval of new paid compute.
- Agent swarms or automatic spawning of multiple paid models.
- Multiple simultaneous paid model sessions by default.
- Voice assistant and always-listening behavior.
- Vision support until a validated provider, model profile, benchmark suite, privacy policy, and UI are complete.
- Additional compute marketplaces beyond Vast.ai.
- Automatic discovery and production registration of arbitrary new models.
- Public plugin marketplace.
- Remote access to the local Mentat desktop.
- Enterprise team collaboration and centralized administration.
- macOS and Linux desktop releases.

Deferred features may be built experimentally behind disabled development flags, but they may not weaken or delay Mentat 1.0 release gates.

## Release acceptance summary

Mentat 1.0 may be declared complete only when:

1. The repository and release supply chain are private and secured.
2. A signed installer passes clean install, setup, upgrade, repair, rollback, and uninstall tests.
3. The full no-spend Windows path passes using fake Vast and inference services.
4. Real Docker tool isolation and credential boundaries are proven.
5. A low-cost Vast canary passes with actual billing reconciliation.
6. The Kimi canary passes tools, long context, streaming, cancellation, recovery, and cost controls.
7. Broker benchmark, prediction, promotion/demotion, safe exploration, and regret reporting work from real evidence.
8. Security, failure-injection, concurrency, restart, and soak gates pass.
9. Documentation and recovery runbooks are complete.
10. The release candidate is installed from the signed release artifact on a clean target Windows machine.

## Change control

Any scope amendment must include:

- the reason;
- release impact;
- security and spending impact;
- added acceptance tests;
- product-owner approval;
- an execution-ledger entry.
