# Mentat 1.0 work items

GitHub Issues were disabled when this completion program began. This file is the authoritative backlog until Issues or another tracker is enabled. Keep work-item IDs stable when migrating them.

## Priority definitions

- `P0` — release blocker or potential credential/spending/security failure.
- `P1` — required Mentat 1.0 capability.
- `P2` — important improvement that may follow the first stable release if explicitly accepted.

## State definitions

`TODO`, `ACTIVE`, `BLOCKED_OWNER`, `BLOCKED_EXTERNAL`, `REVIEW`, `DONE`, `DEFERRED`.

---

## Program 0 — Scope and governance

### MNT-001 — Freeze Mentat 1.0 scope

- Priority: P0
- State: TODO
- Deliverables:
  - supported features list;
  - explicitly deferred features list;
  - acceptance criteria mapped to tests;
  - product-owner approval.
- Exit: no release-blocking feature remains ambiguous.

### MNT-002 — Maintain mission ledger

- Priority: P0
- State: ACTIVE
- Deliverable: update `docs/mentat/execution-ledger.md` at every work boundary.
- Exit: all work has evidence and an exact handoff point.

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

### MNT-200 — Build fake Vast control-plane service

- Priority: P0
- State: TODO
- Exit: deterministic local service supports offer discovery, endpoint/workergroup lifecycle, ambiguous responses, timeouts, duplicates, orphans, billing fixtures, and assertions that no external network/spend occurred.

### MNT-201 — Build fake OpenAI-compatible inference service

- Priority: P0
- State: PARTIAL
- Existing evidence: focused broker integration fixture.
- Exit: reusable service supports streaming, tools, failures, context errors, cancellation, latency, and usage fixtures.

### MNT-202 — Full Windows no-spend acceptance harness

- Priority: P0
- State: TODO
- Dependencies: MNT-200, MNT-201.
- Exit: installed Mentat completes setup, decision, approval, inference, tool, rating, shutdown, and recovery entirely against local fakes.

### MNT-203 — Clean target-PC installation

- Priority: P0
- State: BLOCKED_OWNER
- Exit: install from packaged artifact on clean Windows; no source checkout or manual environment editing.

### MNT-204 — Credential-boundary proof

- Priority: P0
- State: TODO
- Exit: Gateway, tools, renderer, prompts, URLs, logs, crash output, and sandbox cannot access Vast/admin credentials.

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
- Exit: requirements, Docker, Vast connection, budgets, workspace, privacy, no-spend test, and ready state handled in the app.

### MNT-301 — Integrated compute-decision experience

- Priority: P0
- State: PARTIAL
- Exit: model, candidates, hardware, live ceiling, cost range, confidence, new/reused state, fallback, approve/reject, and user override shown in `Mentat.exe`.

### MNT-302 — Active compute controls

- Priority: P0
- State: TODO
- Exit: endpoint status, rate, approved-until, spend estimate, last activity, cool, destroy, and emergency lockout available.

### MNT-303 — History, benchmarks, and costs

- Priority: P1
- State: TODO
- Exit: decisions, models, task classes, estimates, actual costs, ratings, failures, and Kimi-only savings visible.

### MNT-304 — Models and routing settings

- Priority: P1
- State: TODO
- Exit: Best/Balanced/Economy/Manual modes, budgets, exploration opt-in, model status, and disable controls.

### MNT-305 — Diagnostics and repair

- Priority: P0
- State: TODO
- Exit: Desktop/Gateway/Broker/Docker/Vast/sandbox/ports/logs/config checks plus safe repair actions.

### MNT-306 — Update, rollback, repair, uninstall

- Priority: P0
- State: TODO
- Exit: all paths tested with user-data preservation rules documented.

---

## Program 4 — Broker intelligence

### MNT-400 — Structured task analyzer v2

- Priority: P0
- State: TODO
- Exit: repository, attachment, output, tool schema, verification, reversibility, blast radius, latency, quality, and budget requirements included with explainable confidence.

### MNT-401 — Versioned model/profile registry

- Priority: P0
- State: TODO
- Exit: exact model/version/quantization/profile status, migration, retirement, validation, and rollback supported.

### MNT-402 — Canonical benchmark corpus and grader

- Priority: P0
- State: TODO
- Exit: simple, reasoning, coding, repository, tools, and high-risk suites with automatic and blind-human grading.

### MNT-403 — Quality predictor with uncertainty

- Priority: P0
- State: TODO
- Dependencies: MNT-402.
- Exit: task-specific expected quality/success with sample count, variance, recency, version, profile, and confidence bounds.

### MNT-404 — Total-cost and latency predictors

- Priority: P0
- State: TODO
- Exit: setup, cold start, inference, retries, fallback, reuse, and billing increments predicted as ranges and reconciled to actuals.

### MNT-405 — Multi-objective route scorer

- Priority: P0
- State: TODO
- Dependencies: MNT-400, MNT-403, MNT-404.
- Exit: eligible candidates scored for quality, success, cost, speed, reuse, evidence, uncertainty, failure, and risk with deterministic guards.

### MNT-406 — Safe exploration

- Priority: P1
- State: TODO
- Exit: opt-in, low-risk, verifiable, capped exploration with rollback and audit trail.

### MNT-407 — Promotion/demotion and routing regret

- Priority: P0
- State: TODO
- Exit: evidence thresholds, automatic demotion, decision replay, alternatives, regret, and Kimi-only savings tracked.

### MNT-408 — Hardware/host intelligence

- Priority: P1
- State: TODO
- Exit: host/GPU/profile startup, throughput, reliability, total cost, bad-host suppression, and preferred-host scoring.

### MNT-409 — Failure taxonomy and fallback controller

- Priority: P0
- State: TODO
- Exit: error-specific retry, offer fallback, endpoint recreation, reapproval, context recovery, verification escalation, and circuit breakers.

### MNT-410 — Full decision explainability

- Priority: P1
- State: TODO
- Exit: candidates, rejection reasons, estimates, confidence, policy, fallback, exploration, and override audit visible and exportable.

---

## Program 5 — Live Vast validation

### MNT-500 — Validate live API payloads and lifecycle

- Priority: P0
- State: BLOCKED_OWNER
- Exit: current live API behavior verified with redacted evidence and no undocumented assumptions.

### MNT-501 — Low-cost canary

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: Windows no-spend gate complete.
- Exit: reject/no-spend, one create, inference, tool loop, reuse, idle/manual cooling, crash recovery, and actual bill reconciliation.

### MNT-502 — Billing import and reconciliation

- Priority: P0
- State: BLOCKED_EXTERNAL
- Exit: actual Vast charges imported and allocated; estimate error and cost per successful task reported.

### MNT-503 — Kimi production canary

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: MNT-501.
- Exit: exact Kimi profile, tools, reasoning, long context, streaming, cancellation, repository task, caps, recovery, and zero-floor proven.

---

## Program 6 — Security, reliability, and release

### MNT-600 — Threat model and action-risk policy

- Priority: P0
- State: TODO
- Exit: assets, trust boundaries, threats, mitigations, residual risks, and action levels documented and tested.

### MNT-601 — Adversarial sandbox and prompt-injection campaign

- Priority: P0
- State: TODO
- Exit: malicious prompts/workspaces cannot escape, obtain credentials, or perform unapproved consequential actions.

### MNT-602 — Failure-injection suite

- Priority: P0
- State: TODO
- Exit: network loss, ambiguous create, disk full, SQLite corruption, context overflow, cancellation, budget exhaustion, and partial streams fail safely.

### MNT-603 — Soak and concurrency validation

- Priority: P0
- State: BLOCKED_OWNER
- Exit: 100 sessions, 24-hour run, multi-day normal use, concurrent chats, no leaks, no stale paid workers.

### MNT-604 — Independent security review

- Priority: P0
- State: BLOCKED_OWNER
- Exit: critical findings closed; accepted residual risks signed off.

### MNT-605 — Release documentation and recovery runbooks

- Priority: P1
- State: TODO
- Exit: setup, user, troubleshooting, spending, emergency stop, credential rotation, backup/restore, cleanup, incident, model registration, and release guides.

### MNT-606 — Signed Mentat 1.0 release candidate

- Priority: P0
- State: BLOCKED_OWNER
- Dependencies: all P0 items.
- Exit: signed artifact installed from release channel and passes final acceptance on clean Windows.

---

## Current execution order

1. MNT-001 and MNT-100.
2. MNT-200 through MNT-206.
3. MNT-300 through MNT-306.
4. MNT-400 through MNT-410 in evidence-dependent order.
5. MNT-501 then MNT-503.
6. MNT-600 through MNT-605.
7. MNT-606.

Do not begin an expensive Kimi canary before the no-spend Windows gate and low-cost canary are complete.
