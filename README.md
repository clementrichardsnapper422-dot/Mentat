# Mentat

**A Windows-native AI operator and evidence-driven model-and-compute broker built on OpenClaw.**

Mentat keeps the Gateway, tools, memory, repository access, approval gates, and user data on your computer. Remote inference is treated as a controlled resource: Mentat evaluates the task, selects an eligible model and compatible compute strategy, explains the expected tradeoffs, requires approval before new paid compute, records what actually happened, reconciles what it actually cost, and uses verified evidence to improve future routing.

The long-term goal is not simply to run the strongest model or rent the cheapest GPU.

> **Mentat should obtain the best verified result for the lowest practical total cost while satisfying the required quality, context, capability, reliability, latency, risk, security, and spending limits.**

Kimi is an important dependable primary model, but Kimi is not Mentat. Vast.ai is an important compute marketplace, but Vast.ai is not Mentat. The broker, its policy boundaries, its execution controls, and its growing body of local evidence are what make Mentat different.

---

## Table of contents

- [AI / developer — start here](#ai--developer--start-here)
- [Current build state](#current-build-state)
- [Master mission checklist](#master-mission-checklist)
- [Master build roadmap](#master-build-roadmap)
- [What Mentat is](#what-mentat-is)
- [System architecture](#system-architecture)
- [How a request flows through Mentat](#how-a-request-flows-through-mentat)
- [Task analysis](#1-task-analysis)
- [Context estimation](#2-context-estimation)
- [Risk and verification analysis](#3-risk-and-verification-analysis)
- [Model registry](#4-model-registry)
- [Hardware planning](#5-hardware-planning)
- [Compute backends](#6-compute-backends)
- [Vast marketplace discovery and market intelligence](#7-vast-marketplace-discovery-and-market-intelligence)
- [Host reputation](#8-host-reputation)
- [Direct instance provisioning](#9-direct-instance-provisioning)
- [Vast provider adapter contract](#vast-provider-adapter-contract)
- [Mentat workers](#10-mentat-workers)
- [Security and spending authority](#11-security-and-spending-authority)
- [Candidate generation and scoring](#12-candidate-generation-and-scoring)
- [Total-cost prediction and reconciliation](#13-total-cost-prediction-and-reconciliation)
- [Cold starts and reuse](#14-cold-starts-and-reuse)
- [Keep, freeze, stop, cool, or delete](#15-keep-freeze-stop-cool-or-delete)
- [Spend policy and approval](#16-spend-policy-and-approval)
- [Inference and tools](#17-inference-and-tools)
- [Verification](#18-verification)
- [Telemetry and execution history](#19-telemetry-and-execution-history)
- [Human ratings](#20-human-ratings)
- [Learning, promotion, and demotion](#21-learning-promotion-and-demotion)
- [Broker self-learning and efficiency loop](#broker-self-learning-and-efficiency-loop)
- [Safe exploration](#22-safe-exploration)
- [Fallback](#23-fallback)
- [Watchdogs and failure recovery](#24-watchdogs-and-failure-recovery)
- [Example decisions](#example-decisions)
- [Economic strategy](#economic-strategy)
- [Current implementation versus target design](#current-implementation-versus-target-design)
- [AI construction contract — how to turn the Mentat design into code](#ai-construction-contract--how-to-turn-the-mentat-design-into-code)
- [Installation and operation](#install-in-a-few-minutes)

---

# AI / developer — start here

**Do not start coding from a chat prompt alone.** Mentat has a persistent engineering state and a frozen release contract. A new human or coding AI must first reconstruct the real repository state, then resume the earliest authorized incomplete work.

## Resume protocol

Before changing code:

1. Read this README completely enough to understand the mission, architecture, roadmap, provider boundaries, and construction contract.
2. Read `docs/mentat/production-contract.md`.
3. Read `docs/mentat/work-items.md`.
4. Read `docs/mentat/execution-ledger.md`.
5. Read `docs/mentat/current-state.yaml`.
6. Inspect the current `main` commit, open Mentat pull requests, branch heads, and relevant CI.
7. Compare GitHub reality with the handoff files.
8. If the handoff is stale, **update the handoff before implementation**.
9. Find the earliest incomplete roadmap/work-item slice whose dependencies are satisfied.
10. State what you are resuming, why it is next, the evidence already present, the acceptance criterion being closed, and what is explicitly out of scope.
11. Implement only that coherent slice.
12. Run the required unit, adversarial, integration, and platform checks.
13. Before stopping, update the execution ledger and machine-readable current state with the branch/PR, commit, tests, evidence, blockers, exact next task, and `Do not do` rules.

A fresh AI should never need old chat history to determine where to continue.

### Resume decision rule

```text
GitHub reality
    + production contract
    + frozen scope
    + work-item dependencies
    + execution evidence
    + current-state handoff
            |
            v
Earliest incomplete authorized slice
            |
            v
Implement -> verify -> record -> hand off
```

Do **not** choose the next task because it sounds interesting or because the relevant file is already open.

### External-provider documentation rule

Vast.ai is a changing external system. Before implementing or changing Vast behavior:

1. fetch the official documentation index at `https://docs.vast.ai/llms.txt`;
2. discover the relevant current pages from that index;
3. read the specific SDK/API pages needed for the work;
4. separate **documented behavior** from **live-validated Mentat behavior**;
5. record the provider assumption, documentation date, SDK version, and validation status;
6. never turn a documentation assumption into a production claim until the applicable live gate passes.

The README may describe target behavior discovered from current Vast documentation, but live Vast billing, permission, retry, lifecycle, and status semantics remain subject to the production validation gates.

---

# Current build state

This is a human-readable orientation snapshot, not a substitute for checking GitHub. The machine-readable companion is `docs/mentat/current-state.yaml`. **Always verify both against GitHub before coding.**

Last documentation reconciliation: **2026-07-25**.

```text
latest merged documentation milestone:
  PR #15 — provider, learning, spending, and concurrency design hardening
  merge commit: 46f8f71b99f7bfecb0f6d16dc6fc33483ca92941

current verified main:
  897220aa68a3b9d6a85d192cfb2018b2d3ceae2c
  result: post-PR-15 handoff synchronization

active engineering work:
  PR #12
  branch: agent/desktop-no-spend-integration
  published implementation: acdc351b6a6609033d7ea39387dee3349842c851
  verified remote head: ee475eab893206d151eaf3e2341c81e60a142685
  status: OPEN / READY FOR REVIEW / FOCUSED CI GREEN

verified repair:
  rebased on current main: YES
  Broker tests: 39 PASS
  no-spend acceptance: PASS / paid compute used: NO
  Mentat Broker: PASS
  Mentat Runtime: PASS
  Mentat Desktop installer and smoke-install: PASS
  Workflow Sanity: PASS
  review comments/threads: NONE

current release gate:
  Gate 1 — no-spend local integration
  status: IN PROGRESS

exact next engineering task:
  complete PR #12 through the repository-native landing workflow,
  then continue Gate 1 on a clean owner Windows PC.
```

Until the documented gates change:

```text
DO NOT enter/expose real Vast credentials in the public repository, chat, prompts, logs, or CI.
DO NOT start paid Vast compute from ordinary development or CI.
DO NOT begin the Kimi canary.
DO NOT claim Gate 1 complete.
DO NOT describe the direct Vast instance backend as production-validated.
DO NOT begin a new broker feature while the current PR #12 work package is unresolved.
```

The permanent detailed evidence and handoff live in `docs/mentat/execution-ledger.md`.

---

# Master mission checklist

This checklist is the bird's-eye mission status. Detailed sub-items and dependencies belong in `docs/mentat/work-items.md` and `docs/mentat/execution-ledger.md`.

> **A checkbox is complete only when retained evidence exists. Code existing by itself is not enough for a live-system gate.**

## Foundation and specification

- [x] Canonical product/production contract exists.
- [x] Mentat 1.0 scope is frozen.
- [x] Persistent execution ledger exists.
- [x] Stable work-item backlog exists.
- [x] Complete target broker architecture is documented.
- [x] AI construction contract, roadmap, checklist, and resume protocol merged to `main`.
- [x] Machine-readable current-state handoff exists on `main`.
- [ ] Keep README, execution ledger, current-state file, and GitHub reality synchronized at every meaningful handoff.

## No-spend product and security foundation

- [x] Fake Vast control plane exists.
- [x] Fake OpenAI-compatible inference service exists.
- [x] Cross-platform no-spend Broker acceptance harness exists.
- [x] PR #12 focused Broker/Runtime CI failures repaired.
- [ ] Installed `mentat test no-spend` path fully accepted.
- [ ] Desktop no-spend diagnostics fully accepted.
- [ ] Clean Windows installation completed.
- [ ] Actual tool execution proven inside Docker.
- [ ] Gateway/tool processes proven unable to read Vast/admin credentials.
- [ ] Reject, timeout, restart, malformed-response, and shutdown acceptance paths complete.

## Broker intelligence

- [ ] Repository/attachment-aware task estimation.
- [ ] Verification availability and blast-radius classification.
- [ ] Versioned model lifecycle and evidence-aware registry.
- [ ] Stable compute-backend abstraction.
- [ ] Candidate generation and hard-constraint filtering.
- [ ] Quality/success prediction with uncertainty.
- [ ] Cold/warm latency prediction.
- [ ] Real total-cost prediction with component-level reconciliation.
- [ ] Host/runtime reliability penalties.
- [ ] Provider market-state features and freshness handling.
- [ ] Best / Balanced / Economy / Manual routing modes.
- [ ] Full winner/alternative/rejection explanation.
- [ ] Provider request governor, adaptive polling, caching, and rate-limit discipline.
- [ ] Provider lifecycle state normalized independently from Mentat execution state.

## Learning system

- [ ] Canonical benchmark corpus and grading harness.
- [ ] Model/version/hardware-specific benchmark records.
- [ ] Confidence-aware quality predictor.
- [ ] Calibrated cost, latency, success, and reliability predictions.
- [ ] Prediction drift detection and automatic confidence reduction.
- [ ] Safe low-risk exploration.
- [ ] Champion/challenger shadow routing before policy promotion.
- [ ] Promotion/demotion with audit trail.
- [ ] Routing-regret measurement.
- [ ] Kimi-only baseline and savings measurement.
- [ ] Host/GPU history and bad-host suppression.
- [ ] Vast marketplace/benchmark/report data treated as priors rather than production truth.

## Mentat 1.0 live validation and release

- [ ] Standalone private repository and supply-chain gate.
- [ ] Least-privilege Vast credential/permission matrix live-validated.
- [ ] Low-cost Vast Serverless canary.
- [ ] Actual billing reconciliation.
- [ ] Kimi canary.
- [ ] 100-session / 24-hour / multi-day soak and adversarial testing.
- [ ] Complete normal Windows UX without PowerShell.
- [ ] Threat model and security review.
- [ ] Reproducible build, SBOM, checksums, provenance.
- [ ] Authenticode-signed installer.
- [ ] Clean install / upgrade / repair / rollback / uninstall validation.
- [ ] Mentat 1.0 release gates all closed.

## Target broker expansion beyond the currently frozen 1.0 scope

- [ ] Vast direct-instance backend behind the common backend interface.
- [ ] Pinned broker-only Vast Python SDK adapter.
- [ ] Read-plane and mutation-plane clients with different retry semantics.
- [ ] Least-privilege discovery/lifecycle/billing credential separation where live permissions permit it.
- [ ] Direct-instance offer normalization and lifecycle state machine.
- [ ] Automated Mentat worker provisioning.
- [ ] Worker lease/watchdog.
- [ ] Keep/freeze/stop/destroy economics.
- [ ] Direct-instance host reputation and billing reconciliation.
- [ ] Vast GPU market metrics/trends/locations as routing priors.
- [ ] Vast benchmarks as infrastructure bootstrap priors only.
- [ ] Vast machine reports as host-risk priors when available.
- [ ] Notification-webhook feasibility validated before replacing polling.
- [ ] Serverless-versus-direct evidence campaign.
- [ ] Broker chooses backend using measured quality, latency, reliability, uncertainty, and total cost.

Direct Vast instances are part of the target architecture but must **not silently move the frozen Mentat 1.0 goalposts**. Promoting them into the Mentat 1.0 release scope requires an explicit owner-approved scope change.

---

# Master build roadmap

The roadmap is ordered. Later work may be prepared in parallel when it cannot affect the current gate, but the system should not skip unresolved safety or correctness dependencies.

## Phase 0 — specification and handoff integrity

**Goal:** a brand-new coding AI can enter the repository cold and determine the mission, reality, blockers, and exact next task without old chat history.

- [x] Production contract.
- [x] Frozen 1.0 scope.
- [x] Work-item backlog.
- [x] Execution ledger.
- [x] Complete architecture description.
- [x] Construction contract/roadmap/checklist/resume protocol merged.
- [ ] Keep `docs/mentat/current-state.yaml` synchronized at every meaningful handoff.

**Exit condition:** GitHub, README, production contract, ledger, work items, and current-state file agree on what is built and what comes next.

## Phase 1 — finish the active no-spend desktop work package

**Current engineering phase.**

- [ ] Finish PR #12.
- [x] Malformed upstream output is prevented from becoming positive runtime evidence in the PR work package.
- [x] Desktop/no-spend integration work exists in the PR.
- [x] Diagnose Broker CI failures on Windows and Ubuntu.
- [x] Diagnose Runtime CI failure.
- [x] Repair the implementation without weakening tests/invariants.
- [x] Re-run Broker, Runtime, Desktop, and no-spend acceptance checks.
- [ ] Merge or deliberately supersede PR #12.

**Exit condition:** the active work package is green, evidence is retained, and the ledger is updated.

## Phase 2 — close Gate 1: no-spend local integration

- [ ] Clean Windows install.
- [ ] `mentat doctor` green on target PC.
- [ ] Installed wrapper runs `mentat test no-spend` correctly.
- [ ] Desktop can securely run/display no-spend diagnostics.
- [ ] Actual tool execution proven inside Docker.
- [ ] Gateway/tool environment proven free of Vast/admin credentials.
- [ ] Broker client/admin authentication proven end to end.
- [ ] Reject and approval-timeout behavior.
- [ ] Malformed request/response behavior.
- [ ] Broker/Gateway restart behavior.
- [ ] Shutdown cleanup behavior.

**Exit condition:** every Gate 1 requirement in `docs/mentat/production-contract.md` has evidence.

## Phase 3 — formal broker contracts and backend boundary

- [ ] Stabilize typed `TaskRequirements`.
- [ ] Stabilize typed `ExecutionCandidate`.
- [ ] Stabilize typed `ApprovalLease`.
- [ ] Stabilize typed `ExecutionResult`.
- [ ] Stabilize typed `ProviderState`, `ProviderError`, and `ProviderMarketSnapshot`.
- [ ] Introduce the broker-facing `ComputeBackend` boundary without regressing Serverless behavior.
- [ ] Make the existing Vast Serverless path conform to that boundary.
- [ ] Turn the golden scenarios in this README into executable tests where practical.

**Exit condition:** task intelligence, model intelligence, policy, provider behavior, and learning depend on Mentat contracts instead of raw provider structures.

## Phase 4 — task, context, risk, and verification intelligence

- [ ] Repository-aware scope estimation.
- [ ] Attachment-aware scope estimation.
- [ ] Full context prediction including messages, tools, files, and output reserve.
- [ ] Capability requirements.
- [ ] Tool requirements.
- [ ] Verification availability.
- [ ] Reversibility.
- [ ] Blast radius.
- [ ] Risk tier.

**Exit condition:** the broker produces explainable `TaskRequirements` from observable inputs and retains prior user intent correctly.

## Phase 5 — model and candidate intelligence

- [ ] Versioned model profiles.
- [ ] Experimental / approved / preferred / demoted / retired lifecycle.
- [ ] Capability/context/runtime/hardware eligibility.
- [ ] Candidate plan generation.
- [ ] Quality floor enforcement.
- [ ] Quality and successful-completion prediction.
- [ ] Cold-start and warm-start prediction.
- [ ] Total-cost prediction by component.
- [ ] Failure/reliability penalty.
- [ ] Reuse value.
- [ ] Prediction confidence/sample-size handling.
- [ ] Prediction calibration and interval-coverage tracking.
- [ ] Best / Balanced / Economy / Manual routing modes.
- [ ] Winner, alternative, and rejection explanation.

**Exit condition:** Mentat can select an eligible plan using hard constraints first and evidence-aware economics second.

## Phase 6 — learning engine

- [ ] Canonical benchmark corpus.
- [ ] Deterministic/automatic grading where possible.
- [ ] Model/version/hardware benchmark records.
- [ ] Human rating evidence remains separate.
- [ ] Quality confidence bounds.
- [ ] Cost/latency/success calibration.
- [ ] Drift detection and evidence recency weighting.
- [ ] Safe exploration limited to low-risk/verifiable work.
- [ ] Contextual-bandit-style exploration only inside the safe eligible set.
- [ ] Champion/challenger shadow evaluation before routing-policy promotion.
- [ ] Offline replay against historical decision snapshots.
- [ ] Promotion/demotion policy and audit trail.
- [ ] Routing regret.
- [ ] Kimi-only baseline and savings reporting.
- [ ] Host/GPU performance history.

**Exit condition:** verified outcomes improve predictions and routing without rewriting hard safety policy.

## Phase 7 — Mentat 1.0 live Serverless validation

This phase requires owner approval and the repository/credential gates.

- [ ] Repository safe for real credentials.
- [ ] Scoped Vast credential entered only through the protected broker boundary.
- [ ] Exact Vast permission requirements for the Serverless operations Mentat uses are live-validated.
- [ ] Automatic retry behavior is verified not to undermine Mentat's non-idempotent lifecycle rules.
- [ ] Low-cost Serverless canary.
- [ ] Rejection creates nothing.
- [ ] Approval creates one intended resource.
- [ ] Actual price stays below approved ceiling.
- [ ] Real inference succeeds.
- [ ] Reuse succeeds inside approval scope.
- [ ] Cooling reaches zero paid workers.
- [ ] Crash/restart recovery succeeds.
- [ ] Actual billing reconciled.
- [ ] Kimi canary.
- [ ] Long-context/tool/stream/cancellation/cost caps validated.

**Exit condition:** Gates 2 and 3 have retained real-service evidence.

## Phase 8 — reliability, security, and soak campaign

- [ ] Network loss during create/warm/stream/cool.
- [ ] Ambiguous create response.
- [ ] SDK/helper automatic-retry attempted on a non-idempotent mutation.
- [ ] HTTP 429/rate-limit storm.
- [ ] Malformed provider error shape.
- [ ] Provider permission denied after a key-scope change.
- [ ] Provider status `null`, `loading`, `running`, `stopped`, `frozen`, `exited`, `rebooting`, `unknown`, and `offline` where applicable.
- [ ] Broker kill.
- [ ] Gateway kill.
- [ ] Windows restart and user logoff.
- [ ] Expired approval.
- [ ] Corrupt SQLite.
- [ ] Disk full.
- [ ] Context overflow.
- [ ] Runaway tool loop.
- [ ] Concurrent chats.
- [ ] 100-session campaign.
- [ ] 24-hour campaign.
- [ ] Multi-day campaign.
- [ ] Threat model.
- [ ] Malicious workspace/prompt-injection tests.
- [ ] Security review or explicit accepted-risk record.

**Exit condition:** failures are bounded, recoverable, auditable, and do not leak credentials or paid resources.

## Phase 9 — complete Windows product and release engineering

- [ ] First-run setup wizard.
- [ ] Chat/decision/approval/active-compute/history/models/costs/settings/diagnostics UX.
- [ ] Normal operation requires no PowerShell.
- [ ] Repair/update/rollback/uninstall.
- [ ] Private standalone repository.
- [ ] Protected `main` and required checks.
- [ ] Dependency/secret/license scans.
- [ ] SBOM.
- [ ] Reproducible release.
- [ ] Authenticode signing.
- [ ] Checksums and provenance.
- [ ] Operator and incident runbooks.
- [ ] Clean release-artifact install/upgrade/repair/uninstall.

**Exit condition:** all Mentat 1.0 release gates are closed and the signed artifact works on a clean Windows machine.

## Phase 10 — direct Vast instance backend (target expansion)

Do not begin this because it is exciting while the active release work is broken. The frozen 1.0 scope still governs unless the owner explicitly changes it.

When authorized:

- [ ] Add a pinned `vastai` Python SDK dependency behind a broker-owned adapter.
- [ ] Instantiate the production SDK with an explicitly supplied broker credential; never depend on ambient key-file discovery.
- [ ] Use machine-readable production settings such as `raw=True`, `quiet=True`, `explain=False`, and `curl=False` unless a controlled diagnostic mode explicitly overrides them.
- [ ] Separate read-plane and mutation-plane clients so safe read retries cannot become hidden paid-mutation retries.
- [ ] Set or otherwise enforce **zero automatic retry** for non-idempotent paid mutations unless the specific operation has proven idempotency semantics.
- [ ] Normalize provider error variants into a typed Mentat `ProviderError`.
- [ ] Add a provider request governor for caching, rate limits, coalescing, and adaptive polling.
- [ ] Validate a least-privilege credential matrix rather than assuming permission categories are narrower than they are.
- [ ] Treat Vast `misc` as potentially spending-capable because current permission docs place both search operations and Serverless create/update/delete operations in that category.
- [ ] Use endpoint-level permission constraints where supported and live-validated; never assume an unrestricted `misc` key is read-only.
- [ ] Use `search_offers` only inside the adapter and normalize raw results into Mentat candidates.
- [ ] Use `create_instance` only after policy + authenticated approval lease validation.
- [ ] Re-check the selected offer/price immediately before the paid mutation.
- [ ] Persist the returned instance/contract ID immediately after successful creation.
- [ ] Reconcile ambiguous create outcomes before any retry.
- [ ] Evaluate `cancel_unavail=True` for interactive on-demand acquisitions; make it production default only after live validation proves the desired behavior.
- [ ] Implement bounded readiness polling.
- [ ] Preserve provider `actual_status`, `intended_status`, `cur_state`, and `status_msg` separately from Mentat execution state.
- [ ] Handle documented instance states `null`, `loading`, `running`, `stopped`, `frozen`, `exited`, `rebooting`, `unknown`, and `offline` explicitly where applicable.
- [ ] Never poll forever while storage charges continue.
- [ ] Require more than provider `running` before Mentat marks a worker ready: network reachability, health, expected model/runtime identity, and a controlled test inference must pass.
- [ ] Version/integrity-check the Mentat worker bootstrap or image.
- [ ] Start the OpenAI-compatible runtime and health-check it before routing inference.
- [ ] Record acquisition, image pull, provisioning, model download/load, TTFT, throughput, runtime, and teardown timing.
- [ ] Model `running`, `frozen`, `stopped`, and destroyed resources as economically different states.
- [ ] Record GPU, storage, bandwidth, and other provider charge components separately when available.
- [ ] Reconcile provider charges to Mentat's predicted cost components and calculate prediction error.
- [ ] Add independent worker lease/watchdog protection.
- [ ] Add no-spend simulator coverage before a live direct-instance canary.

The current Vast SDK/API documentation confirms programmatic primitives for scoped keys, offer search, benchmark search, market metrics, instance creation/status, data movement, stop/destroy, machine reports, billing charges, and notification webhooks. Those provider primitives are **inputs to a Mentat backend adapter**, not permission to expose Vast control directly to models or tools.

**Exit condition:** direct instances satisfy the same credential, approval, reconciliation, billing, evidence, and failure-safety contract as Serverless.

## Phase 11 — backend comparison and fleet intelligence

- [ ] Compare Serverless and direct instances on equivalent model/task workloads.
- [ ] Measure cold/warm latency, quality, throughput, completion rate, and actual total cost.
- [ ] Build direct-host reputation and temporary suppression.
- [ ] Add Vast marketplace supply/demand/price features with source timestamps and freshness bounds.
- [ ] Add Vast benchmark priors without allowing them to become automatic quality-promotion evidence.
- [ ] Add recent machine-report signals when available, weighted below Mentat's own verified production history.
- [ ] Learn keep-warm / freeze / stop / destroy economics.
- [ ] Include storage and re-provisioning costs.
- [ ] Evaluate signed notification webhooks as a supplement to polling only after event types and delivery/replay behavior are validated.
- [ ] Let the broker choose backend only from eligible, validated plans.

**Exit condition:** Mentat can explain why a particular model + hardware + backend plan wins from measured evidence.

## Phase 12 — continuous broker optimization

- [ ] Detect prediction error and drift.
- [ ] Recalibrate cost/latency/quality/success models.
- [ ] Revalidate new model/runtime/provider-adapter versions.
- [ ] Demote regressions quickly.
- [ ] Safely explore cheaper alternatives.
- [ ] Preserve hard security/spending constraints outside the learning loop.
- [ ] Continuously report savings, regret, reliability, calibration, and quality versus baselines.
- [ ] Keep provider-market priors fresh without letting external data overwrite stronger local evidence.

**Exit condition:** Mentat becomes more efficient over time without becoming less predictable, less safe, or less explainable.

---

# What Mentat is

Mentat is a local AI operating system that can dynamically obtain the right amount of remote intelligence for each job.

The user should be able to talk to Mentat like a normal AI assistant. Behind the scenes, Mentat asks questions such as:

- What kind of task is this?
- How difficult is it?
- What capabilities are required?
- How much context must the model understand?
- How dangerous would an incorrect answer be?
- Can the result be automatically verified?
- Which registered models are eligible?
- What hardware can run those models correctly?
- Is compatible compute already warm and approved?
- What does Vast.ai currently offer?
- Is the current GPU market unusually expensive or constrained?
- How reliable are those hosts based on marketplace data, recent provider signals, and Mentat's own history?
- How long will a cold start take?
- What will the entire job cost, not just the GPU hourly rate?
- How uncertain are those predictions?
- Is the proposed spend permitted?
- Should compute remain warm, be cooled, frozen, stopped, or destroyed afterward?

The system should become better at answering those questions as it operates.

A useful mental model is:

```text
Request
  -> requirements
  -> eligible models
  -> eligible hardware
  -> provider/market snapshot
  -> eligible compute backends
  -> candidate execution plans
  -> conservative predictions + uncertainty
  -> policy and approval
  -> execution
  -> verification
  -> billing reconciliation
  -> telemetry and rating
  -> evidence
  -> better future decisions
```

---

# System architecture

```text
                              USER
                                |
                                v
                           Mentat.exe
                                |
                                v
                            OpenClaw
                  conversations / tools / memory
                     repositories / approvals
                                |
                                v
                    +-----------------------+
                    |     MENTAT BROKER     |
                    +-----------+-----------+
                                |
                 +--------------+--------------+
                 |              |              |
                 v              v              v
              Task           Context          Risk /
             analysis       estimation      verification
                 |              |              |
                 +--------------+--------------+
                                |
                                v
                         Model Registry
                                |
                                v
                        Hardware Planner
                                |
                                v
                    Compute Backend Registry
                         /               \
                        /                 \
                       v                   v
             Vast Serverless        Vast Direct Instance
                       \                   /
                        \                 /
                         v               v
                     Provider Adapter Layer
                    state / market / errors
                                |
                                v
                         Candidate Plans
                                |
                                v
                   Hard Eligibility Filters
                                |
                                v
                         Broker Scoring
                                |
                                v
                      Spend / Policy Governor
                                |
                                v
                       Local User Approval
                         when required
                                |
                                v
                             Execute
                                |
                                v
                        Verify / Measure
                                |
                                v
                    Billing Reconciliation
                                |
                                v
                        Execution History
                                |
                                v
                         Learning Engine
                                |
                                +----> future decisions
```

The GPU is not Mentat.

The model is not Mentat.

The endpoint is not Mentat.

The Vast SDK is not Mentat.

**Mentat is the local operator, broker, policy boundary, execution governor, evidence store, and learning loop that decides how those resources should be used.**

---

# How a request flows through Mentat

A typical request should eventually follow this lifecycle:

```text
1. User sends request
2. OpenClaw supplies conversation/tool/repository context
3. Mentat classifies the task
4. Mentat estimates required context and capabilities
5. Mentat evaluates risk and verification options
6. Model registry produces eligible models
7. Hardware planner produces valid hardware configurations
8. Provider adapter supplies normalized live market/resource information
9. Compute backends produce execution candidates
10. Hard eligibility removes candidates that cannot safely satisfy requirements
11. Predictors estimate quality, success, latency, total cost, and uncertainty
12. Broker scores only remaining eligible candidates
13. Spend policy rejects anything outside hard limits
14. New paid compute waits for authenticated local approval
15. Budget/approval authority is reserved atomically before a paid mutation
16. Approved compute is created, reused, or warmed
17. Provider lifecycle state is reconciled until the resource is truly ready
18. Inference runs
19. Tools run locally through the OpenClaw security boundary
20. Mentat verifies the result where possible
21. Runtime telemetry is recorded
22. Provider billing is reconciled when available
23. Human quality feedback may be recorded separately
24. Compute is kept warm, cooled/frozen/stopped, or destroyed according to validated policy
25. The learning system updates evidence for future decisions
```

Each stage exists for a reason. A system that skips these stages and simply sends every task to one expensive model is not the Mentat we are trying to build.

---

# 1. Task analysis

The broker first determines what kind of work the user is asking Mentat to perform.

Mentat should not delegate this decision to a weaker model and blindly trust its opinion. Routing should be driven by observable characteristics of the request and retained user intent.

Example:

```text
Task:
"Change the button text from Buy to Purchase."

Classification:
coding

Complexity:
low

Repository scope:
small

Tools required:
yes

Risk:
low

Verification:
easy
```

Compare that with:

```text
Task:
"Review the entire Mentat broker, find lifecycle race conditions,
redesign it, and implement the corrections."

Classification:
repository architecture

Complexity:
very high

Repository scope:
large

Tools required:
yes

Risk:
high

Verification:
complex
```

Those requests should not automatically use the same model or compute budget.

Mentat also preserves prior intent for short follow-up instructions such as:

```text
go
continue
fix it
try again
```

A short latest message does not mean the underlying task suddenly became small.

---

# 2. Context estimation

Model intelligence is only useful when the model can see enough of the problem.

Mentat therefore estimates the complete context requirement, including:

- current user request
- relevant prior conversation
- repository files
- attachments
- tool schemas
- system instructions
- expected tool results
- output reservation
- previous task state

A model may be inexpensive and capable but still be ineligible because its context window is too small.

Conceptually:

```text
required_context =
    messages
  + repository excerpts
  + attachments
  + tool schemas
  + system instructions
  + output reserve
```

Context compatibility is a hard eligibility condition, not merely a preference.

---

# 3. Risk and verification analysis

Mentat should separately estimate:

1. **How harmful would an incorrect result be?**
2. **How easily can the result be verified?**

Examples of increasing risk:

```text
README wording change                 low
CSS change                            low
application business logic            medium
payment calculation                    high
authentication or authorization        high
credential or infrastructure handling  very high
```

Verification may include:

```text
unit tests
integration tests
lint
type checking
compilation
schema validation
runtime health checks
known-answer checks
independent model review
human review
```

A cheaper experimental model can safely receive more opportunities on low-risk tasks with strong automatic verification. High-risk work with weak verification should strongly favor models with better measured evidence.

---

# 4. Model registry

Mentat maintains a controlled registry of models it knows how to use.

The initial registry includes models such as:

1. **Kimi K2.7 Code** — dependable primary for high-risk, tool-heavy, long-context, and repository-scale work.
2. **Qwen3 Coder 30B A3B** — lower-cost coding candidate after sufficient local evidence.
3. **DeepSeek Coder V2 Lite** — inexpensive candidate for simpler text and coding work after sufficient local evidence.

A model entry should evolve beyond a name. It should describe the complete operational profile.

Example conceptual profile:

```yaml
id: qwen3-coder-30b-a3b
version: pinned-model-version
status: experimental

capabilities:
  coding: true
  reasoning: true
  tool_calling: true
  vision: false

context:
  max_tokens: 65536

runtime:
  engine: vllm
  runtime_version: pinned
  image_digest: sha256:...
  openai_compatible: true

hardware:
  minimum_vram_gb: 32
  preferred_gpu_classes:
    - RTX_5090
    - A100_80GB
    - H100

measured_evidence:
  coding_simple: pending
  coding_medium: pending
  repository_architecture: pending
```

The registry should eventually track a model lifecycle such as:

```text
experimental
   -> approved
   -> preferred for selected task classes
   -> demoted when evidence worsens
   -> retired
```

A cheaper model is never promoted simply because a public benchmark claims it is good. Mentat should prefer its own verified local evidence for the workloads it actually performs.

---

# 5. Hardware planning

Once eligible models are known, Mentat determines which hardware configurations can actually run them.

The planner considers constraints such as:

```text
GPU architecture
GPU count
VRAM
CUDA compatibility
system RAM
CPU allocation
disk capacity
disk performance
PCIe generation
NVLink or other interconnect requirements
runtime compatibility
```

Example conceptual mapping:

```text
smaller coding model
    -> 1 x RTX 5090 may be sufficient

larger model
    -> multiple RTX 5090s or a datacenter GPU

very large long-context primary
    -> larger multi-GPU H100/H200-class configuration
```

The broker should determine technically valid hardware classes first, then compare real execution plans. The cheapest hourly GPU is not automatically the cheapest successful task.

---

# 6. Compute backends

Mentat should treat the method of obtaining compute as part of the routing decision.

The target abstraction is:

```text
ComputeBackendRegistry
  |
  +-- VastServerlessBackend
  |
  +-- VastInstanceBackend
```

Additional providers can be added later without rewriting the broker's task and model logic.

## Vast Serverless

The current Mentat implementation is primarily built around guarded Vast Serverless endpoints.

Conceptually:

```text
Mentat
  -> Vast Serverless endpoint
  -> workergroup
  -> GPU worker(s)
  -> model runtime
```

Advantages include:

- reusable endpoint identity
- managed worker lifecycle
- zero-floor cooling
- simpler OpenAI-compatible serving
- easier reuse of approved sessions

## Direct Vast instance

The target broker should also support directly renting a Vast marketplace machine.

Conceptually:

```text
Mentat
  -> normalized marketplace search
  -> rent approved CUDA instance
  -> provision Mentat worker
  -> install/verify runtime
  -> load selected model
  -> start OpenAI-compatible API
  -> verify worker identity and health
  -> inference
```

Direct instances give Mentat finer control over the exact host, GPU, storage, runtime, provisioning path, and lifecycle.

**Important:** direct Vast instance support is a target architecture capability and should not be confused with the currently validated Serverless path unless and until it is implemented and tested. It is not silently part of the frozen Mentat 1.0 scope.

---

# 7. Vast marketplace discovery and market intelligence

Mentat should evaluate complete offers, not just GPU names and hourly prices.

A Vast offer can contain useful signals such as:

```text
GPU model
GPU count
VRAM
CUDA version
PCIe generation
CPU model
allocated CPU cores
system RAM
network download bandwidth
network upload bandwidth
disk type
disk throughput
available disk
host verification
reliability
maximum rental duration
location
GPU hourly price
bandwidth price
storage price
machine ID
host ID
```

A normalized candidate might look like:

```text
ComputeCandidate

GPU: RTX 5090
GPU count: 1
VRAM: 32 GB
Price: $0.300/hr
Reliability: 99.38%
Download: 1697 Mbps
Upload: 1766 Mbps
Disk: NVMe
CPU: AMD EPYC
Verified: yes
Location: California, US
Host: 402342
```

Two machines with the same GPU and hourly price can still have very different network, disk, CPU, reliability, and historical performance. Mentat should treat them as different candidates.

## Market-intelligence inputs

Current Vast documentation exposes more than individual offer rows. The provider adapter may eventually consume, cache, and timestamp:

- **GPU metrics** — current supply, availability, utilization and price distribution, including price percentiles and performance-per-dollar fields;
- **GPU trends** — time-series supply, demand and pricing data;
- **GPU locations** — geographic distribution of marketplace GPUs;
- **search benchmarks** — benchmark records containing fields such as machine, image, model, GPU count, benchmark name, update time, and score;
- **machine reports** — recent provider-side machine problem reports when available.

These are **market and infrastructure priors**, not proof that a model is good at the user's task.

A provider benchmark may help estimate whether a new host/configuration is worth exploring. It must not directly promote a model into high-risk production work.

## Market snapshot contract

Every external market observation used by routing should carry at least:

```text
provider
source endpoint/capability
observed_at
expires_at / freshness policy
raw provider identity
normalized fields
adapter version
confidence / evidence tier
```

Stale market data may inform planning, but paid acquisition must revalidate critical price/availability information immediately before spending.

## Provider request governor

Provider reads should not be scattered across independent subsystems. A central request governor should coordinate:

```text
search offers
market metrics/trends
host reports
benchmarks
instance status
serverless status
billing reads
```

The governor should support:

- request coalescing;
- short-lived caching by data type;
- endpoint-aware rate-limit budgets;
- adaptive polling during lifecycle transitions;
- jitter where appropriate;
- explicit stale-data markers;
- observability for 429s, retries, and provider latency.

Vast currently documents endpoint/identity-based rate limits and no `Retry-After` header for HTTP 429. Mentat therefore needs its own request discipline rather than relying on aggressive polling.

---

# 8. Host reputation

Marketplace statistics are useful, but Mentat should build its own host history from real jobs.

Example:

```text
Host 402342

Mentat deployments:        213
Successful deployments:    211
Median startup:             24 sec
Median model load:          46 sec
Network failures:           1
Unexpected shutdowns:       0
Average throughput:         81 tok/sec
Mentat host score:          96.4 / 100
```

Another host may appear cheap and attractive but accumulate evidence such as:

```text
9 deployments
4 startup failures
2 interrupted jobs
poor disk performance
```

Mentat can penalize or temporarily suppress that host.

## Host evidence sources

A host score should keep its sources separate rather than collapsing everything into one unexplained number:

```text
Vast marketplace reliability     external prior
Vast benchmark records           external prior
Vast recent machine reports      external risk prior, when available
Mentat startup history           local measured evidence
Mentat throughput history        local measured evidence
Mentat disconnect/failure rate   local measured evidence
Mentat cost reconciliation       local measured evidence
```

Mentat's own recent verified history should eventually outweigh generic external priors for the exact workload/configuration it has observed.

External provider reports should decay with age and should not be double-counted with failures already observed by Mentat.

The broker therefore learns not merely that:

```text
RTX 5090 is good
```

but that a specific GPU class on a specific host with a specific storage/network/runtime profile has performed well or poorly for Mentat's real workload.

---

# 9. Direct instance provisioning

When the future direct-instance backend chooses a raw Vast CUDA worker, Mentat should automatically transform it into an inference service.

The target flow is:

```text
Search normalized offers
  -> validate freshness
  -> validate policy and approval lease
  -> re-check selected offer/price
  -> reserve approved budget authority
  -> create exactly one intended instance
  -> persist returned instance ID immediately
  -> poll bounded provider lifecycle state
  -> CUDA container starts
  -> Mentat provisioning script/image runs
  -> verify runtime dependencies
  -> install/verify vLLM/SGLang when needed
  -> acquire pinned model revision
  -> load model
  -> start OpenAI-compatible server
  -> verify health + model/runtime identity
  -> controlled test inference
  -> mark worker ready
```

Vast's CUDA development environment supports a provisioning-script mechanism, which is a natural fit for this design. Vast's Python SDK also exposes programmatic authentication, offer search, instance creation/status, data movement, stop, and destroy operations.

A worker bootstrap can receive controlled configuration such as:

```text
MENTAT_MODEL=<registered model id>
MENTAT_MODEL_REVISION=<pinned revision>
MENTAT_RUNTIME=vllm
MENTAT_RUNTIME_VERSION=<pinned version>
MENTAT_PORT=8000
MENTAT_JOB_ID=<job id>
MENTAT_LEASE_SECONDS=<bounded lease>
```

The provisioning path should be versioned, integrity checked, and treated as part of Mentat's supply chain.

---

# Vast provider adapter contract

Provider SDKs are implementation helpers. They are **not** Mentat's policy authority.

The target architecture is:

```text
                    Mentat Broker
                         |
         +---------------+----------------+
         |               |                |
         v               v                v
   Vast Read Plane   Vast Spend Plane   Billing Plane
         |               |                |
         +---------------+----------------+
                         |
                  Vast Adapter
                         |
                         v
                    Vast API/SDK
```

## SDK construction rules

The current VastAI constructor documents options including `api_key`, `server_url`, `retry`, `raw`, `explain`, `quiet`, and `curl`. Production Mentat should instantiate the SDK explicitly and predictably.

Target production posture:

```python
VastAI(
    api_key=broker_owned_secret,
    retry=<plane-specific>,
    raw=True,
    explain=False,
    quiet=True,
    curl=False,
)
```

The official VastAI reference currently contains inconsistent text for implicit API-key file fallback paths. Mentat must therefore **not depend on implicit key discovery at all**. The broker passes its protected credential explicitly.

## Read plane versus spend plane

Safe read operations and paid mutations have different retry requirements.

Current Vast SDK documentation says the normal `VastAI` client automatically retries HTTP 429 by default, while the Serverless client retries 408, 429, and 5xx with exponential backoff/jitter.

That convenience is useful for idempotent reads. It is dangerous if it can hide a repeated non-idempotent paid mutation.

Target rule:

```text
READ PLANE
  automatic bounded retry may be allowed
  cache/coalesce where useful
  record retry count and latency

SPEND PLANE
  no hidden automatic retry of non-idempotent create/start/warm mutations
  ambiguous result -> RECONCILE -> then decide
```

For the normal VastAI client, a mutation client should use `retry=0` unless the exact operation has proven safe idempotency/retry semantics. For Serverless or other helpers with internal retries, Mentat must either configure/bypass those retries for spending mutations or wrap only operations whose idempotency behavior has been explicitly validated.

## Error normalization

Vast currently documents more than one error response shape. Some responses contain:

```json
{
  "success": false,
  "error": "invalid_args",
  "msg": "..."
}
```

while some endpoints may return only `msg` or `message`.

Raw provider errors must therefore be normalized into a Mentat-owned structure such as:

```text
ProviderError
  provider
  operation
  http_status
  provider_code
  message
  retryable_read
  ambiguous_mutation
  rate_limited
  auth_or_permission_failure
  raw_shape_version
```

The rest of the broker should not branch on random provider dictionaries.

## Least-privilege credential design

Vast currently documents permission categories including `instance_read`, `instance_write`, `user_read`, `user_write`, `billing_read`, `billing_write`, `machine_read`, `machine_write`, `misc`, `team_read`, and `team_write`, plus endpoint-specific constraints.

Mentat should use the smallest permissions that can actually perform each broker role.

A future setup may use:

```text
OWNER / BOOTSTRAP CREDENTIAL
  only during explicit setup
  may create Mentat-specific scoped keys
  removed from Mentat runtime storage afterward
  never automatically revoke/delete an owner's unrelated key

DISCOVERY / READ CREDENTIAL
  only the exact search/read endpoints required

LIFECYCLE CREDENTIAL
  only exact instance/serverless lifecycle operations required

BILLING / RECONCILIATION CREDENTIAL
  only the exact read permission needed for charges
```

### Important `misc` warning

Current Vast permission documentation places **both** search operations and Serverless endpoint/workergroup create/update/delete operations under `misc`.

Therefore:

> **An unrestricted `misc` key is not a read-only discovery key.**

Mentat should use endpoint-level restrictions/constraints when the live API and permission identifiers support them. If the required least-privilege split cannot be proven, the credential remains isolated to the broker process and the limitation is recorded honestly.

### Billing permission must be validated, not guessed

The current Vast permission reference describes `billing_read` primarily in terms of invoices/earnings, while `show charges` is documented separately as the per-instance GPU/storage/bandwidth cost endpoint. Mentat must live-test the minimum permission required to read charges rather than assuming the category from a label.

## Provider lifecycle state normalization

Current Vast instance documentation exposes multiple status dimensions. Mentat should preserve them separately:

```text
ProviderInstanceState
  actual_status
  intended_status
  cur_state
  status_msg
  observed_at
```

Documented `actual_status` values include:

```text
null       provisioning
loading    image/container startup
running    container executing; GPU charges apply
stopped    container halted; disk charges continue, no GPU charges
frozen     memory preserved; GPU charges continue
exited     container process exited unexpectedly
rebooting  transient restart
unknown    no recent host heartbeat
offline    host disconnected from Vast servers
```

Mentat execution state is separate:

```text
ACQUIRING
PROVISIONING
READY
RUNNING
VERIFYING
RECONCILING
RELEASING
FAILED_...
```

Do not collapse provider status and Mentat job status into one field.

## Readiness contract

Provider `running` is necessary but not sufficient for `Mentat READY`.

A worker becomes ready only after all applicable checks pass:

```text
provider state is compatible with running
network route reachable
runtime health endpoint passes
expected runtime/version identity matches
expected model/profile/revision identity matches
controlled inference probe succeeds
approval lease still valid
```

## `cancel_unavail`

The Vast `create_instance` SDK currently exposes `cancel_unavail`, documented as returning an error when scheduling fails rather than creating a stopped instance.

For interactive Mentat jobs, that may be preferable to receiving a stopped/unavailable resource. Treat it as a candidate policy and test it in no-spend/live canaries before making it a production default.

## Rate limits and adaptive polling

Vast documents rate limits per endpoint and identity, and HTTP 429 responses without a `Retry-After` header.

Mentat should therefore use state-aware polling rather than fixed aggressive loops.

Example policy:

```text
new transition:
  poll relatively quickly

known long image/model pull:
  back off

near predicted ready time:
  shorten interval modestly

429 / provider pressure:
  expand interval with jitter

terminal/error state or deadline:
  stop polling and reconcile
```

Polling strategy itself should be measurable and later tunable from real startup distributions.

## Notifications as an optional optimization

The current Vast documentation index includes signed notification-webhook management and discoverable notification types.

Mentat may investigate webhooks as a supplement to polling, but must not assume that the notification types required for instance/serverless readiness exist until they are enumerated and tested.

Any webhook path must validate signatures, protect the signing secret, handle duplicates/replays, and retain polling/reconciliation as a recovery path.

---

# 10. Mentat workers

A direct GPU instance should become a temporary **Mentat Worker**.

Conceptually:

```text
Mentat Worker
  |
  +-- CUDA
  +-- Python runtime
  +-- vLLM / SGLang / approved engine
  +-- selected pinned model revision
  +-- OpenAI-compatible inference API
  +-- health/identity monitor
  +-- metrics collector
  +-- bounded lease/watchdog
  +-- shutdown controller
```

The worker is disposable muscle. The broker remains the brain.

The worker should expose only the capabilities required to serve inference and report health/telemetry. Infrastructure credentials and local user tools do not belong inside the model process.

---

# 11. Security and spending authority

Mentat has a hard security rule:

> **A language model cannot create, warm, resize, approve, retry, extend, or otherwise authorize paid compute.**

Spending authority belongs to the local broker and ultimately the local authenticated user.

The current implementation protects the Vast key inside the broker boundary. The target design narrows this further with broker-owned least-privilege credential roles where live Vast permissions allow it.

```text
                         Local PC

+-------------------------------------------------------+
| Broker security boundary                              |
|                                                       |
|  Credential vault                                     |
|    - current protected Vast credential                |
|    - future scoped read credential                    |
|    - future scoped lifecycle credential               |
|    - future scoped billing credential                 |
|                                                       |
|  Spend / Policy Governor                              |
|    - approval leases                                  |
|    - price ceilings                                   |
|    - session/job budgets                              |
|    - atomic spend reservation                         |
|    - kill switch                                      |
+---------------------------+---------------------------+
                            |
                 non-spending authenticated API
                            |
+---------------------------v---------------------------+
| OpenClaw Gateway / tools / Mentat.exe                 |
|   - no Vast spending credential                       |
+---------------------------+---------------------------+
                            |
                            v
                       Model endpoint
                            |
                            X
                     no Vast API key
```

Approval and provider credentials must never appear in:

- model prompts
- tool environments
- URLs
- logs
- Git history
- repository workspaces
- provider diagnostic output that is retained without redaction

The current Windows installation protects the Vast API key with Windows DPAPI for the current operating-system user.

## Credential bootstrap target

If Mentat later automates scoped-key creation, the setup flow should be explicit:

```text
owner supplies bootstrap-capable key locally
      -> Mentat creates/validates narrowly scoped runtime keys
      -> Mentat removes bootstrap key from its own runtime storage
      -> owner key is NOT silently deleted/revoked
```

The everyday broker should not require `user_write`, `billing_write`, `machine_write`, or team-management authority unless a future feature explicitly requires and separately approves it.

## Spend Governor target

Every operation capable of increasing paid exposure should pass through one narrow internal governor.

```text
proposed paid mutation
      -> verify approval lease
      -> verify policy
      -> verify current price/resource identity
      -> atomically reserve worst-case authorized exposure
      -> perform one controlled mutation
      -> persist remote identity
      -> reconcile result
```

This prevents two concurrent jobs from each believing the same remaining budget is available.

---

# 12. Candidate generation and scoring

Mentat should score complete **execution plans**, not isolated GPUs.

A candidate is a combination of factors such as:

```text
Candidate
  |
  +-- model + exact version/profile
  +-- runtime + image/bootstrap identity
  +-- hardware configuration
  +-- compute backend
  +-- specific host or Serverless profile
  +-- current market snapshot
  +-- expected quality
  +-- expected startup time
  +-- expected inference time
  +-- expected reliability
  +-- expected total cost
  +-- uncertainty/confidence
```

Example:

```text
Candidate A

Model: Qwen
Backend: Vast Direct Instance
GPU: 1 x RTX 5090
Host: 402342
Predicted quality: 4.5 / 5
Quality lower bound: 4.2
Predicted cold start: 95 sec
Latency upper bound: 150 sec
Predicted total cost: $0.014
Cost upper bound: $0.025
```

versus:

```text
Candidate B

Model: Kimi
Backend: Vast Serverless
GPU: larger multi-GPU profile
Predicted quality: 4.9 / 5
Quality lower bound: 4.7
Predicted startup: 30 sec
Predicted inference: 15 sec
Predicted total cost: $0.41
Cost upper bound: $0.50
```

The correct choice depends on the task requirements.

A low-risk CSS change probably does not justify paying many times more for a small quality advantage. A repository-wide architecture or security task may justify exactly that premium.

## Hard filters before scoring

A candidate that violates a hard requirement is **ineligible**, not merely lower-scoring.

Hard filters include:

```text
capability
context
model/profile status
runtime compatibility
hardware compatibility
security policy
quality lower bound
risk policy
reliability floor
provider availability
approval scope
hourly price ceiling
worst-case cost bound
lease expiration
```

Only eligible candidates reach economic scoring.

Conceptually the broker is optimizing:

```text
expected useful result
  = expected quality
  x probability of successful completion
  x reliability

while minimizing:
  total successful-task cost
  latency
  failure/retry risk
  uncertainty
```

The production implementation should use explicit, testable scoring rules rather than a vague single formula.

---

# 13. Total-cost prediction and reconciliation

GPU hourly price is only one component of real task cost.

Mentat should estimate cost by component:

```text
TOTAL EXPECTED COST

compute / GPU runtime
+ storage
+ bandwidth
+ endpoint/instance acquisition effects
+ container/image startup
+ provisioning
+ model download
+ model loading
+ inference runtime
+ retry probability
+ failed-start probability
+ fallback probability
+ warm idle time
+ teardown/restart effects
```

The broker should also estimate total latency:

```text
TOTAL EXPECTED LATENCY

market search
+ acquisition
+ image pull
+ provisioning
+ model download
+ model load
+ queue/warmup
+ inference
+ verification
```

A $0.30/hour GPU that takes ten minutes to become useful can be worse for an interactive job than a more expensive worker that is already warm.

## Reconcile predicted cost to provider charges

Vast's current `show charges` API is documented as reporting per-instance charges including GPU, storage, and bandwidth, and can carry endpoint/workergroup metadata for applicable records.

Mentat should retain both prediction and actual provider evidence:

```text
Predicted:
  gpu:       $0.018
  storage:   $0.003
  bandwidth: $0.001
  total:     $0.022

Actual:
  gpu:       $0.020
  storage:   $0.004
  bandwidth: $0.001
  total:     $0.025

Prediction error:
  +$0.003
```

Actual provider billing remains the source of truth. Mentat uses the error to improve future cost predictions.

Do not train one opaque `cost` number when useful components are available. Component-level learning makes failures and drift much easier to diagnose.

## Economic north-star metric

The broker should track:

```text
TOTAL REAL COST
-------------------------------
VERIFIED SUCCESSFUL TASKS
```

A model that costs less per attempt but fails often and triggers retries may be more expensive per successful task.

---

# 14. Cold starts and reuse

Cold-start behavior can dominate both cost and user experience.

Example:

```text
GPU rental rate:       $0.30/hr
instance startup:      20 sec
model download:       180 sec
model load:            90 sec
inference:             30 sec
```

The inference itself took only thirty seconds, but the user waited more than five minutes.

Mentat therefore needs to distinguish:

```text
cold response latency
warm response latency
```

A worker that performs poorly for one-off interactive requests may be excellent for a long coding session.

Mentat should reuse already-approved compatible compute when policy allows it.

Example:

```text
Keep Qwen/5090 worker warm for 8 minutes.

Second coding request arrives after 3 minutes.

Reuse existing worker:
  no marketplace acquisition
  no model download
  no model load
  near-immediate inference
```

Over time the broker can learn the economically useful warm window from actual request-arrival patterns, GPU price, restart cost, storage cost, and cold-start distributions.

---

# 15. Keep, freeze, stop, cool, or delete

Different backends expose different lifecycle choices. Provider words must not be treated as interchangeable economic states.

## Serverless

A Serverless endpoint can remain reusable while its worker floor is cooled to zero when idle.

Conceptually:

```text
endpoint identity remains
workers cool to zero
future approved work can reuse endpoint identity
```

## Direct instance target

Current Vast instance documentation distinguishes at least these relevant states:

### Running / keep warm

```text
container executing
GPU charges apply
model may stay loaded
fast next request
```

### Frozen

```text
container memory preserved
GPU charges still apply
NOT equivalent to stopped compute
```

A frozen instance may be operationally useful in some workflows, but it is not a cheap sleep state if GPU charges continue.

### Stopped

```text
container halted
GPU charges stop
storage charges continue
future restart may avoid rebuilding all state
```

### Destroyed

```text
instance removed
instance data is lost according to provider destroy semantics
avoidable instance charges end
next job requires a cold path unless separate persistent storage exists
```

The broker should compare the expected cost of keeping compute running, freezing, stopping, or destroying based on the probability and timing of future tasks.

Example:

```text
Expected next task: 4 minutes
  -> keep warm may win

Expected next task: several hours
  -> stop may win

Expected next task: tomorrow or unknown
  -> destroy may win

Frozen:
  -> only when its operational benefit exceeds continued GPU billing
```

These are policy decisions backed by measured evidence, not hard-coded guesses forever.

---

# 16. Spend policy and approval

Before any paid compute is started, the candidate must pass hard policy limits.

Examples include:

```text
maximum hourly rate
maximum expected job cost
maximum worst-case authorized job cost
maximum session cost
maximum session duration
maximum simultaneous paid model sessions
maximum retry/fallback spend
maximum exploration spend
approved providers
approved GPU classes
approved model profiles
```

New paid sessions require authenticated local approval.

A decision UI should explain both the expected spend and the maximum authorized exposure.

Example:

```text
MENTAT COMPUTE DECISION

Task:
Repository architecture review

Selected model:
Kimi K2.7 Code

Backend:
Vast Serverless

Expected quality:
High

Estimated startup:
42 sec

Expected task cost:
$0.28

Maximum authorized cost:
$0.50

Reason:
Repository-scale reasoning requires the highest validated quality tier.

[ APPROVE ]   [ REJECT ]
```

Approval is a **bounded lease**, not unlimited permission.

For example:

```text
Model/profile scope: Kimi profile X
Backend scope: Vast Serverless
Maximum total cost: $0.50
Maximum hourly rate: $4.00
Maximum paid resource count: 1
Lease expires: 30 minutes
```

The broker must not silently turn that approval into a larger or longer spend.

---

# 17. Inference and tools

Once approved compute is ready:

```text
OpenClaw
  -> Mentat broker
  -> selected approved endpoint/worker
  -> model
```

The selected model provides inference.

OpenClaw remains responsible for local tools, memory, repository access, and agent execution.

The model can request tool actions through the local agent loop, but it does not receive infrastructure credentials or unrestricted host access.

Production tool execution should remain inside the intended Docker sandbox boundary with elevated host escape disabled.

---

# 18. Verification

Receiving an HTTP 200 response is not the same as completing the task successfully.

Mentat should verify outputs whenever practical.

Examples:

```text
Code changes:
  tests
  lint
  compile
  type check
  targeted runtime checks

Structured output:
  schema validation

Streaming inference:
  valid protocol termination

Tool calls:
  valid structure
  successful tool execution

Known-answer benchmark:
  deterministic expected result
```

Verification strength should be recorded explicitly:

```text
strong:
  deterministic tests / compile / schema / known-answer

medium:
  independent model/rubric/cross-check

weak:
  same-model self-evaluation
```

Task risk should influence the minimum verification strength required.

A malformed or failed upstream result must not become a successful learning sample.

---

# 19. Telemetry and execution history

Every completed decision should create a structured operational record.

A future record may contain fields such as:

```text
Task ID:                    82174
Task class:                 coding-medium
Model:                      Qwen
Model version:              pinned version
Runtime/image profile:      pinned identity
Backend:                    Vast Direct
GPU:                        RTX 5090
Host:                       402342
Market snapshot observed:   timestamp
Marketplace price:          $0.300/hr
Provider actual_status:     running
Provider status history:    retained transitions
Startup time:               18.4 sec
Provision time:             21.8 sec
Model download:             48.1 sec
Model load:                 32.6 sec
Time to first token:        0.77 sec
Generation throughput:      84.2 tok/sec
Inference duration:         21.4 sec
Total worker lifetime:      143.7 sec
Provider read retries:      1
Provider mutation retries:  0
Rate-limit events:          0
Estimated GPU cost:         ...
Estimated storage cost:     ...
Estimated bandwidth cost:   ...
Estimated total cost:       $0.012
Actual reconciled cost:     pending
Prediction error:           pending
Result:                     success
Verification:               passed / strong
Human rating:               5/5
```

Runtime measurements and human quality ratings are deliberately separate forms of evidence.

The history should answer questions such as:

- Which model is best for TypeScript debugging?
- Which model is cheapest per verified successful simple code edit?
- Which hosts fail most often?
- Does H100 beat RTX 5090 after cold-start time is included?
- Is Serverless or a direct instance better for a specific model/task class?
- Which provider-market conditions predict poor acquisition times?
- How accurate are our quality/cost/latency intervals?
- How much money has the broker saved versus a Kimi-only policy?

---

# 20. Human ratings

Automatic verification cannot judge everything.

Mentat therefore supports human quality evidence separately from runtime telemetry.

Conceptually:

```text
How good was this result?

1  2  3  4  5
```

A rating belongs to the exact decision context:

```text
task class
model
model version
runtime/profile
hardware/backend context
completed decision
```

It should not become a simplistic global statement such as:

```text
Qwen = 4.5 forever
```

A model may be excellent at one task class and weak at another.

---

# 21. Learning, promotion, and demotion

Mentat learns by comparing prediction with reality.

Example:

```text
Predicted:
  model: Qwen
  cost: $0.020
  latency: 90 sec
  quality: 4.5

Actual:
  cost: $0.017
  latency: 72 sec
  rating: 5
  verification: passed
```

That is positive evidence.

Another candidate might produce:

```text
Predicted:
  cheap host
  total cost: $0.012

Actual:
  model download failed
  second attempt required
  total cost: $0.061
  user waited 7 minutes
```

That is negative host/runtime evidence.

## Promotion

A cheaper model can eventually replace Kimi for a specific task class when enough evidence shows that it meets the required quality and reliability threshold while materially reducing cost or latency.

Example:

```text
Qwen / coding-medium

Rated samples:        150
Verified success:     97%
Average human rating: 4.7
Cost saving vs Kimi:  84%
Calibration:          acceptable

Result:
promote for coding-medium
```

## Demotion

Promotion is reversible.

If a model version, host class, runtime, provider condition, or workload begins producing worse outcomes, Mentat should reduce its preference or remove it from eligibility until revalidated.

Every promotion and demotion should have an audit trail.

---

# Broker self-learning and efficiency loop

Mentat should become more efficient by improving **predictions and routing evidence**, not by letting an unconstrained learner rewrite safety rules.

```text
                    NEW TASK
                       |
                       v
              TaskRequirements
                       |
                       v
              Candidate Plans
                       |
                       v
        predict quality/success/cost/time
                       |
                       v
           hard policy + route choice
                       |
                       v
                    execute
                       |
                       v
             verify + reconcile
                       |
                       v
          compare prediction vs reality
                       |
                       v
              update evidence models
                       |
                       +----------> future task
```

## Learn separate predictors

Do not hide everything in one opaque broker score.

Maintain distinct estimators for:

```text
quality
probability of successful completion
cold-start latency
warm latency
total latency
GPU cost
storage cost
bandwidth cost
retry/failure cost
host reliability
reuse value
verification strength
```

Then combine them only after hard eligibility constraints pass.

## Learn by task and exact configuration

Evidence should be conditioned on relevant context:

```text
task class
programming language / workload family
risk tier
repository/context size
tool requirements
model + exact version
quantization/profile
runtime + version
container/image/bootstrap identity
GPU / GPU count
host
backend
market conditions
```

Do not treat two materially different model/runtime profiles as the same evidence bucket.

## Recency and drift

Models, hosts, runtimes, and marketplaces change.

Mentat should:

- weight recent comparable evidence more heavily;
- reduce confidence after model/runtime/provider changes;
- detect sustained prediction error;
- trigger re-benchmark/revalidation when drift crosses a threshold;
- demote candidates when recent verified performance no longer supports their old status.

## Calibration

A prediction system must learn how wrong it is.

Track:

```text
success-probability calibration
quality prediction error
cost interval coverage
latency interval coverage
host reliability calibration
```

If jobs predicted at 90% success only succeed 65% of the time, the predictor is not trustworthy even if its ranking looks plausible.

## External data is a prior, not a reward

Vast marketplace metrics, trends, benchmark records, and machine reports can improve bootstrap estimates and exploration choices.

They should enter the evidence store with a lower-trust source class such as:

```text
provider market prior
provider benchmark prior
provider machine-risk prior
```

They do not count as verified task success and do not directly promote a model.

Mentat's own verified executions, deterministic checks, and authenticated human ratings remain stronger evidence for real routing quality.

## Contextual-bandit-style exploration

Mentat's routing problem resembles a contextual bandit:

```text
context:
  task/risk/context/tools/budget/market

actions:
  eligible model + runtime + hardware + backend plans

reward evidence:
  verified quality
  successful completion
  real total cost
  latency
  failure/retry penalty
```

Use this style of exploration only **inside the already-safe eligible set**.

Hard security, approval, capability, context, quality-floor, and budget constraints stay outside the learner.

## Champion / challenger

New routing policies should begin in shadow mode.

```text
                    REQUEST
                       |
              +--------+--------+
              |                 |
         Champion vN       Challenger vN+1
              |                 |
       actual decision      shadow decision
              |                 |
              +--------+--------+
                       |
                    compare
```

The challenger may be promoted only after replay/shadow evidence shows improvement without violating safety/quality floors.

## Offline replay

Persist enough decision context to replay historical tasks through a new broker policy without spending money.

Replay should compare:

```text
old winner
new hypothetical winner
hard-eligibility differences
predicted cost difference
predicted latency difference
quality/risk difference
confidence/calibration effects
```

## Exploration budget

Exploration should have its own bounded budget separate from ordinary production spending.

```text
production budget
exploration budget
```

When exploration budget is exhausted, production continues with trusted routes rather than silently funding more experiments.

## Cost of failure and routing regret

The learner should measure the total cost of a failed cheap attempt followed by a stronger fallback.

Example:

```text
cheap attempt:  $0.04
fallback:       $0.31
total:          $0.35

Kimi first:     $0.31

cost regret:    $0.04
plus latency regret
```

This prevents Mentat from calling a route "cheap" merely because the first attempt had a low hourly rate.

## Learning boundary

Mentat may automatically learn:

```text
quality estimates
cost estimates
latency estimates
host reputation
market priors
warm timeout
exploration preference
model/task specialization
```

Mentat may **not** learn around:

```text
credential isolation
user approval
maximum spend
provider allowlist
sandbox rules
hard capability/context requirements
minimum quality/risk policy
```

That separation is fundamental.

---

# 22. Safe exploration

A broker cannot learn alternatives if it never tries them.

But exploration must be controlled.

Good exploration candidates include:

```text
low-risk tasks
easy-to-verify tasks
repeatable benchmarks
opt-in workloads
jobs with strong rollback paths
```

Bad exploration candidates include:

```text
critical authentication changes
irreversible production operations
credential handling
high-blast-radius infrastructure changes
```

External Vast benchmark/market data may help choose which alternatives are worth exploring, but it never removes the need for Mentat's own verification.

Mentat should never sacrifice safety merely to collect cheaper-model data.

---

# 23. Fallback

Fallback is not permission to ignore the original task requirements.

If the selected endpoint fails, the next candidate must independently satisfy the original:

```text
task class
capabilities
context requirement
risk requirement
quality tier
spending policy
remaining approval/budget
```

A high-risk repository-scale task must not silently fall back to a tiny cheap model solely because the preferred endpoint became unavailable.

Fallback should be a fresh routing decision using updated evidence from the failure.

Example:

```text
primary host failed
  -> mark host evidence
  -> update available candidates
  -> re-run hard eligibility
  -> re-check remaining approval/budget
  -> choose next eligible plan
```

Fallback must not silently start a second paid cluster outside the user's approved spending boundary.

---

# 24. Watchdogs and failure recovery

Paid compute must fail safely when Mentat, Windows, the network, the SDK, or Vast behaves unexpectedly.

The system must account for failures such as:

```text
Windows restart
user logoff
broker crash
Gateway crash
network loss
ambiguous create response
Vast API timeout
HTTP 429 / rate-limit pressure
provider permission failure
SDK/helper hidden retry
provider malformed error shape
provider status unknown/offline/exited/frozen/rebooting
worker startup failure
model-server crash
stream interruption
billing mismatch
disk full
SQLite corruption
context overflow
runaway tool loop
```

## Local lifecycle reconciliation

The broker should use idempotent or explicitly reconciled lifecycle operations, write local state atomically, and fail closed on duplicate or orphaned remote resources.

## Circuit breakers

Repeated provider failures should not turn into an expensive failure storm.

Examples:

```text
repeated create/provision failures
  -> open provider/operation circuit
  -> stop new paid acquisition
  -> require cooldown/reconciliation

host repeatedly fails startup
  -> temporarily suppress host

model/profile verification failure spikes
  -> demote profile and require revalidation

rate-limit storm
  -> throttle/coalesce reads and extend polling intervals
```

## Worker watchdog target

A future direct Mentat Worker should have an independent bounded lease.

Example:

```text
Lease expires:          02:30:00
Last broker heartbeat:  02:19:42
Active authorized job:  none
```

If the lease expires without an authorized job or renewed controller heartbeat, the worker should shut itself down according to the safest supported Vast lifecycle action.

This creates two independent protections:

```text
Central broker
  -> shuts down unused compute

Worker watchdog
  -> protects against broker/PC disappearance
```

The objective is simple: a crashed PC should not leave expensive GPU compute running unattended all night.

---

# Example decisions

## Example A — simple coding change

User:

```text
Change the checkout button to green.
```

Mentat determines:

```text
Task class: coding-simple
Scope: small
Risk: low
Verification: easy
Context: small
```

Possible candidates:

```text
Candidate A
Qwen + already-warm RTX 5090 worker
Estimated incremental cost: $0.003
Measured quality: sufficient

Candidate B
Kimi
Estimated incremental cost: $0.16
Measured quality: higher, but unnecessary for this task
```

Decision:

```text
Use Qwen on existing approved compute.
```

Tests pass. The user rates the result highly. The ledger gains another successful Qwen coding sample.

## Example B — repository architecture and lifecycle safety

User:

```text
Review the entire compute broker and redesign the lifecycle so failures cannot accidentally keep paid instances alive.
```

Mentat determines:

```text
Task class: repository architecture
Scope: large
Risk: high
Tools: required
Context: large
Verification: complex
```

Evidence shows Kimi has a meaningful quality advantage for this class.

Decision UI:

```text
Selected: Kimi K2.7 Code
Reason: measured quality advantage outweighs the estimated additional cost
Expected cost: $0.28
Maximum authorized cost: $0.50

Approve?
```

This is exactly the kind of task where premium compute is justified.

## Example C — cheap host versus reliable host

```text
Host A:
  $0.27/hr
  low local sample count
  recent startup failures

Host B:
  $0.31/hr
  strong local completion history
  stable startup
```

If Host B's expected **cost per verified successful task** is lower after failure/retry penalties, the broker should choose Host B even though its hourly rate is higher.

---

# Economic strategy

Mentat should not follow a naive escalation ladder on every request, but its predictions should reflect an economic hierarchy like this:

```text
                         TASK
                           |
                    task requirements
                           |
              +------------+------------+
              |                         |
          cheap tier                 strong tier
       smaller model(s)            larger model(s)
        5090-class etc.          H100/H200-class etc.
              |                         |
              +------------+------------+
                           |
                    Kimi premium tier
                 when evidence justifies it
```

The goal is not to force every request through each tier in sequence. The goal is to predict the correct tier before execution and learn from mistakes.

A trivial task should not automatically wake the most expensive model in the system.

The broker should optimize **successful-task economics**, not hourly price vanity metrics.

---

# Current implementation versus target design

This README intentionally describes both the **current validated Mentat 1.0 foundation** and the **target broker architecture**. They must not be confused.

## Current implemented foundation

Mentat already contains substantial pieces of the design, including:

- Windows-native `Mentat.exe` shell
- local OpenClaw Gateway, tools, memory, repositories, and approvals
- deterministic task-classification foundation
- versioned model registry and validation
- live Vast offer discovery and hardware filtering
- guarded Vast Serverless endpoint lifecycle
- explicit local approval before new paid compute
- cost ceilings and session caps
- reusable approved endpoint sessions
- zero-floor cooling behavior
- lifecycle reconciliation and fail-closed handling
- SQLite decision/runtime history
- separate runtime telemetry and human quality ratings
- fake Vast control plane for no-spend testing
- fake OpenAI-compatible inference service
- cross-platform no-spend broker acceptance harness
- Windows and Ubuntu CI coverage for the previously completed no-spend Broker milestone

## Target broker capabilities still being completed or validated

The complete design also calls for work such as:

- repository- and attachment-aware task estimation
- explicit blast-radius and verification-availability classification
- versioned experimental/approved/retired model lifecycle
- richer candidate scoring with uncertainty and conservative bounds
- prediction calibration and drift detection
- real cold-start prediction
- component-level total-cost prediction
- actual Vast charge reconciliation
- stable compute-backend abstraction
- provider error/state normalization
- provider request governor, caching, and adaptive polling
- least-privilege provider credential roles
- host-specific reputation and bad-host suppression
- provider market metrics/trends as routing priors
- provider benchmark/report data as lower-tier evidence
- canonical benchmark corpus and grading harness
- quality prediction with confidence bounds
- safe exploration
- champion/challenger shadow routing
- offline decision replay
- promotion and demotion policy
- routing-regret reporting
- Kimi-only baseline cost comparison
- low-cost live canary
- Kimi canary
- clean Windows target-machine validation
- long-running soak and adversarial failure testing
- signed reproducible release pipeline

The target architecture also includes a **direct Vast instance backend**, automatic CUDA worker provisioning, worker leases/watchdogs, and keep/freeze/stop/destroy optimization. Those capabilities are planned/experimental expansion and are not part of the frozen Mentat 1.0 release claim unless the owner explicitly changes scope.

A feature should not be described as production-ready merely because it appears in the design. Live-compute claims require executed integration evidence.

---

# Core design rule

The broker should **not** optimize for:

```text
CHEAPEST GPU
```

It should optimize for:

```text
BEST VERIFIED RESULT
FOR THE LOWEST TOTAL PRACTICAL COST
WHILE SATISFYING REQUIRED
QUALITY, CONTEXT, CAPABILITY,
RELIABILITY, LATENCY, RISK,
SECURITY, AND SPENDING LIMITS
```

Optimization happens only inside the safe eligible region.

That is the central Mentat design principle.

---

<!-- MENTAT_AI_CONSTRUCTION_CONTRACT_START -->
# AI construction contract — how to turn the Mentat design into code

This section is the implementation contract for any human or coding AI changing Mentat. The architecture above describes **what Mentat must become**. The rules below describe **how that design is permitted to become production code without drifting away from the mission**.

A change that appears to work but violates this contract is a regression.

## 1. Required reading order before changing Mentat

Before substantial implementation work, read and reconcile these sources in this order:

1. `README.md` — product vision, architecture, roadmap, mission checklist, provider contract, and this construction contract.
2. `docs/mentat/production-contract.md` — canonical production invariants and release gates.
3. `docs/mentat/work-items.md` — authoritative MNT work-item backlog and execution order.
4. `docs/mentat/execution-ledger.md` — permanent evidence, completed work, blockers, and handoffs.
5. `docs/mentat/current-state.yaml` — concise machine-readable current resume state.
6. The implementation and tests for the subsystem being changed.
7. Current GitHub PR/branch/CI reality.
8. For Vast behavior, fetch `https://docs.vast.ai/llms.txt` first and discover the current relevant provider pages.

Do not begin by editing code from a vague prompt. First identify the exact product requirement and the exact MNT work item being advanced.

When documents and GitHub reality conflict, **stop, determine which state is stale, and reconcile the handoff before coding**. Do not silently pick the interpretation that makes implementation easiest.

## 2. Required plan before substantial coding

Before a substantial change, record a short implementation plan containing:

```text
Work item:
User/product requirement:
Current behavior:
Target behavior:
Files expected to change:
Interfaces/data contracts affected:
Security or spending invariants affected:
Provider assumptions affected:
Tests that will prove completion:
Failure cases to test:
Things explicitly out of scope:
Owner-only or live-service actions required:
```

This plan is how scope drift, accidental redesign, and false completion are prevented.

## 3. Non-negotiable implementation invariants

These are laws of the system, not preferences.

```text
INV-001  A language model never receives a credential that can authorize paid compute.
INV-002  A language model never creates, warms, resizes, approves, retries, or extends paid compute directly.
INV-003  Every increase in paid-compute authority must fit inside a valid authenticated approval lease.
INV-004  Fallback may not silently exceed the original quality, risk, capability, context, or spending policy.
INV-005  Unknown or ambiguous infrastructure state fails closed and is reconciled before more spending.
INV-006  A failed, malformed, interrupted, or unverified execution cannot become positive quality evidence.
INV-007  Runtime telemetry and human quality evidence remain separate data sources.
INV-008  Estimated cost is never represented as actual billed cost.
INV-009  A cheaper candidate cannot override a hard quality, capability, context, reliability, or risk floor.
INV-010  Model/version/profile evidence is version-specific; a new version does not inherit trust blindly.
INV-011  Tool execution remains inside the intended local security boundary; broker credentials stay outside it.
INV-012  Paid resource creation is never blindly retried after an ambiguous outcome.
INV-013  Local lifecycle state is durable/atomic enough to support crash reconciliation.
INV-014  Rejection or expired approval must not start new paid compute.
INV-015  One task's approval cannot be silently converted into unlimited time, GPUs, models, retries, or dollars.
INV-016  Verification failure counts as task failure for learning and routing evidence.
INV-017  Current implementation, tested behavior, live-validated behavior, and target design remain distinguishable.
INV-018  Safety controls may not be weakened merely to make tests pass or simplify implementation.
INV-019  Provider SDK/helper automatic retries must never cause a hidden repeated non-idempotent paid mutation.
INV-020  Production provider credentials are explicit, broker-owned, least-privilege where validated, and never discovered implicitly from ambient key files.
INV-021  Raw provider response/error/status structures are normalized at the adapter boundary before entering broker logic.
INV-022  Provider benchmarks, market metrics, trends, and machine reports are priors; they are not verified task-success evidence.
INV-023  Provider rate-limit handling and lifecycle polling are centrally governed, bounded, and observable.
INV-024  Provider permission, billing, lifecycle, and retry assumptions remain untrusted until documented and live-validated at the appropriate gate.
INV-025  Provider infrastructure state and Mentat execution state remain separate concepts.
```

If an implementation seems to require breaking an invariant, the implementation is wrong until the product owner explicitly changes the invariant and production contract.

## 4. Prohibited shortcuts

Never:

- give OpenClaw, a model, renderer, tool subprocess, or workspace a Vast spending credential;
- allow model-generated shell commands to control Vast billing or lifecycle directly;
- bypass authenticated local approval for a new paid session;
- silently start a second paid model/backend as fallback;
- rely on an SDK's automatic retry for an ambiguous non-idempotent paid create/start/warm mutation;
- assume an unrestricted Vast `misc` credential is read-only;
- rely on implicit Vast SDK key-file discovery as the production credential boundary;
- parse pretty CLI/SDK output when a machine-readable provider response is available;
- expose `curl`/verbose SDK diagnostics containing sensitive request context in normal production logs;
- weaken, delete, skip, or rewrite a test merely because the implementation fails it;
- hard-code invented Vast behavior when live behavior is unknown;
- treat a public/provider benchmark as equivalent to Mentat's verified local evidence;
- treat bootstrap priors as measured model quality;
- treat an HTTP `200` or provider `running` status as proof that a task/worker is valid;
- mark a feature complete because code exists without executed evidence;
- make unrelated architectural changes while implementing one work item;
- hide uncertainty behind fake precision;
- assume a host/GPU/runtime is reliable without evidence;
- use real credentials or paid compute in ordinary CI;
- commit secrets, private tokens, approval credentials, endpoint credentials, webhook signing secrets, or sensitive local state.

## 5. Work-item discipline

Substantial work should map to a stable `MNT-xxx` work item from `docs/mentat/work-items.md`.

Prefer one coherent work item per pull request. A PR titled `Improve broker` is too vague. A PR implementing `MNT-404 — Total-cost and latency predictors` has a testable boundary.

Do not automatically start the next work item because the relevant files are already open.

When a work item is split, state:

```text
MNT work item:
Slice implemented:
What remains:
Acceptance criteria covered:
Acceptance criteria still open:
```

## 6. Status vocabulary — never confuse the dream with reality

Use these states consistently:

```text
PLANNED         described but not implemented
IMPLEMENTED     code exists
TESTED          automated or controlled integration evidence exists
LIVE-VALIDATED  exercised against the real external service/hardware
EXPERIMENTAL    implemented but not trusted for normal routing
BLOCKED         cannot advance without an explicit dependency/owner action
DEFERRED        intentionally outside the current release
RETIRED         no longer eligible for normal use
```

Do not describe `PLANNED` functionality as working. Do not describe simulator behavior as `LIVE-VALIDATED`. Unknown is a valid state; never invent a measurement to make a predictor look complete.

## 7. Define data contracts before wiring large subsystems together

Core concepts must have explicit, versionable contracts rather than ad-hoc dictionaries.

### TaskRequirements

```text
TaskRequirements
  task_class
  complexity
  repository_scope
  attachment_scope
  required_capabilities
  required_context
  tools_required
  verification_available
  reversibility
  blast_radius
  risk_tier
  latency_requirement
  quality_floor
  budget_limit
  confidence
```

### ExecutionCandidate

```text
ExecutionCandidate
  model_profile
  model_version
  runtime_profile
  compute_backend
  hardware_profile
  host_or_endpoint_identity
  provider_market_snapshot_id
  reuse_state
  expected_quality
  quality_confidence
  expected_success_probability
  expected_startup_seconds
  expected_inference_seconds
  expected_total_latency
  expected_total_cost
  cost_confidence
  evidence_count
  uncertainty
  policy_eligibility
  rejection_reasons
```

### ApprovalLease

```text
ApprovalLease
  approval_id
  model/profile scope
  backend scope
  maximum GPU/resource count
  maximum hourly rate
  maximum total spend
  maximum retry/fallback spend
  maximum duration
  issued_at
  expires_at
  authenticated local approver
```

### ProviderState

```text
ProviderState
  provider
  resource_identity
  provider_actual_status
  provider_intended_status
  provider_allocation_state
  provider_status_message
  observed_at
  normalized_state
```

### ProviderError

```text
ProviderError
  provider
  operation
  http_status
  provider_code
  message
  retryable_read
  rate_limited
  auth_or_permission_failure
  ambiguous_mutation
```

### ProviderMarketSnapshot

```text
ProviderMarketSnapshot
  provider
  observed_at
  freshness_deadline
  source_capabilities
  normalized_offer/market fields
  adapter_version
  evidence_tier
```

### ExecutionResult

```text
ExecutionResult
  task/decision identity
  selected candidate identity
  actual startup/provision/load timings
  actual inference timings
  observed throughput
  estimated cost components
  actual reconciled billing components when available
  prediction error
  success/failure classification
  verification result + strength
  retry/fallback history
  human rating when supplied
```

Do not let two subsystems invent incompatible meanings for `candidate`, `success`, `cost`, `quality`, `host`, `provider state`, or `approval`.

## 8. Compute backends must implement a common boundary

The target conceptual interface is:

```text
ComputeBackend
  capabilities()
  discover(requirements)
  estimate(candidate)
  acquire(approved_candidate, approval_lease)
  status(resource)
  prepare(resource, model_profile)
  health(resource)
  execute(resource, request)
  cool(resource)
  freeze(resource)     # when supported
  stop(resource)       # when supported
  destroy(resource)
  reconcile(saved_state)
  billing(resource)    # when available
```

`VastServerlessBackend` and a future `VastInstanceBackend` should implement the same broker-facing concepts even when their internal lifecycle operations differ. Avoid scattering backend-specific conditionals throughout task classification, model quality logic, and policy code.

Direct-instance SDK integration, when authorized, must remain behind this boundary. The Vast Python SDK is an infrastructure adapter dependency, not a new authority boundary. Its automatic credential discovery and retry convenience must not replace Mentat's broker-owned credential and reconciliation controls.

## 9. Deterministic broker decision order

"Best broker possible" must be explainable and testable.

```text
1. Build TaskRequirements from observable task/context/tool/risk information.
2. Generate registered model candidates.
3. Reject candidates that fail hard capability or context requirements.
4. Obtain a fresh-enough normalized provider/market snapshot.
5. Generate technically valid hardware/runtime/backend plans.
6. Reject plans violating security, risk, reliability, quality, or budget floors.
7. Predict quality and successful-completion probability with uncertainty.
8. Predict cold/warm latency and total cost with uncertainty.
9. Apply host/runtime/provider failure, stale-market, and cold-start penalties.
10. Apply reuse advantages only when an existing session is still authorized and compatible.
11. Score remaining eligible plans according to the user's routing mode.
12. Explain the winner and meaningful rejected alternatives.
13. Revalidate price/resource facts required for spending.
14. Require authenticated approval before new paid authority is exercised.
15. Atomically reserve authorized exposure.
16. Execute exactly one controlled paid mutation when needed.
17. Reconcile provider state until the worker is truly ready or safely failed.
18. Execute inference.
19. Verify the result.
20. Record telemetry and evidence.
21. Reconcile billing and lifecycle state.
22. Feed verified evidence and prediction error back into future decisions.
```

Hard eligibility rules run **before** economic optimization. A cheap plan that cannot safely do the job is not a candidate.

## 10. User routing modes change preferences, not safety

Target modes are:

```text
Best
Balanced
Economy
Manual
```

They may change how eligible candidates are ranked, but they must not bypass hard constraints. `Economy` may accept higher latency or prefer a proven cheaper model; it may not ignore context or quality floors. `Manual` may select among eligible options but must warn or refuse when an option is technically impossible or violates a non-overridable boundary.

## 11. Predictions require uncertainty and evidence counts

Prefer:

```text
Expected total cost: $0.018-$0.026
Confidence: 81%
Comparable samples: 37
Evidence age: recent
```

not fake precision such as `$0.021437` when the data cannot support it.

Quality, cost, latency, host reliability, and success predictions should say how many comparable samples support them, how variable/recent those samples are, whether the model/runtime/version/provider conditions changed, and whether the value is measured evidence or a bootstrap prior.

For hard policy, use conservative bounds where appropriate:

```text
quality lower bound >= required quality floor
cost upper bound <= maximum authorized spend
latency upper bound <= hard latency limit, when one exists
failure-risk upper bound <= accepted risk threshold
```

## 12. Evidence hierarchy

Mentat should know what kind of evidence taught it something:

```text
Tier 0  bootstrap assumption / explicit prior
Tier 1  provider/public benchmark or synthetic deterministic benchmark
Tier 2  real task with automatic verification
Tier 3  real task with authenticated human quality rating
Tier 4  repeated, recent, high-confidence production evidence
```

Provider market metrics, trends, benchmarks, and machine reports carry their source labels and do not masquerade as task-quality evidence.

Promotion policies should require evidence appropriate to task risk. No external benchmark silently overwrites stronger local production evidence.

## 13. Golden scenarios are executable product specifications

At minimum preserve these scenarios.

### A — trivial coding request

```text
Task: change button text
Risk: low
Context: small
Verification: strong
Available: approved warm Qwen/5090 and cold expensive Kimi
Expected: choose Qwen/5090
Forbidden: waking Kimi solely because it has higher absolute quality
```

### B — repository-scale high-risk architecture

```text
Task: inspect entire broker and repair lifecycle races
Risk: high
Context: large
Verification: complex
Evidence: Kimi has meaningful measured quality advantage
Expected: propose Kimi and require approval for new paid compute
Forbidden: silently downgrade to an unproven cheap model
```

### C — cheap but historically bad host

```text
Host A: cheaper, poor Mentat historical completion rate
Host B: slightly more expensive, strong history and still within budget
Expected: reliability/failure penalty can make Host B win
Forbidden: selecting Host A from hourly price alone
```

### D — approval ceiling exceeded

```text
Approved total spend: $0.50
New required upper-bound spend: $0.67
Expected: stop and request new approval
Forbidden: extending the original approval silently
```

### E — ambiguous create response

```text
Create request: network timeout after request may have reached Vast
Expected: reconcile exact remote state before another create
Forbidden: SDK/helper blind retry that can create duplicate paid resources
```

### F — malformed HTTP-200 response

```text
Upstream HTTP status: 200
Body/protocol: malformed or incomplete
Expected: execution failure and no positive learning sample
Forbidden: treating status code alone as task success
```

### G — fallback

```text
Primary unavailable
Original task: high-risk, tool-heavy, large context
Expected: fallback independently satisfies original requirements and remaining approved spend
Forbidden: tiny model or second paid cluster started silently
```

### H — direct-instance readiness failure

```text
Instance status: loading -> unknown/offline/exited, or readiness timeout
Expected: stop waiting, reconcile/destroy according to policy, record failure, penalize host/runtime where justified
Forbidden: infinite polling while storage charges continue
```

### I — SDK automatic retry on paid mutation

```text
Operation: non-idempotent paid create
SDK default: automatic retry enabled
Expected: Mentat disables/bypasses hidden mutation retry and owns reconciliation
Forbidden: letting provider convenience repeat the paid create silently
```

### J — frozen is not stopped

```text
Provider actual_status: frozen
Documented economics: GPU charges still apply
Expected: model as paid GPU state
Forbidden: treating frozen as zero-compute-cost sleep
```

### K — broad misc permission

```text
Credential: unrestricted Vast misc category
Need: offer discovery only
Expected: reject as overly broad for a read-only role or validate endpoint-level restriction
Forbidden: calling misc a read-only discovery permission
```

### L — provider rate-limit storm

```text
Repeated reads receive HTTP 429
Expected: request governor throttles/coalesces/backoffs and records pressure
Forbidden: every subsystem independently retries/polls harder
```

Golden scenarios should become automated tests whenever possible.

## 14. Requirement-to-code-to-test traceability

Reference MNT IDs in tests and implementation where practical:

```python
def test_mnt_404_cold_start_is_included_in_total_cost():
    ...


def test_mnt_405_high_risk_task_respects_quality_floor():
    ...
```

Searching for an MNT ID should make it possible to find the specification, implementation, tests, evidence, and remaining work.

## 15. Acceptance matrix

For each substantial requirement preserve the chain:

```text
Requirement
  -> implementation
  -> unit/adversarial tests
  -> integration test
  -> live validation when external behavior matters
  -> retained evidence
```

Simulator evidence can close a simulator/test gate; it cannot close a live-service gate.

Provider documentation can justify a design assumption; it cannot close a live-provider gate.

## 16. Tests must prove failure behavior

Depending on the subsystem, include cases such as:

```text
network timeout
ambiguous create
partial response
malformed JSON/SSE
provider error missing expected fields
HTTP 429 / rate limit
SDK/helper hidden retry
permission denied
stale market snapshot
price changed before acquisition
duplicate/orphan remote resource
provider null/loading/stopped/frozen/exited/rebooting/unknown/offline state
expired approval
budget exhaustion
context overflow
model/runtime startup failure
host failure
billing mismatch / partial charge data
cancellation
Windows/Gateway/Broker restart
SQLite corruption
disk full
concurrent requests
runaway tool loop
bounded readiness timeout
```

A system that works only when every dependency behaves perfectly is not production-ready Mentat.

## 17. Never weaken tests just to make CI green

When a test fails, determine whether implementation is wrong, the test is wrong because the product contract intentionally changed, or an external assumption changed. Do not change assertions merely to match new broken behavior.

A deliberate invariant change must identify the old rule, new rule, reason, risks, and replacement tests.

## 18. Narrow PRs and durable architecture decisions

Each substantial PR should state:

```text
MNT work item:
Problem being solved:
Design chosen:
Alternatives rejected:
Invariants touched:
Provider assumptions touched:
Files/subsystems changed:
Tests executed:
Evidence produced:
Live/owner gates still open:
Explicitly out of scope:
```

Do not perform opportunistic rewrites unrelated to the work item.

Long-lived architecture decisions should be recorded durably with:

```text
Decision
Context
Alternatives considered
Why this choice
Consequences
Security/spending impact
Provider dependency/assumptions
How the decision can be revisited
```

## 19. Stop conditions — do not guess through these boundaries

Stop and report the blocker when:

- live Vast behavior contradicts the documented assumption;
- the exact permission required for a sensitive provider action is unknown;
- SDK retry semantics could repeat a paid mutation and have not been proven safe;
- a real credential is required but unavailable through the approved local boundary;
- paid compute would begin without explicit owner approval;
- billing semantics needed for correctness are unknown;
- authoritative specifications conflict materially;
- a destructive/irreversible migration is required;
- a security invariant appears incompatible with the proposed implementation;
- the only way to pass a test is to weaken a safety guarantee;
- a live result is required to make a factual claim;
- required evidence cannot be produced honestly.

Do not manufacture a plausible answer to cross one of these boundaries.

## 20. Owner-only actions remain owner-only

Coding agents must not pretend to complete owner-only actions such as entering/rotating the real Vast API key, creating production scoped credentials with real account authority, approving paid canaries, inspecting private billing, clean owner-PC validation, code-signing certificate operations, or irreversible repository/security changes reserved for the owner.

Prepare everything possible up to the gate, document the exact owner action, then stop.

## 21. Definition of done

A work item is not `DONE` merely because code was written.

```text
[ ] requirement is unambiguous
[ ] implementation exists
[ ] interfaces/data contracts are explicit
[ ] provider assumptions are documented and current
[ ] unit tests pass
[ ] important adversarial/failure cases pass
[ ] integration path passes
[ ] security/spending invariants remain intact
[ ] no secrets are introduced
[ ] current-vs-target status is documented honestly
[ ] live validation is complete when the requirement depends on live behavior
[ ] provider permission/retry/billing behavior is live-validated when correctness depends on it
[ ] retained evidence exists
[ ] execution ledger is updated
[ ] current-state.yaml is updated when the handoff changed
[ ] remaining limitations are explicit
[ ] relevant CI is green
```

If a condition does not apply, say why. If one remains open, do not silently call the item complete.

## 22. Handoff discipline

At every meaningful stopping point update `docs/mentat/execution-ledger.md` and `docs/mentat/current-state.yaml`.

Record at least:

```text
Date/time:
Main commit:
Branch/PR:
MNT work item:
Last completed item:
Current item:
Files changed:
Tests run and results:
Evidence produced:
Provider docs/live behavior checked:
Known failures:
Owner action required:
External dependency:
Exact next task:
Do not do:
```

Then verify the handoff against GitHub. The next coding agent should be able to continue without reconstructing the project from chat history.

## 23. Implementation objective

When choosing between technically valid implementations, prefer the one that makes Mentat:

```text
more correct
more measurable
more explainable
more recoverable
more testable
more evidence-driven
safer with credentials
safer with money
cheaper per verified successful task
faster when cost/quality are equivalent
more robust to provider changes
less dependent on hidden SDK behavior
easier to evolve without breaking invariants
```

Do not prefer cleverness for its own sake.

The final test for any implementation decision is:

> **Does this change move Mentat closer to obtaining the best verified result for the lowest practical total cost, while preserving the required quality, context, capability, reliability, latency, risk, security, and spending boundaries — and can we prove that with evidence?**

If the answer cannot be demonstrated, the work is not finished.
<!-- MENTAT_AI_CONSTRUCTION_CONTRACT_END -->

---

# Install in a few minutes

First-class installers support:

- Windows 10/11 natively through PowerShell — no WSL required
- macOS
- Linux

Requirements:

- Git
- Node.js 24.15+ recommended, or 22.22.3+ / 25.9+
- Python 3.11+

## Windows — native desktop application

Open PowerShell:

```powershell
git clone https://github.com/clementrichardsnapper422-dot/Mentat.git
cd Mentat
.\install.cmd
```

The Windows installer:

1. installs Mentat's local runtime and command-line tools
2. builds the local Control UI
3. builds a native `Mentat.exe` desktop application
4. installs it per-user
5. creates Desktop and Start Menu shortcuts

`install.cmd` uses a process-only execution-policy bypass. It does not alter the permanent Windows execution policy and does not use WSL, Git Bash, or Cygwin.

Open a new PowerShell window and configure the model provider:

```powershell
mentat setup
```

Then launch **Mentat** from the Desktop or Start Menu. The application starts the local Gateway when necessary and opens the Control UI in its own native window.

Command-line chat remains available:

```powershell
mentat start
mentat chat
```

Windows installer options:

```powershell
.\install.cmd -SkipUI
.\install.cmd -SkipDeps
.\install.cmd -SkipDesktop
.\install.cmd -NoPath
```

`-SkipDesktop` keeps the native command-line installation but skips building and installing `Mentat.exe`.

The locally built Windows installer is unsigned until a code-signing certificate is configured. Windows may display an unknown-publisher notice.

See the [native Windows guide](docs/mentat/windows.md) for paths, DPAPI protection, desktop-app behavior, and troubleshooting.

## macOS and Linux

```bash
git clone https://github.com/clementrichardsnapper422-dot/Mentat.git
cd Mentat
bash install.sh
```

Open a new terminal, then run:

```bash
mentat setup
mentat start
mentat chat
```

Unix installer options:

```bash
bash install.sh --skip-ui
bash install.sh --skip-deps
bash install.sh --no-path
```

## What the installers do

The installers:

1. check Node.js, Python, Git, and the operating system
2. install the pinned pnpm version into the user account when needed
3. install repository dependencies
4. build the local Control UI
5. install one `mentat` command
6. create per-user configuration and state directories
7. run `mentat doctor`

The Windows installer additionally builds and installs the Electron desktop application unless `-SkipDesktop` is supplied.

They do not upload credentials or store secrets in GitHub.

### Local files

macOS and Linux:

```text
~/.local/bin/mentat
~/.config/mentat/
```

Windows runtime:

```text
%LOCALAPPDATA%\Mentat\bin
%LOCALAPPDATA%\Mentat\config
%LOCALAPPDATA%\Mentat\state
```

Windows desktop application:

```text
%LOCALAPPDATA%\Programs\Mentat\Mentat.exe
```

The native Windows setup encrypts the Vast API key with Windows DPAPI. The saved value can only be decrypted by the same Windows user profile on that Windows installation.

## First-time setup

Run the interactive setup wizard:

```text
mentat setup
```

Select a provider directly:

```text
mentat setup vast
mentat setup ollama-cloud
```

### Vast.ai

The **current Serverless setup path** asks for:

- the Vast OpenAI-compatible endpoint ending in `/v1`
- the model ID, defaulting to `moonshotai/Kimi-K2.7-Code`
- a scoped Vast API key
- the Vast Serverless template hash, which may be left blank until endpoint creation

On Windows, the current key is DPAPI-encrypted in `%LOCALAPPDATA%\Mentat\config\config.json`. On macOS and Linux, the local environment file is created with owner-only permissions.

The target credential architecture is stricter than the current one-key setup: Mentat should eventually create/use narrowly scoped broker credentials for discovery, lifecycle, and billing where Vast's live permission model allows that split. A bootstrap-capable owner key should not remain in everyday runtime storage.

As the broker evolves, setup should move toward configuring policy and credentials while allowing the broker to create or select runtime endpoints itself rather than requiring the user to understand infrastructure details.

### Ollama Cloud fallback

Install Ollama and sign in, then select the fallback provider:

```text
ollama signin
mentat setup ollama-cloud
mentat start
```

This launches `kimi-k2.7-code:cloud` through Ollama Cloud. It is separate from the Vast inference route.

## Desktop application behavior

The Windows `Mentat.exe` application:

- opens the local Control UI in a dedicated desktop window
- starts the local Gateway when it is not already running
- leaves an already-running Gateway alone
- stops the Gateway on exit only when the desktop app started it
- permits only the configured local Gateway origin inside the window
- opens outside links in the default browser
- disables Node.js and Electron APIs inside the web interface
- allows only one Mentat desktop instance at a time
- includes menu commands for reload, Gateway restart, logs, zoom, full screen, and developer tools

The desktop app is a secure shell around the same local Mentat Gateway. It is not a hosted website and does not move your tools or data to Electron.

## Everyday command-line use

```text
mentat start                   start the local Gateway in the background
mentat stop                    stop it
mentat restart                 restart it
mentat status                  process and Gateway status
mentat chat                    open the terminal UI
mentat chat "Review my repo"  send one message directly
mentat logs                    follow Gateway logs
mentat doctor                  diagnose setup problems
```

Run in the foreground when debugging:

```text
mentat start --foreground
```

## Configuration

```text
mentat config path
mentat config show
mentat config edit
```

Credentials are redacted from `mentat config show`. The default Gateway port is `18789`.

## Vast endpoint lifecycle

Mentat includes guarded commands for the current Kimi Serverless endpoint path. These are explicit operator actions; the language model does not receive unrestricted infrastructure control.

```text
mentat vast estimate --hourly-price 28 --hours 2
mentat vast create --accept-test-worker-cost
mentat vast status
mentat vast test
mentat vast warm
mentat vast cool
mentat vast destroy --confirm
```

The acknowledgement is required because the initial profile may launch a complete 8×H200 worker cluster for benchmarking. The committed profile allows only one worker cluster and caps marketplace offers at `$32/hour`.

## No-spend diagnostics

Mentat's broker development path includes fake Vast and fake OpenAI-compatible services so important lifecycle and inference behavior can be exercised without renting a real GPU.

The no-spend acceptance path is intentionally separate from live Vast canaries. Passing a no-spend test proves local broker behavior against the simulator; it does not prove real Vast billing, permissions, retry semantics, or GPU behavior.

## Vast documentation references for broker work

Provider behavior should be rechecked from the current documentation index before implementation:

- [Vast documentation index](https://docs.vast.ai/llms.txt)
- [VastAI SDK client](https://docs.vast.ai/sdk/python/reference/vastai)
- [SDK permissions](https://docs.vast.ai/sdk/python/permissions)
- [API permissions mapping](https://docs.vast.ai/api-reference/permissions)
- [SDK rate limits and errors](https://docs.vast.ai/sdk/python/rate-limits)
- [create_instance](https://docs.vast.ai/sdk/python/reference/create-instance)
- [show_instances status semantics](https://docs.vast.ai/sdk/python/reference/show-instances)
- [show charges](https://docs.vast.ai/api-reference/billing/show-charges)
- [search benchmarks](https://docs.vast.ai/api-reference/search/search-benchmarks)
- [GPU metrics](https://docs.vast.ai/api-reference/machines/show-gpu-metrics)
- [GPU trends](https://docs.vast.ai/api-reference/machines/show-gpu-trends)
- [machine reports](https://docs.vast.ai/api-reference/machines/show-reports)
- [notification webhooks](https://docs.vast.ai/api-reference/notifications/create-notification-webhook)

These links document provider capabilities; they are not a substitute for Mentat's retained live validation evidence.

## Update Mentat

```text
mentat update
```

This performs a fast-forward Git pull, installs dependencies, and rebuilds the Control UI. Run `install.cmd` again when desktop application code or packaging changes.

## Uninstall

Remove the command while preserving configuration:

```text
mentat uninstall
```

Remove command-line configuration and state:

```text
mentat uninstall --purge
```

The Windows desktop application is uninstalled separately from **Windows Settings → Apps → Installed apps → Mentat**. The source checkout is deliberately not deleted automatically.

## Troubleshooting

Start here:

```text
mentat doctor
mentat status
mentat logs
```

Reinstall on Windows:

```powershell
.\install.cmd
```

Reinstall on macOS or Linux:

```bash
bash install.sh
```

Detailed documentation:

- [Mentat production contract](docs/mentat/production-contract.md)
- [Mentat execution ledger](docs/mentat/execution-ledger.md)
- [Mentat machine-readable current state](docs/mentat/current-state.yaml)
- [Mentat 1.0 work items](docs/mentat/work-items.md)
- [Native Windows installation and desktop app](docs/mentat/windows.md)
- [Desktop packaging](apps/mentat-desktop/README.md)
- [Architecture](docs/mentat/architecture.md)
- [Model runtime](docs/mentat/model-runtime.md)
- [Vast Kimi endpoint](infrastructure/vast/kimi-k2.7-code/README.md)

## Development from source

The main repository is a pnpm workspace. Plain `npm install` at the repository root is not supported.

```text
corepack enable
pnpm install
pnpm openclaw setup
pnpm gateway:watch
```

Build the runtime and Control UI:

```text
pnpm build
pnpm ui:build
```

Build only the Windows desktop installer:

```powershell
cd apps\mentat-desktop
npm install
npm run dist
```

The generated installer is placed in `apps\mentat-desktop\dist`.

## Security

Mentat can execute local tools and access real repositories and accounts. Treat inbound messages as untrusted input, keep approval gates enabled for destructive or paid actions, and do not expose the Gateway publicly without following OpenClaw's security guidance.

Never commit:

- Vast API keys
- endpoint credentials
- scoped lifecycle/discovery/billing credentials
- webhook signing secrets
- Hugging Face tokens
- Ollama credentials
- `MENTAT_COMPUTE_TOKEN`

The language model itself must never receive the credential that authorizes paid Vast infrastructure.

## OpenClaw foundation

Mentat is built from the open-source [OpenClaw](https://github.com/openclaw/openclaw) project and retains its local Gateway, tools, channels, memory, apps, plugin system, and security model.

Useful upstream documentation:

- [Getting started](https://docs.openclaw.ai/start/getting-started)
- [Gateway](https://docs.openclaw.ai/gateway)
- [Models](https://docs.openclaw.ai/concepts/models)
- [Tools](https://docs.openclaw.ai/tools)
- [Security](https://docs.openclaw.ai/gateway/security)
- [Channels](https://docs.openclaw.ai/channels)

## License

MIT. See [LICENSE](LICENSE) and [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
