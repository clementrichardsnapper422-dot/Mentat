# Mentat work items

GitHub Issues were disabled when this completion program began. This file is the authoritative backlog until Issues or another tracker is enabled. Keep work-item IDs stable when migrating them.

This backlog contains both the **frozen Mentat 1.0 release program** and explicitly **deferred target-broker expansion**. A deferred target item does not become a Mentat 1.0 release blocker unless the owner deliberately changes frozen scope.

## Priority definitions

- `P0` — release blocker or potential credential/spending/security failure.
- `P1` — required Mentat 1.0 capability.
- `P2` — important target improvement that may follow the first stable release unless explicitly promoted into scope.

## State definitions

`TODO`, `PARTIAL`, `ACTIVE`, `BLOCKED_OWNER`, `BLOCKED_EXTERNAL`, `REVIEW`, `DONE`, `DEFERRED`.

A state may only advance when the evidence required by the exit criteria exists. Simulator evidence cannot close a live-service gate.

---

## Program 0 — Scope and governance

### MNT-001 — Freeze Mentat 1.0 scope

- Priority: P0
- State: DONE
- Evidence: `docs/mentat/version-1-scope.md`, `docs/mentat/production-contract.md`, README scope boundary.
- Exit: no release-blocking feature remains ambiguous and target expansion cannot silently move the 1.0 goalposts.

### MNT-002 — Maintain mission ledger and resumable state

- Priority: P0
- State: ACTIVE
- Deliverables:
  - update `docs/mentat/execution-ledger.md` at every meaningful work boundary;
  - update `docs/mentat/current-state.yaml` whenever the resume point changes;
  - verify both against GitHub before coding or handoff.
- Exit: all work has evidence, an exact handoff point, and no stale PR/commit claims.

---

## Program 1 — Repository and supply chain

### MNT-100 — Migrate to standalone private repository

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: successful bare backup and integrity check.
- Exit:
  - standalone private repository;
  - no public fork relationship;
  - branches and tags restored;
  - new remote verified;
  - old public fork removed only after verification.

### MNT-101 — Full secret and sensitive-history audit

- Priority: P0
- State: TODO
- Dependencies: MNT-100.
- Exit: history scan complete; findings documented; affected credentials rotated.

### MNT-102 — Protect `main` and require focused checks

- Priority: P0
- State: TODO
- Dependencies: MNT-100.
- Exit: direct pushes restricted; required Mentat Broker, Runtime, Desktop, and security checks enabled.

### MNT-103 — Supply-chain scanning and SBOM

- Priority: P1
- State: TODO
- Exit: secret, dependency, license, and artifact scans run in CI; SBOM attached to releases.

### MNT-104 — Reproducible signed release pipeline

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: code-signing certificate, private release environment.
- Exit: signed installer/executable, checksums, provenance, and repeatable clean build.

---

## Program 2 — Windows no-spend integration

### MNT-200 — Fake Vast control-plane service

- Priority: P0
- State: PARTIAL
- Existing evidence: reusable fake Vast HTTP control plane, offer discovery, endpoint/workergroup lifecycle, state inspection, zero-dollar billing fixtures, and cross-platform no-spend acceptance.
- Exit: deterministic local service also covers the complete required ambiguity/timeout/duplicate/orphan/rate-limit/error-shape matrix while proving no external network or spend occurred.

### MNT-201 — Fake OpenAI-compatible inference service

- Priority: P0
- State: PARTIAL
- Existing evidence: reusable JSON, SSE, `[DONE]`, tool-call, context rejection, outage, malformed-response, and delay fixtures.
- Exit: remaining cancellation, interruption, usage, and adversarial protocol cases required by Gate 1 are reusable and deterministic.

### MNT-202 — Full Windows no-spend acceptance harness

- Priority: P0
- State: ACTIVE
- Dependencies: MNT-200, MNT-201.
- Active work: PR #12 `agent/desktop-no-spend-integration`.
- Exit: installed Mentat completes setup, decision, approval, inference, tool, rating, diagnostics, shutdown, and recovery entirely against local fakes, with retained machine-readable evidence.

### MNT-203 — Clean target-PC installation

- Priority: P0
- State: BLOCKED_OWNER
- Exit: install from packaged artifact on clean Windows; no source checkout or manual environment editing.

### MNT-204 — Credential-boundary proof

- Priority: P0
- State: TODO
- Exit: Gateway, tools, renderer, prompts, URLs, logs, crash output, workspace, and sandbox cannot access Vast/admin credentials.

### MNT-205 — Real Docker tool-isolation proof

- Priority: P0
- State: BLOCKED_OWNER
- Exit: actual OpenClaw tool runs inside Docker and fails all credential, host-path, Docker-socket, and elevated-escape attempts.

### MNT-206 — Windows shutdown/restart recovery

- Priority: P0
- State: BLOCKED_OWNER
- Exit: process kill, app close, user logoff, and Windows restart recover safely with no uncontrolled compute.

---

## Program 3 — Native desktop product

### MNT-300 — First-run setup wizard

- Priority: P1
- State: TODO
- Exit: requirements, Docker, Vast connection, hourly/per-session/daily/monthly budgets, workspace, privacy, no-spend test, and ready state handled in the app.

### MNT-301 — Integrated compute-decision experience

- Priority: P0
- State: PARTIAL
- Exit: model, candidates, hardware, live ceiling, expected cost range, maximum authorized exposure, confidence, new/reused state, fallback, approve/reject, and user override shown in `Mentat.exe`.

### MNT-302 — Active compute controls and emergency lockout

- Priority: P0
- State: TODO
- Exit: endpoint/resource status, rate, approval expiry, spend estimate, last activity, cool/stop/destroy where supported, and a local global paid-compute kill switch are available without giving the model infrastructure authority.

### MNT-303 — History, benchmarks, costs, and prediction error

- Priority: P1
- State: TODO
- Exit: decisions, models, task classes, estimates, actual costs, prediction errors, ratings, failures, evidence tier, regret, and Kimi-only savings visible.

### MNT-304 — Models and routing settings

- Priority: P1
- State: TODO
- Exit: Best/Balanced/Economy/Manual modes, budgets, exploration opt-in, model status, disable controls, and hard-safety boundaries clearly separated from preferences.

### MNT-305 — Diagnostics and repair

- Priority: P0
- State: TODO
- Exit: Desktop/Gateway/Broker/Docker/Vast/sandbox/ports/logs/config/provider-state checks plus safe repair actions.

### MNT-306 — Update, rollback, repair, uninstall

- Priority: P0
- State: TODO
- Exit: all paths tested with user-data preservation and rollback rules documented.

---

## Program 4 — Broker intelligence, spending safety, and learning

### MNT-400 — Structured task analyzer v2

- Priority: P0
- State: TODO
- Exit: repository, attachment, output, tool schema, verification strength, reversibility, blast radius, latency, quality, and budget requirements included with explainable confidence.

### MNT-401 — Versioned model/profile registry

- Priority: P0
- State: TODO
- Exit: exact model/version/revision/quantization/runtime/image/profile status, migration, retirement, validation, rollback, and evidence isolation supported.

### MNT-402 — Canonical benchmark corpus and grader

- Priority: P0
- State: TODO
- Exit: simple, reasoning, coding, repository, tools, and high-risk suites with automatic and blind-human grading; benchmark evidence remains distinguishable from real production evidence.

### MNT-403 — Quality/success predictor with uncertainty and calibration

- Priority: P0
- State: TODO
- Dependencies: MNT-402.
- Exit:
  - task-specific expected quality and successful-completion probability;
  - sample count, variance, recency, model/runtime version, profile, and confidence bounds;
  - interval/probability calibration measured;
  - drift reduces confidence or triggers revalidation instead of silently trusting stale evidence.

### MNT-404 — Total-cost and latency predictors

- Priority: P0
- State: TODO
- Exit:
  - setup, cold start, warm start, acquisition, inference, retries, failed attempts, fallback, reuse, warm idle, storage, bandwidth, and teardown modeled where applicable;
  - estimates represented as ranges with uncertainty;
  - actual provider charges reconciled by component when available;
  - prediction error retained;
  - cost per **verified successful task** reported rather than optimizing hourly GPU price alone.

### MNT-405 — Multi-objective route scorer

- Priority: P0
- State: TODO
- Dependencies: MNT-400, MNT-403, MNT-404.
- Exit:
  - hard capability/context/security/risk/reliability/quality/spend eligibility runs before economic scoring;
  - conservative quality lower bounds and cost/latency/failure upper bounds can disqualify unsafe uncertain plans;
  - eligible candidates ranked for quality, success, total cost, speed, reuse, evidence, uncertainty, failure, and user routing mode;
  - routing modes change preferences, never hard safety.

### MNT-406 — Safe exploration

- Priority: P1
- State: TODO
- Exit:
  - opt-in/capped exploration only inside the already-safe eligible set;
  - low-risk, reversible, strongly verifiable work favored;
  - dedicated exploration budget and audit trail;
  - contextual-bandit-style selection may be used, but no learning algorithm can bypass hard policy.

### MNT-407 — Promotion/demotion, replay, and routing regret

- Priority: P0
- State: TODO
- Exit:
  - evidence thresholds and reversible promotion/demotion;
  - decision/policy version retained;
  - old decisions can be replayed from retained snapshots;
  - alternatives, regret, Kimi-only savings, and cost-of-failure measured;
  - regressions trigger demotion rather than being averaged away.

### MNT-408 — Hardware/host/provider-market intelligence

- Priority: P1
- State: TODO
- Exit:
  - host/GPU/profile startup, throughput, reliability, total cost, bad-host suppression, and preferred-host scoring;
  - provider marketplace metrics, trends, benchmark records, and machine reports retained only as timestamped external priors;
  - Mentat's recent local evidence can outweigh generic provider priors;
  - stale market observations cannot authorize stale-price paid acquisition.

### MNT-409 — Failure taxonomy, fallback controller, and circuit breakers

- Priority: P0
- State: TODO
- Exit:
  - normalized failure taxonomy drives error-specific retry/replan/fallback/reapproval/reconciliation behavior;
  - ambiguous paid mutations reconcile before retry;
  - fallback independently re-satisfies original requirements and remaining approval scope;
  - host/model/provider failure storms open bounded circuit breakers;
  - recovery actions and suppression expiry are auditable.

### MNT-410 — Full decision explainability

- Priority: P1
- State: TODO
- Exit: candidates, hard rejection reasons, estimates, uncertainty, evidence age/tier, policy version, fallback, exploration, provider-market freshness, and override audit visible/exportable.

### MNT-411 — Spend Governor and atomic budget ledger

- Priority: P0
- State: TODO
- Exit:
  - exactly one narrow internal authority controls actions that can increase paid exposure;
  - a valid authenticated `ApprovalLease` is revalidated immediately before spend;
  - worst-case authorized exposure is reserved atomically before acquisition/warm/extension so concurrent jobs cannot overcommit the same budget;
  - committed, reserved, released, reconciled, and remaining budget are distinguishable;
  - per-job, per-session, hourly-price, daily, monthly, retry/fallback, and exploration limits are enforced where configured;
  - rejection, expiry, cancellation, database failure, and race conditions cannot silently increase authority;
  - the local global paid-compute kill switch prevents new spend-increasing actions without requiring the model.

### MNT-412 — Paid execution state machine and concurrency safety

- Priority: P0
- State: TODO
- Dependencies: MNT-411 for spend-bearing transitions.
- Exit:
  - paid execution uses one explicit state machine rather than incompatible loose booleans;
  - legal transitions are enumerated and enforced atomically/with compare-and-swap semantics where concurrent actors can race;
  - acquisition versus cancellation, approval expiry versus warm/create, fallback versus original execution, shutdown versus active work, and duplicate-request races have adversarial tests;
  - provider state remains separate from Mentat execution state;
  - invalid transitions fail closed and ambiguous remote state enters reconciliation rather than another paid mutation;
  - restart can reconstruct/reconcile enough durable state to prevent duplicate or orphaned paid resources.

---

## Program 5 — Live Vast validation

### MNT-500 — Validate current Vast API/SDK assumptions and permission matrix

- Priority: P0
- State: BLOCKED_OWNER
- Exit:
  - begin from the current official documentation index at `https://docs.vast.ai/llms.txt`;
  - exact endpoints/SDK calls used by Mentat validated against live Vast with redacted evidence;
  - minimum permissions for search, Serverless lifecycle, instance lifecycle, and charge reconciliation measured rather than guessed;
  - documented SDK retry behavior proven not to weaken Mentat's ambiguous-mutation rules;
  - provider error/status shapes normalized and tested;
  - no undocumented behavior is represented as production fact.

### MNT-501 — Low-cost canary

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: Windows no-spend gate complete, repository/credential gate safe, MNT-500 applicable assumptions validated.
- Exit: reject/no-spend, one intended create, inference, tool loop, reuse, idle/manual cooling, rate-limit/error handling, crash recovery, and actual bill reconciliation.

### MNT-502 — Billing import and reconciliation

- Priority: P0
- State: BLOCKED_EXTERNAL
- Exit: actual Vast charges imported and allocated by available components; estimate error and cost per verified successful task reported; permission requirements recorded from live validation.

### MNT-503 — Kimi production canary

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: MNT-501.
- Exit: exact Kimi profile, tools, reasoning, long context, streaming, cancellation, repository task, caps, recovery, billing, and zero-floor proven.

---

## Program 6 — Security, reliability, and release

### MNT-600 — Threat model and action-risk policy

- Priority: P0
- State: TODO
- Exit: assets, trust boundaries, provider credentials, spend authority, threats, mitigations, residual risks, kill switch, and action levels documented and tested.

### MNT-601 — Adversarial sandbox and prompt-injection campaign

- Priority: P0
- State: TODO
- Exit: malicious prompts/workspaces cannot escape, obtain credentials, influence infrastructure authorization, or perform unapproved consequential actions.

### MNT-602 — Failure-injection, race, and property-test suite

- Priority: P0
- State: TODO
- Dependencies: include MNT-411/MNT-412 behavior before release.
- Exit: network loss, ambiguous create, provider 429/error variants, automatic-retry hazards, disk full, SQLite corruption, context overflow, cancellation, budget exhaustion, partial streams, concurrent approvals, duplicate requests, budget reservation races, invalid state transitions, and lifecycle races fail safely.

### MNT-603 — Soak and concurrency validation

- Priority: P0
- State: BLOCKED_OWNER
- Exit: 100 sessions, 24-hour run, multi-day normal use, concurrent chats, no credential leaks, no budget overcommit, no stale paid workers, and recovery evidence retained.

### MNT-604 — Independent security review

- Priority: P0
- State: BLOCKED_OWNER
- Exit: critical findings closed; accepted residual risks signed off.

### MNT-605 — Release documentation and recovery runbooks

- Priority: P1
- State: TODO
- Exit: setup, user, troubleshooting, spending, emergency stop, credential rotation, backup/restore, cleanup, incident, model registration, provider outage, and release guides.

### MNT-606 — Signed Mentat 1.0 release candidate

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: all in-scope P0 items, including MNT-411 and MNT-412.
- Exit: signed artifact installed from release channel and passes final acceptance on clean Windows.

---

## Program 7 — Deferred target broker hardening and direct-compute expansion

These are part of the documented long-term Mentat architecture. They are **DEFERRED from the frozen Mentat 1.0 scope** unless the owner explicitly promotes a specific item. Normal execution begins after MNT-606.

### MNT-700 — Provider adapter, request governor, and least-privilege credentials

- Priority: P2
- State: DEFERRED
- Dependencies: MNT-500, MNT-606 unless scope is explicitly changed.
- Exit: pinned provider adapter; separate read/spend/billing concerns; explicit protected credentials; endpoint-level least privilege where supported; typed provider errors/state/market snapshots; caching/coalescing/adaptive polling; no hidden non-idempotent mutation retries.

### MNT-701 — Vast direct-instance backend lifecycle

- Priority: P2
- State: DEFERRED
- Exit: normalized offer discovery, price freshness recheck, approved create, immediate resource-ID persistence, bounded provider polling, reconciliation, stop/destroy semantics, and no-spend simulator coverage.

### MNT-702 — Pinned Mentat Worker supply chain and readiness attestation

- Priority: P2
- State: DEFERRED
- Exit: pinned image/bootstrap/runtime/model revision, integrity evidence, health + identity checks, controlled inference probe, bounded worker lease/watchdog, and no infrastructure credential in the model process.

### MNT-703 — Direct-host and marketplace intelligence

- Priority: P2
- State: DEFERRED
- Exit: local host reputation, provider priors, freshness/decay, bad-host suppression, provider-market condition features, and evidence-source separation.

### MNT-704 — Keep/freeze/stop/destroy economics

- Priority: P2
- State: DEFERRED
- Exit: lifecycle choices use measured GPU/storage/bandwidth/restart/reprovisioning economics and predicted next-request timing; `frozen` is never treated as compute-free.

### MNT-705 — Advanced broker policy shadowing and offline comparison

- Priority: P2
- State: DEFERRED
- Exit: immutable policy versions; current known-good champion; challenger evaluates without spending authority; large-scale historical replay; evidence-based promotion; automatic/manual rollback path. This extends the basic versioning/replay required by MNT-407 rather than replacing it.

### MNT-706 — Adaptive spend forecasting and session economics

- Priority: P2
- State: DEFERRED
- Dependencies: MNT-411.
- Exit: forecast request-arrival/reuse and remaining-budget economics to optimize warm/reuse choices while never weakening the hard atomic reservations, approval scope, configured spending caps, or kill switch required by Mentat 1.0.

### MNT-707 — Append-only broker event ledger and deterministic decision replay

- Priority: P2
- State: DEFERRED
- Exit: critical lifecycle/decision events are append-only or equivalently auditable; state can be reconstructed; decision replay captures policy/model/provider snapshots without storing secrets unnecessarily.

### MNT-708 — Advanced calibration, drift, and evidence-decay engine

- Priority: P2
- State: DEFERRED
- Exit: extend the basic calibration/drift behavior required by MNT-403 across model/runtime/provider-policy changes with richer decay/rebenchmarking automation and rollback signals.

### MNT-709 — Serverless-versus-direct evidence campaign

- Priority: P2
- State: DEFERRED
- Exit: equivalent workloads compared on verified quality, success, cold/warm latency, throughput, reliability, full provider charges, retry/failure cost, and cost per verified successful task.

### MNT-710 — Safe software self-improvement proposals

- Priority: P2
- State: DEFERRED
- Exit: Mentat may detect systematic broker error and prepare a branch/PR with tests, replay, and shadow evidence, but may not self-merge, weaken hard safety rules, or grant itself new spending authority.

---

## Current execution order

1. Keep MNT-002 active continuously; GitHub and handoff documents must agree.
2. Finish the existing PR #12 work package advancing MNT-201/MNT-202; diagnose Broker/Runtime CI without weakening invariants.
3. Close the remaining no-spend Gate 1 work in MNT-202 through MNT-206 as dependencies/owner actions permit.
4. Complete MNT-100 through MNT-104 before real credentials, paid canaries, or release operations that depend on the private supply-chain boundary.
5. Complete MNT-300 through MNT-306 and MNT-400 through MNT-412 in dependency/evidence order; MNT-411/MNT-412 are spending/concurrency safety work, not optional optimization.
6. Validate live Vast assumptions with MNT-500, then MNT-501/MNT-502, then MNT-503.
7. Complete MNT-600 through MNT-605 and close all in-scope P0 gates.
8. Complete MNT-606.
9. Begin MNT-700 through MNT-710 only after Mentat 1.0 or an explicit owner-approved scope change.

Do not begin an expensive Kimi canary before the no-spend Windows gate and low-cost canary are complete. Do not start deferred target work merely because it is more interesting than the current blocker.