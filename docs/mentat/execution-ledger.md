# Mentat mission execution ledger

This is the permanent handoff record for completing Mentat. Update it whenever work starts, stops, passes, fails, changes scope, or requires an owner-only action.

## Mission

Ship a signed Windows-native Mentat release that safely combines local OpenClaw tools and memory with a deterministic, evidence-driven broker that selects approved remote models and Vast.ai hardware, explains cost and quality before spending, learns from verified outcomes, and fails safely.

## Definition of done

Mentat 1.0 is complete only when all release gates in `docs/mentat/production-contract.md` pass and the release candidate is installed from a signed artifact on a clean Windows machine.

## Current repository state

- Repository: `clementrichardsnapper422-dot/Mentat`
- Default branch: `main`
- Current visibility at the start of this execution program: **public**
- Current repository type: public fork larger than 1 GB
- GitHub Issues: disabled; `docs/mentat/work-items.md` is the temporary authoritative backlog
- Production contract: present
- Mentat 1.0 scope: frozen on completion-program branch
- Focused Windows and broker CI: present
- Cross-platform no-spend Broker acceptance harness: present and green in CI
- Live Vast canary: not completed
- Signed installer: not completed

## Status vocabulary

- `DONE` — implemented and supported by evidence.
- `IN PROGRESS` — active work exists on a branch or test environment.
- `BLOCKED: OWNER` — requires the repository owner, Windows PC, credentials, payment approval, signing certificate, or another irreversible owner action.
- `BLOCKED: EXTERNAL` — depends on an external service or vendor.
- `NOT STARTED` — no implementation or verified execution yet.
- `DEFERRED` — intentionally excluded from Mentat 1.0.

## Master gate status

| Gate | Status | Evidence required to close |
|---|---|---|
| 0. Private repository and supply chain | BLOCKED: OWNER | Standalone private repository, protected `main`, required checks, secret scan, signed/reproducible release pipeline |
| 1. No-spend Windows integration | IN PROGRESS | CI fake Vast/OpenAI path is green; still requires clean target-PC install, real Docker tool execution, credential-boundary proof, restart and shutdown tests |
| 2. Low-cost Vast canary | NOT STARTED | Rejection creates nothing, approval creates one endpoint, real inference, reuse, cooling, crash recovery, actual bill reconciliation |
| 3. Kimi canary | NOT STARTED | Kimi startup, tools, reasoning, long context, streaming, cancellation, cost and zero-floor proof |
| 4. Broker learning campaign | IN PROGRESS | Benchmark corpus, grading, quality/cost predictors, exploration policy, promotion/demotion, routing-regret reports |
| 5. Soak and adversarial validation | NOT STARTED | Multi-day use, failure injection, sandbox attacks, state corruption, Windows restart, update rollback |
| 6. Signed Mentat 1.0 release | NOT STARTED | Signed installer, checksums, provenance, SBOM, clean install/upgrade/repair/uninstall, docs and recovery runbooks |

## Owner-only gates

These actions cannot be honestly completed by repository automation alone:

1. Create or approve the standalone private repository migration.
2. Rotate and enter the real Vast API key without sharing it in chat, Git, logs, or prompts.
3. Run the clean Windows installation on the target PC.
4. Approve real paid Vast canaries and inspect actual billing.
5. Obtain and use an Authenticode code-signing certificate.
6. Decide whether Mentat 1.0 may be distributed to other users.

## Workstream tracker

### A. Scope and product contract

- [x] Canonical production contract exists.
- [x] Freeze Mentat 1.0 supported features.
- [x] Record explicitly deferred features.
- [x] Convert the Broker no-spend definition of done into executable cross-platform acceptance tests.
- [ ] Convert remaining desktop, sandbox, release, and live-compute gates into executable acceptance tests where possible.

### B. Repository and supply chain

- [ ] Move to a standalone private repository.
- [ ] Search complete Git history for secrets and sensitive URLs.
- [ ] Rotate exposed or development credentials.
- [ ] Protect `main` and require focused Mentat checks.
- [ ] Add dependency, secret, and license scanning.
- [ ] Produce an SBOM.
- [ ] Pin installer-critical dependencies.
- [ ] Create reproducible signed release workflow.

### C. Windows product

- [x] Native PowerShell/CMD install path exists.
- [x] Electron desktop shell exists.
- [x] Windows packaging and smoke checks exist.
- [ ] Clean Windows install completed.
- [ ] First-run setup wizard completed.
- [ ] Desktop chat, decision, active compute, history, models, costs, settings, and diagnostics screens completed.
- [ ] Normal operation requires no PowerShell.
- [ ] Repair, update, rollback, and uninstall validated.

### D. OpenClaw and sandbox

- [x] Loopback binding configured.
- [x] Docker sandbox required in production mode.
- [x] Elevated host escape disabled.
- [ ] Actual tool execution proven to occur inside Docker.
- [ ] Sandbox cannot read broker/admin/Vast credentials.
- [ ] Workspace mount is restricted to the intended paths.
- [ ] Tool risk levels and approvals implemented.
- [ ] Malicious workspace and prompt-injection tests passed.

### E. Broker core

- [x] Deterministic task classification foundation.
- [x] Model registry and strict validation.
- [x] Live offer discovery and hardware filters.
- [x] Cost ceilings, approval, endpoint reuse, zero-floor lifecycle, reconciliation, and fallback capability checks.
- [x] Reusable fake Vast control plane and real lifecycle subprocess acceptance coverage.
- [x] Reusable fake OpenAI-compatible inference service covering JSON, SSE streaming, tool calls, context rejection, and outage behavior.
- [x] Standalone no-spend production acceptance harness runs on Windows and Ubuntu CI.
- [ ] Repository/attachment-aware task estimation.
- [ ] Verification availability and blast-radius classification.
- [ ] Versioned model profiles and experimental/approved/retired lifecycle.
- [ ] Candidate scoring with uncertainty, reuse, cold-start, and failure penalties.
- [ ] User routing modes: Best, Balanced, Economy, Manual.
- [ ] Explain full candidate comparison and rejection reasons.

### F. Broker learning system

- [x] Runtime telemetry and one authenticated human rating per completed decision.
- [x] Runtime metrics separated from human quality evidence.
- [x] No-spend acceptance verifies failed upstream requests do not create successful runtime samples.
- [ ] Canonical benchmark corpus and grading harness.
- [ ] Model/version/hardware-specific benchmark records.
- [ ] Quality predictor with confidence bounds and sample-size handling.
- [ ] Real total-cost predictor including cold starts, retries, setup, and reuse.
- [ ] Safe exploration limited to low-risk, verifiable, opt-in tasks.
- [ ] Promotion and demotion policy with audit trail.
- [ ] Routing-regret and Kimi-only savings measurement.
- [ ] Host/GPU performance history and bad-host suppression.

### G. Vast live validation

- [ ] Validate payloads against the live API.
- [ ] Complete low-cost canary.
- [ ] Prove rejection starts no compute.
- [ ] Prove actual price stays below approved ceiling.
- [ ] Prove endpoint reuse and zero-floor cooling.
- [ ] Prove recovery after Broker/Gateway/Windows failure.
- [ ] Import and reconcile actual billing.
- [ ] Complete Kimi canary and repository-scale task.

### H. Reliability, security, and release

- [ ] Threat model completed.
- [ ] Failure taxonomy and circuit breakers completed.
- [ ] 100-session, 24-hour, and multi-day soak completed.
- [ ] Disk-full, SQLite corruption, network loss, context overflow, and runaway tool-loop tests completed.
- [ ] Third-party security review completed or findings explicitly accepted.
- [ ] Signed installer, checksums, provenance, SBOM, and release documentation completed.

## Evidence rules

A checkbox may be marked complete only when the evidence is linked or described here. Acceptable evidence includes:

- merged pull request and commit;
- green CI run covering the behavior;
- test artifact or log;
- screenshot/video of the Windows flow;
- Vast endpoint and billing record with secrets redacted;
- signed installer checksum and provenance;
- written owner approval for accepted risk.

Code existing without an executed integration test is not sufficient evidence for a live-system gate.

## Execution log

### 2026-07-22 — Completion program started

- Created branch `agent/complete-mentat-mission` from `main`.
- Confirmed repository is still public and larger than 1 GB.
- Confirmed GitHub Issues are disabled; issue creation returned HTTP 410.
- Added `docs/mentat/work-items.md` as the stable MNT backlog.
- Added `docs/mentat/version-1-scope.md`; Mentat 1.0 required and deferred features are now frozen.
- Created draft PR #11, **Start the Mentat 1.0 completion program**.
- Added explicit test-only Vast endpoints:
  - `MENTAT_VAST_API_BASE`
  - `MENTAT_VAST_BUNDLES_URL`
  Production defaults remain the real Vast domains.
- Added `scripts/mentat/testing/fake_vast.py`, a reusable authenticated HTTP control-plane simulator with offers, endpoints, workergroups, lifecycle calls, state inspection, and zero-dollar billing fixtures.
- Added cross-platform tests that exercise real HTTP offer discovery and the real `vast_endpoint.py` subprocess through create, status, warm, cool, billing, destroy, and local-state cleanup.

### 2026-07-23 — No-spend Broker acceptance milestone completed

- Added `scripts/mentat/testing/fake_openai.py`.
- Added deterministic fixtures for:
  - normal OpenAI JSON completion;
  - SSE streaming and `[DONE]` termination;
  - OpenAI-compatible function/tool calls;
  - context-limit rejection;
  - upstream HTTP 503 outage;
  - malformed-response and delay hooks for subsequent failure testing.
- Added `services/model-broker/tests/test_no_spend_inference.py`.
- Added `scripts/mentat/testing/no_spend_acceptance.py`, which starts fake Vast, fake inference, and the production Broker, then writes a machine-readable no-spend report.
- Updated `.github/workflows/mentat-broker.yml` so the standalone acceptance harness runs on both Windows and Ubuntu and uploads retained JSON evidence.
- Corrected the production-test dependency composition so the no-spend suite uses the same hardened store and session manager as `broker.py`.
- CI evidence for commit `e9c9397cd7f19fd7391ed1a3d95c13d68f5dc446`:
  - Windows Broker job: success;
  - Ubuntu Broker job: success;
  - lint: success;
  - compile: success;
  - 38 tests: success;
  - committed Broker configuration validation: success;
  - standalone no-spend acceptance: success on Windows and Ubuntu;
  - retained acceptance artifacts: `mentat-no-spend-windows-latest` and `mentat-no-spend-ubuntu-latest`.
- Paid compute used by this milestone: **none**.

### Current handoff

```text
Date/time: 2026-07-23
Branch/PR: agent/complete-mentat-mission / PR #11
Last completed item: cross-platform no-spend Broker and fake Vast/inference acceptance milestone
Current item: finalize and merge PR #11, then begin desktop/no-spend integration milestone on a fresh branch
Files changed:
- .github/workflows/mentat-broker.yml
- docs/mentat/execution-ledger.md
- docs/mentat/work-items.md
- docs/mentat/version-1-scope.md
- scripts/mentat/testing/fake_openai.py
- scripts/mentat/testing/fake_vast.py
- scripts/mentat/testing/no_spend_acceptance.py
- scripts/mentat/vast_http.py
- services/model-broker/mentat_broker/vast.py
- services/model-broker/pyproject.toml
- services/model-broker/tests/conftest.py
- services/model-broker/tests/test_fake_vast_control_plane.py
- services/model-broker/tests/test_no_spend_inference.py
Tests run and results: Windows and Ubuntu Broker jobs green; 38 tests green; no-spend acceptance green on both operating systems
Known failures: none in the focused no-spend Broker work package
Owner action required: standalone private repository migration remains required before real credentials or paid tests
External dependency: none for the next desktop no-spend integration work
Exact next task: merge PR #11, create a fresh desktop-integration branch, expose the no-spend acceptance result through Mentat.exe, and add installed-wrapper/desktop diagnostics tests
Do not do: do not enter real Vast credentials, start a paid endpoint, or begin Kimi testing while the repository is public and the clean Windows/sandbox gates are incomplete
```

## Handoff template

Copy this block when stopping work:

```text
Date/time:
Branch/PR:
Last completed item:
Current item:
Files changed:
Tests run and results:
Known failures:
Owner action required:
External dependency:
Exact next command or task:
Do not do:
```
