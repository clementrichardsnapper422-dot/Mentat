# Mentat mission execution ledger

This is the permanent handoff and evidence record for completing Mentat. Update it whenever work starts, stops, passes, fails, changes scope, or reaches an owner-only gate. A fresh coding agent should be able to resume from this file plus `docs/mentat/current-state.yaml` without relying on old chat history.

## Mission

Ship a signed Windows-native Mentat release that safely combines local OpenClaw tools and memory with a deterministic, evidence-driven model-and-compute broker that selects approved remote intelligence, explains cost and quality before spending, learns from verified outcomes, and fails safely.

The economic objective is not cheapest GPU-hour. It is the **best verified result for the lowest practical total cost** while satisfying quality, context, capability, reliability, latency, risk, security, and spending limits.

## Definition of done

Mentat 1.0 is complete only when every in-scope release gate in `docs/mentat/production-contract.md` passes and the release candidate is installed from a signed artifact on a clean Windows machine.

Target direct-instance and advanced broker-hardening work documented in Program 7 of `docs/mentat/work-items.md` is deferred from the frozen Mentat 1.0 release scope unless the owner explicitly changes scope.

## Current repository state

Last reconciled for PR #15 review: **2026-07-24**.

- Repository: `clementrichardsnapper422-dot/Mentat`
- Default branch: `main`
- Current `main` baseline: `ce7a42fadd721b6c5bcb11ffb4356d17751c1eaa`
- Current visibility: **public**
- Current repository type: public fork larger than 1 GB
- GitHub Issues: disabled; `docs/mentat/work-items.md` is the authoritative backlog until a replacement tracker is enabled
- Production contract: present and canonical
- Mentat 1.0 scope: frozen
- Machine-readable handoff: `docs/mentat/current-state.yaml`
- PR #11: merged; no-spend Broker milestone established
- PR #13: merged; complete target broker architecture documented
- PR #14: merged as `ce7a42fadd721b6c5bcb11ffb4356d17751c1eaa`; construction contract, roadmap, checklist, and resume system established
- PR #15: open documentation hardening package on `docs/vast-broker-learning-hardening`
- PR #12: open draft engineering work package on `agent/desktop-no-spend-integration`; latest verified engineering head remains `655634d1a4dacb8a4c077a0970e16571f6c8cb48`
- Live Vast canary: not completed
- Signed installer: not completed

## Status vocabulary

- `DONE` — implemented and supported by the evidence required for that gate.
- `PARTIAL` — meaningful implementation/evidence exists but the stated exit criteria are not fully closed.
- `ACTIVE` / `IN PROGRESS` — current work exists on a branch or test environment.
- `BLOCKED: OWNER` — requires the owner, target Windows PC, credentials, payment approval, signing certificate, or another owner-only action.
- `BLOCKED: EXTERNAL` — depends on an external service/vendor behavior that has not yet been validated.
- `NOT STARTED` — no implementation or verified execution yet.
- `DEFERRED` — intentionally outside the frozen Mentat 1.0 scope unless explicitly promoted.

## Master gate status

| Gate | Status | Evidence required to close |
|---|---|---|
| 0. Private repository and supply chain | BLOCKED: OWNER | standalone private repository, protected `main`, secret/history audit, required checks, reproducible signed release path |
| 1. No-spend Windows integration | IN PROGRESS | PR #12 repaired/accepted, clean target-PC install, Docker tool isolation, credential-boundary proof, restart/shutdown behavior |
| 2. Low-cost Vast canary | NOT STARTED | current API/permission assumptions validated, reject/no-spend, one intended create, real inference, reuse/cooling, recovery, actual billing reconciliation |
| 3. Kimi canary | NOT STARTED | exact Kimi profile, tools, long context, stream/cancellation, caps, recovery, actual latency/throughput/billing |
| 4. Broker intelligence/learning | IN PROGRESS BY DESIGN | benchmark corpus, calibrated quality/success/cost/latency predictions, safe exploration, promotion/demotion, regret/savings, explainability |
| 5. Soak/adversarial validation | NOT STARTED | race/failure injection, security attacks, 100-session/24-hour/multi-day campaign, no leaks or stale paid resources |
| 6. Signed Mentat 1.0 release | NOT STARTED | all in-scope P0 gates closed, signed/checksummed/provenanced artifact installed on clean Windows |

## Owner-only gates

These actions cannot be honestly completed by repository automation alone:

1. Approve/create the standalone private repository migration.
2. Rotate and enter real Vast credentials locally without sharing them in chat, Git, prompts, logs, CI, or workspaces.
3. Run clean target-PC Windows validation.
4. Approve real paid Vast canaries and inspect actual billing.
5. Obtain and use an Authenticode signing certificate.
6. Decide final Mentat 1.0 distribution policy.

Until those gates change:

```text
DO NOT expose real Vast credentials.
DO NOT start paid Vast compute from ordinary development or CI.
DO NOT begin the Kimi canary.
DO NOT claim Gate 1 complete.
DO NOT claim direct Vast instances are production-validated.
DO NOT begin a new broker implementation feature while PR #12 remains unresolved.
DO NOT start deferred Program 7 work merely because it is more interesting than the current release blocker.
```

## Workstream tracker

### A. Scope, governance, and handoff

- [x] Canonical production contract exists.
- [x] Mentat 1.0 scope frozen.
- [x] Target direct-instance expansion explicitly separated from frozen 1.0 scope.
- [x] Stable MNT backlog exists.
- [x] Persistent execution ledger exists.
- [x] Machine-readable current-state file exists.
- [x] README contains target architecture, roadmap, construction invariants, and resume protocol.
- [ ] Keep GitHub, README orientation state, work items, ledger, and `current-state.yaml` synchronized at meaningful handoffs.

### B. Repository and supply chain

- [ ] Migrate to standalone private repository.
- [ ] Scan complete history for secrets/sensitive URLs.
- [ ] Rotate affected credentials.
- [ ] Protect `main` and require focused Mentat checks.
- [ ] Add dependency/secret/license scans and SBOM.
- [ ] Produce reproducible signed release workflow.

### C. Windows product and Gate 1

- [x] Native PowerShell/CMD install path exists.
- [x] Electron `Mentat.exe` shell exists.
- [x] Windows packaging/smoke checks exist.
- [x] Fake Vast control-plane foundation exists.
- [x] Fake OpenAI-compatible inference foundation exists.
- [x] Cross-platform no-spend Broker acceptance harness exists and has prior retained green evidence.
- [ ] Repair/revalidate PR #12 Broker/Runtime failures.
- [ ] Installed `mentat test no-spend` path accepted.
- [ ] Desktop diagnostics path accepted.
- [ ] Actual OpenClaw tool execution proven inside Docker.
- [ ] Gateway/tools/renderer/sandbox proven unable to read broker/admin/Vast credentials.
- [ ] Clean target-PC Windows installation.
- [ ] Restart/logoff/shutdown recovery proof.

### D. Broker intelligence and learning

- [x] Deterministic task-classification foundation.
- [x] Model registry/strict validation foundation.
- [x] Live offer discovery/hardware filtering foundation.
- [x] Current guarded Serverless approval, ceiling, reuse, zero-floor, reconciliation, and fallback safeguards.
- [x] Runtime telemetry separated from authenticated human quality evidence.
- [ ] Repository/attachment-aware task requirements.
- [ ] Verification strength, reversibility, blast radius, and risk classification.
- [ ] Exact versioned model/runtime/image/profile lifecycle.
- [ ] Stable provider/backend contracts instead of raw provider structures.
- [ ] Confidence-aware quality/success prediction.
- [ ] Component-level total-cost/latency prediction and actual reconciliation.
- [ ] Calibration, recency, drift, and evidence-age handling.
- [ ] Hard eligibility before multi-objective economic scoring.
- [ ] Safe exploration only inside the eligible low-risk/verifiable set.
- [ ] Promotion/demotion, decision replay, routing regret, and Kimi-only baseline.
- [ ] Host/GPU/provider-market priors kept separate from Mentat local measured evidence.
- [ ] Full candidate/rejection/policy explanation.

### E. Vast live validation

- [ ] Begin provider work from the current official docs index at `https://docs.vast.ai/llms.txt`.
- [ ] Validate exact API/SDK payloads Mentat uses.
- [ ] Validate the minimum permission matrix rather than guessing from category names.
- [ ] Prove SDK/helper retry behavior cannot undermine ambiguous non-idempotent mutation safety.
- [ ] Normalize live provider error/state shapes.
- [ ] Complete capped low-cost Serverless canary.
- [ ] Reconcile displayed estimates against actual provider billing.
- [ ] Complete Kimi canary only after the low-cost gate passes.

### F. Reliability, security, and release

- [ ] Threat model and action-risk policy.
- [ ] Prompt-injection/workspace/sandbox adversarial campaign.
- [ ] Failure taxonomy and circuit breakers.
- [ ] Race/concurrency/property tests for approvals, budget, lifecycle, fallback, and provider ambiguity.
- [ ] 100-session, 24-hour, and multi-day soak.
- [ ] Independent security review or explicit accepted-risk record.
- [ ] Operator/emergency/credential-rotation/backup/recovery/provider-outage runbooks.
- [ ] Signed installer, checksums, provenance, SBOM, clean install/upgrade/repair/uninstall.

### G. Deferred target broker expansion

These do not become Mentat 1.0 blockers without explicit scope change.

- [ ] Provider adapter with read/spend/billing separation and request governor.
- [ ] Least-privilege broker credentials where live permissions permit it.
- [ ] Vast direct-instance lifecycle backend.
- [ ] Pinned Mentat Worker provisioning/readiness attestation and watchdog.
- [ ] Direct-host/market intelligence and bad-host suppression.
- [ ] Keep/freeze/stop/destroy economics.
- [ ] Spend Governor with atomic budget reservation, layered limits, and kill switch.
- [ ] Broker policy versioning, champion/challenger shadowing, and offline replay.
- [ ] Append-only/equivalently auditable broker event history and deterministic replay.
- [ ] Calibration/drift/evidence-decay engine.
- [ ] Serverless-versus-direct evidence campaign.
- [ ] Safe software self-improvement proposals may open tested PRs but may never self-merge or grant themselves spending authority.

## Evidence rules

A checkbox or gate is complete only when the required evidence is linked or described. Acceptable evidence includes:

- merged pull request and commit;
- green CI run covering the behavior;
- retained machine-readable test artifact/log;
- clean-Windows screenshot/video when UI/installation behavior matters;
- live Vast resource/billing record with secrets redacted;
- signed installer checksum/provenance;
- written owner acceptance of residual risk.

Code existing is not enough for a live-system claim. Provider documentation is not live validation. A simulator can close simulator gates, not real billing/hardware gates.

## Execution log

### 2026-07-22 — completion program started

- Created the persistent execution ledger, work-item backlog, and frozen scope document.
- Confirmed repository was public and GitHub Issues unavailable for tracking.
- Added test seams for a fake Vast control plane without changing production Vast defaults.
- No paid compute used.

### 2026-07-23 — no-spend Broker acceptance milestone

- Added reusable fake Vast and fake OpenAI-compatible services.
- Added JSON/SSE/tool/context/outage fixtures and production Broker acceptance orchestration.
- CI evidence retained for commit `e9c9397cd7f19fd7391ed1a3d95c13d68f5dc446`:
  - Windows Broker: success;
  - Ubuntu Broker: success;
  - lint/compile/config validation: success;
  - 38 tests: success;
  - standalone no-spend acceptance: success on Windows and Ubuntu.
- PR #11 later merged as `7bb276cf593e09c45e69c41e594b58a1b71f7332`.
- Paid compute used: **none**.

### 2026-07-24 — broker architecture documentation

- PR #13 merged as `de0dabb521906952f52530ef143dbdd165c8da0d`.
- README gained the complete target broker architecture while distinguishing implemented/live-validated behavior from target design.

### 2026-07-24 — construction/resume contract

- PR #14 merged as `ce7a42fadd721b6c5bcb11ffb4356d17751c1eaa`.
- Added the master roadmap/checklist, AI construction contract, resume discipline, and `docs/mentat/current-state.yaml`.
- Reaffirmed guarded Vast Serverless as the frozen Mentat 1.0 path; direct Vast instances remain target expansion unless scope changes.

### 2026-07-24 — PR #15 hard broker-design review

- Branch: `docs/vast-broker-learning-hardening`.
- Reviewed new Vast SDK/API information against the architecture rather than copying provider convenience behavior into policy.
- README changes include:
  - external-provider documentation protocol;
  - read/spend/billing provider separation;
  - least-privilege credential target and unrestricted-`misc` warning;
  - explicit retry/reconciliation ownership;
  - provider state/error/market normalization;
  - stronger readiness identity/health rules;
  - rate-limit/request-governor/adaptive-polling design;
  - component cost reconciliation;
  - market/benchmark/report signals treated as priors;
  - calibration, drift, safe exploration, shadow routing, replay, regret, and cost-per-verified-successful-task objective;
  - Spend Governor/atomic reservation/kill-switch target;
  - expanded failure/circuit-breaker requirements.
- `docs/mentat/work-items.md` was hard-reviewed and reconciled:
  - stale MNT status/order corrected;
  - PR #12 restored as the exact active engineering work package;
  - advanced direct/provider hardening moved into explicit deferred Program 7 so it cannot silently expand Mentat 1.0.
- `docs/mentat/current-state.yaml` refreshed for PR #14 merged / PR #15 active / PR #12 engineering blocker.
- This ledger refreshed so it no longer instructs a future agent to finish already-merged PR #14.
- Runtime code changed: **none**.
- Real credentials used: **none**.
- Paid compute used: **none**.

## Current handoff

```text
Date/time: 2026-07-24
Main baseline before PR #15: ce7a42fadd721b6c5bcb11ffb4356d17751c1eaa
Documentation branch/PR: docs/vast-broker-learning-hardening / PR #15
Engineering branch/PR: agent/desktop-no-spend-integration / PR #12
Active documentation item: final review/CI and merge of PR #15
Active engineering item: PR #12 desktop/no-spend integration blocked by focused Broker/Runtime CI failures
Last verified PR #12 engineering CI: Desktop PASS; Broker FAIL; Runtime FAIL on head 655634d1a4dacb8a4c077a0970e16571f6c8cb48
Owner action required: private-repository migration remains required before real credentials or paid tests
Exact next task after PR #15 is complete:
1. Reconcile current-state/ledger against the actual PR #15 merge commit.
2. Resume PR #12.
3. Diagnose Broker and Runtime failures without weakening tests/invariants.
4. Rerun focused Broker, Runtime, Desktop, and no-spend acceptance CI.
5. Merge or deliberately supersede PR #12 only when evidence is green and handoff files are updated.
Do not do: real credentials, paid compute, Kimi canary, Gate-1 completion claims, new broker implementation features, or deferred Program-7 work while PR #12 remains unresolved.
```

## Handoff template

Copy this block whenever stopping work:

```text
Date/time:
Main commit:
Branch/PR:
MNT work item:
Last completed item:
Current item:
Files changed:
Tests/checks run and results:
Evidence produced:
Known failures:
Owner action required:
External dependency:
Exact next command or task:
Do not do:
```

Before handing off, verify this ledger and `docs/mentat/current-state.yaml` against GitHub.