# Mentat mission execution ledger

This is the permanent handoff and evidence record for completing Mentat. Update it whenever work starts, stops, passes, fails, changes scope, or reaches an owner-only gate. A fresh coding agent should be able to resume from this file plus `docs/mentat/current-state.yaml` without relying on old chat history.

## Mission

Ship a signed Windows-native Mentat release that safely combines local OpenClaw tools and memory with a deterministic, evidence-driven model-and-compute broker that selects approved remote intelligence, explains cost and quality before spending, learns from verified outcomes, and fails safely.

The economic objective is not cheapest GPU-hour. It is the **best verified result for the lowest practical total cost** while satisfying quality, context, capability, reliability, latency, risk, security, and spending limits.

## Definition of done

Mentat 1.0 is complete only when every in-scope release gate in `docs/mentat/production-contract.md` passes and the release candidate is installed from a signed artifact on a clean Windows machine.

Target direct-instance and advanced broker-hardening work documented in Program 7 of `docs/mentat/work-items.md` remains deferred from the frozen Mentat 1.0 release scope unless the owner explicitly changes scope.

## Current repository state

Last reconciled: **2026-07-26 during Shot 1 exact-head validation**, against `main` commit `c374e529bb03d16606c2ae03b6b05b04c748e69a`.

The ledger deliberately does **not** claim that hash is forever the current `main` tip. A document cannot safely embed the hash of the commit that will contain its own update. **Always fetch the current GitHub `main` tip and PR state at resume time.**

- Repository: `clementrichardsnapper422-dot/Mentat`
- Default branch: `main`
- Current visibility at reconciliation: **public**
- Repository type: public fork larger than 1 GB
- GitHub Issues: disabled; `docs/mentat/work-items.md` is the authoritative backlog until a replacement tracker is enabled
- Production contract: present and canonical
- Mentat 1.0 scope: frozen
- Machine-readable handoff: `docs/mentat/current-state.yaml`
- PR #11: merged; no-spend Broker milestone established
- PR #13: merged; complete target broker architecture documented
- PR #14: merged; construction contract, roadmap, checklist, and resume system established
- PR #15: merged as `46f8f71b99f7bfecb0f6d16dc6fc33483ca92941`; provider/learning/spending design hardening complete
- PR #12: **merged** as `c374e529bb03d16606c2ae03b6b05b04c748e69a`; installed and desktop no-spend diagnostics are on `main`
- Last verified PR #12 focused CI: Desktop PASS; Broker PASS; Runtime PASS; Workflow Sanity PASS; CodeQL PASS; no paid compute used
- PR #17: **open and ready for review** on `agent/post-pr12-gate1-handoff`; Shot 0 repository-truth reconciliation, exact head `94d8925eb9d8f64bf255b965827f15c07b78f30a`
- PR #18: **open and stacked on PR #17** on `agent/mnt-202-complete-runtime-package`; Shot 1 complete-runtime packaging, exact code head `748d5a069873961aa82a632d9556c2b06f14b45b`
- PR #9: still open, 16 commits ahead and 29 commits behind `main`; diverged and not the current execution slice; requires separate triage before reuse
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

| Gate                                   | Status                | Evidence required to close                                                                                                                                                   |
| -------------------------------------- | --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 0. Private repository and supply chain | BLOCKED: OWNER        | standalone private repository, protected `main`, secret/history audit, required checks, reproducible signed release path                                                     |
| 1. No-spend Windows integration        | IN PROGRESS           | PR #12 repaired/accepted, clean target-PC install, Docker tool isolation, credential-boundary proof, restart/shutdown behavior                                               |
| 2. Low-cost Vast canary                | NOT STARTED           | current API/permission assumptions validated, reject/no-spend, one intended create, real inference, reuse/cooling, recovery, actual billing reconciliation                   |
| 3. Kimi canary                         | NOT STARTED           | exact Kimi profile, tools, long context, stream/cancellation, caps, recovery, actual latency/throughput/billing                                                              |
| 4. Broker intelligence/learning        | IN PROGRESS BY DESIGN | benchmark corpus, calibrated quality/success/cost/latency predictions, safe exploration, promotion/demotion, regret/savings, explainability, spending/concurrency safeguards |
| 5. Soak/adversarial validation         | NOT STARTED           | race/failure injection, security attacks, 100-session/24-hour/multi-day campaign, no leaks or stale paid resources                                                           |
| 6. Signed Mentat 1.0 release           | NOT STARTED           | all in-scope P0 gates closed, signed/checksummed/provenanced artifact installed on clean Windows                                                                             |

## Owner-only gates

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
DO NOT bypass the remaining Gate 1 evidence work to begin a new broker implementation feature.
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
- [x] README contains target architecture, roadmap, construction invariants, provider contract, and resume protocol.
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
- [x] Repair/revalidate PR #12 Broker/Runtime failures.
- [x] `mentat test no-spend` accepted after the source-tree `install.ps1` path in CI.
- [x] Desktop diagnostics accepted in focused CI.
- [x] Complete clean-install artifact includes the local runtime, Broker, required scripts, and `mentat` wrapper without a source checkout or checkout-path embedding; exact-head clean-runner proof is retained on PR #18.
- [ ] Actual OpenClaw tool execution proven inside Docker.
- [ ] Gateway/tools/renderer/sandbox proven unable to read broker/admin/Vast credentials.
- [ ] Clean target-PC Windows installation.
- [ ] Restart/logoff/shutdown recovery proof.

### D. In-scope Mentat 1.0 broker intelligence, safety, and learning

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
- [ ] Calibration, recency, drift, and evidence-age handling required by the 1.0 predictors.
- [ ] Hard eligibility before multi-objective economic scoring.
- [ ] Safe exploration only inside the eligible low-risk/verifiable set.
- [ ] Promotion/demotion, basic decision replay, routing regret, and Kimi-only baseline.
- [ ] Host/GPU/provider-market priors kept separate from Mentat local measured evidence.
- [ ] Full candidate/rejection/policy explanation.
- [ ] **MNT-411 Spend Governor and atomic budget ledger**: one narrow spend authority, atomic worst-case budget reservation, layered configured limits, and global paid-compute kill switch.
- [ ] **MNT-412 paid execution state machine and concurrency safety**: legal atomic transitions, race handling, durable reconciliation, and prevention of duplicate/orphaned paid resources.

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
- [ ] Race/concurrency/property tests for approvals, atomic budget reservation, state transitions, lifecycle, fallback, and provider ambiguity.
- [ ] 100-session, 24-hour, and multi-day soak.
- [ ] Independent security review or explicit accepted-risk record.
- [ ] Operator/emergency/credential-rotation/backup/recovery/provider-outage runbooks.
- [ ] Signed installer, checksums, provenance, SBOM, clean install/upgrade/repair/uninstall.

### G. Deferred target broker expansion

These do not become Mentat 1.0 blockers without explicit scope change.

- [ ] Full provider adapter with read/spend/billing separation, request governor, and validated least-privilege role split.
- [ ] Vast direct-instance lifecycle backend.
- [ ] Pinned Mentat Worker provisioning/readiness attestation and watchdog.
- [ ] Direct-host/market intelligence and bad-host suppression.
- [ ] Keep/freeze/stop/destroy economics for direct workers.
- [ ] Advanced broker policy champion/challenger shadowing and large-scale offline comparison.
- [ ] Adaptive spend forecasting/session economics that extends—but never weakens—the MNT-411 hard budget ledger.
- [ ] Append-only/equivalently auditable broker event history and richer deterministic replay.
- [ ] Advanced calibration/drift/evidence-decay automation.
- [ ] Serverless-versus-direct evidence campaign.
- [ ] Safe software self-improvement proposals may open tested PRs but may never self-merge, weaken hard policy, or grant themselves spending authority.

## Evidence rules

A checkbox or gate is complete only when the required evidence is linked or described. Acceptable evidence includes merged pull requests/commits, green focused CI, retained machine-readable test artifacts, clean-Windows proof, redacted live Vast resource/billing evidence, signed artifact provenance, or written accepted-risk records.

Code existing is not enough for a live-system claim. Provider documentation is not live validation. Simulator evidence can close simulator gates, not real billing/hardware gates.

## Known repository CI debt

The general repository CI currently contains failures that predate PR #15 and the post-merge state sync:

- `security-fast` fails the production dependency audit;
- `check-docs` fails the repository formatting lane;
- the aggregate `openclaw/ci-gate` therefore fails.

The same failure categories were present on the merged PR #14 baseline. They are **not** being called green and still need repair, but they are not evidence that the PR #15 documentation design changed runtime behavior.

Focused PR #15 checks passed: Mentat Runtime, Mentat Desktop, Workflow Sanity, Shared OpenClawKit Periphery, iOS Periphery, and macOS Periphery.

## Execution log

### 2026-07-22 — completion program started

- Created the persistent execution ledger, work-item backlog, and frozen scope document.
- Added test seams for a fake Vast control plane without changing production Vast defaults.
- No paid compute used.

### 2026-07-23 — no-spend Broker acceptance milestone

- Added reusable fake Vast and fake OpenAI-compatible services.
- Added JSON/SSE/tool/context/outage fixtures and production Broker acceptance orchestration.
- Prior retained evidence for commit `e9c9397cd7f19fd7391ed1a3d95c13d68f5dc446`: Windows Broker success, Ubuntu Broker success, lint/compile/config validation success, 38 tests success, standalone no-spend acceptance success on Windows and Ubuntu.
- PR #11 later merged as `7bb276cf593e09c45e69c41e594b58a1b71f7332`.
- Paid compute used: **none**.

### 2026-07-24 — architecture and construction contracts

- PR #13 merged as `de0dabb521906952f52530ef143dbdd165c8da0d` with the complete target broker architecture.
- PR #14 merged as `ce7a42fadd721b6c5bcb11ffb4356d17751c1eaa` with the master roadmap/checklist, AI construction contract, resume discipline, and machine-readable state.
- Guarded Vast Serverless remains the frozen Mentat 1.0 path; direct Vast instances remain target expansion unless scope changes.

### 2026-07-24 — PR #15 hard broker-design review and merge

- PR #15 merged as `46f8f71b99f7bfecb0f6d16dc6fc33483ca92941`.
- Re-reviewed current official Vast documentation beginning from `https://docs.vast.ai/llms.txt` before locking provider assumptions into the design.
- Added/readied the provider adapter contract, explicit retry ownership, least-privilege target, provider state/error/market normalization, readiness rules, rate-limit discipline, cost-component reconciliation, self-learning/calibration/drift/exploration/regret design, and circuit breakers.
- Hard review found stale handoff/backlog state and corrected it.
- `MNT-411` Spend Governor + atomic budget ledger and `MNT-412` paid execution state machine/concurrency safety were made explicit **P0 Mentat 1.0 requirements** rather than optional optimization.
- Advanced provider/direct-instance/self-improvement work was separated into deferred Program 7 so it cannot silently expand the frozen release scope.
- PR #15 changed documentation/state only: no runtime code, real credentials, or paid compute.

### 2026-07-24 — post-PR-15 handoff synchronization

- Removed the self-referential `main_commit` assumption from machine-readable state. The state now records the commit it was reconciled against and explicitly requires fetching the live `main` tip on resume.
- Cleared PR #15 from active documentation work.
- Kept PR #12 as the exact active engineering work package.
- Reconciled the ledger's in-scope/deferred split with the final work-item backlog.
- No runtime code, credentials, or paid compute changed.

### 2026-07-25 — PR #12 Broker and Runtime repair published

- Verified GitHub `main` at `897220aa68a3b9d6a85d192cfb2018b2d3ceae2c`, PR #12 remote head at `655634d1a4dacb8a4c077a0970e16571f6c8cb48`, and the last focused CI state as Desktop PASS, Broker FAIL, Runtime FAIL.
- Rebased `agent/desktop-no-spend-integration` onto the verified `main`; the clean rebased branch was `731b95bb6f57d7f0ab5dcdddaef9519e1137c22d` before the repair.
- Diagnosed the Broker failures as a runtime hook-composition problem plus a response/evidence completion race. Routed production inference through one explicit integrity path, preserved malformed-response failure evidence, made client completion wait for the evidence commit, and normalized stored benchmark success values to booleans.
- Diagnosed the Runtime failure as a successful installed Windows diagnostic followed by an invalid artifact path. The workflow now copies the report to `RUNNER_TEMP` and uploads that stable path.
- Local evidence: 39 Broker tests passed; focused regression tests passed; Broker Ruff passed; Python compileall passed; Broker configuration check passed; standalone no-spend acceptance passed all nine checks with `paid_compute_used: false`; Electron production main-process syntax passed.
- Windows PowerShell parsing, installed-wrapper execution, artifact upload, and focused GitHub CI still require a remote rerun. No CI gate is being called green from local evidence.
- Published the rebased implementation through the connected GitHub app as `acdc351b6a6609033d7ea39387dee3349842c851`, with parent `897220aa68a3b9d6a85d192cfb2018b2d3ceae2c`, after rechecking that PR #12's remote head had not changed.
- No real credentials, provider behavior, paid compute, Kimi canary, or deferred Program 7 scope was used or changed.

### 2026-07-25 — PR #12 focused CI green and ready for review

- Verified PR #12 head `ee475eab893206d151eaf3e2341c81e60a142685` as open and mergeable against `main` commit `897220aa68a3b9d6a85d192cfb2018b2d3ceae2c`.
- Exact-head focused GitHub evidence passed: Mentat Broker run `30186887152`, Mentat Runtime run `30186887132`, Mentat Desktop run `30186887114`, and Workflow Sanity run `30186887142`.
- The Desktop workflow built the NSIS installer, verified the executable and installer, smoke-installed the package, ran the installed no-spend command, and retained its report. No paid compute was used.
- Updated the PR body with the problem, repair, user impact, safety invariants, exact evidence, and remaining Gate 1 scope.
- Inspected top-level comments, submitted reviews, and inline review threads; none were present, so there were no ClawSweeper rank-up moves to apply.
- Marked PR #12 ready for review. This does not claim Gate 1 complete and does not bypass the repository-native landing workflow.

### 2026-07-25 — PR #12 ready-review findings repaired locally

- The ready-for-review Codex pass found three actionable issues: malformed tool-call entries could become successful evidence, invalid usage telemetry could raise after a 200 response began, and desktop diagnostics blocked Electron's main thread.
- JSON completions now validate every nonempty tool call, including its id, function type, function name, and JSON-object arguments, before the response can count as successful evidence.
- Optional `usage.completion_tokens` telemetry is accepted only when it is finite, positive, and numeric; malformed telemetry is ignored before response headers or body are sent.
- Desktop diagnostics now run through an asynchronous child process. The menu action is disabled while a run is active, output capture is bounded, credentials remain cleared, and timeout termination is covered by Node tests.
- Local evidence after the fixes: 41 Broker tests passed; Broker Ruff passed; desktop syntax and two process-handling tests passed; standalone no-spend acceptance passed all nine checks with `paid_compute_used: false`; Python compileall, workflow YAML parsing, and diff checks passed.
- Exact-head GitHub evidence passed on `793e253be0930f1a4011d4c691ac129f80386119`: Mentat Broker `30187463254`, Mentat Runtime `30187463264`, Mentat Desktop `30187463286`, Workflow Sanity `30187463275`, and CodeQL `30187463279`.
- Replied to each review finding with its commit and regression evidence, then resolved all three threads. No real credentials or paid compute were used.

### 2026-07-26 — PR #12 merged and clean-install packaging gap identified

- PR #12 merged into `main` as `c374e529bb03d16606c2ae03b6b05b04c748e69a` from verified head `546e2e1a34a1a06e19f0e4ca0984baa2c8e5d228`.
- The source-tree installed `mentat test no-spend` path, desktop asynchronous diagnostics, response-integrity fixes, installer build/smoke-install, and retained no-spend evidence are now on `main`.
- Focused Broker, Runtime, Desktop, Workflow Sanity, and CodeQL evidence remained green; no real credentials or paid compute were used.
- Review of the retained Desktop artifact found that it contains the Electron NSIS installer only. The source-tree `install.ps1` creates the `mentat` wrapper and embeds the checkout path, so the artifact cannot yet support `mentat doctor` or command diagnostics on a truly clean PC.
- MNT-202 remains `PARTIAL`; its next engineering slice is a complete clean-install runtime artifact. Owner-PC installation, actual Docker tool execution, credential-boundary and authentication proof, reject/timeout behavior, and restart/shutdown recovery follow only after that artifact passes clean-runner CI.
- PR #9 remains open but is diverged from `main` and is not the current execution slice; it must be separately reviewed before any of its changes are reused.

### 2026-07-26 — Shot 1 complete-runtime package proven on a clean runner

- PR #18 packages `Mentat.exe`, the exact Node runtime, OpenClaw, the Mentat runtime/Broker scripts, the model registry and all registry-declared endpoint configs, plus a checkout-independent `mentat` wrapper in one NSIS artifact.
- The installer provisions the runtime transactionally under the installed desktop resources, maintains the user PATH entry, preserves user configuration/state on uninstall, and removes the source-checkout dependency from installed commands.
- Packaged-runtime doctor no longer requires Git, npm, pnpm, or system Node. Runtime endpoint validation is derived from the guarded model registry rather than a hard-coded provider list.
- Exact code head `748d5a069873961aa82a632d9556c2b06f14b45b` passed Mentat Desktop run `30207508634`: the installer was built, installed silently from a clean Windows runner, and verified outside the checkout; installed doctor reported 0 failures and the expected unconfigured-provider warning; installed command and desktop no-spend diagnostics both passed with `paid_compute_used: false`.
- The exact code head also passed Mentat Runtime `30207508662`, Workflow Sanity `30207508638`, and all three Periphery lanes. The installed no-spend report (artifact `8633637438`) and Windows installer (artifact `8633638741`, SHA-256 `d029e5431dd6492704ab3b78862710d521b34e29d5c35d32698c3b05257b9911`) were retained.
- PR #17 remains open, so PR #18 remains stacked on its Shot 0 branch. Land PR #17 first, then retarget/revalidate PR #18 against `main`; this evidence does not claim either PR is merged.
- MNT-202 remains `PARTIAL`: its complete-runtime packaging slice is proven, while MNT-203 through MNT-206 still require clean owner-PC installation, actual Docker isolation, credential-boundary/authentication proof, reject/timeout behavior, and restart/shutdown recovery. Gate 1 remains `IN PROGRESS`.
- No real credentials, external provider calls, or paid compute were used.

## Current handoff

```text
Date/time: 2026-07-26T15:24:54Z
State reconciled against main: c374e529bb03d16606c2ae03b6b05b04c748e69a
Current main tip verified live: c374e529bb03d16606c2ae03b6b05b04c748e69a
Documentation branch/PR: agent/post-pr12-gate1-handoff / PR #17 / OPEN / READY FOR REVIEW
Engineering branch/PR: agent/mnt-202-complete-runtime-package / PR #18 / OPEN / STACKED ON PR #17
MNT work item: MNT-002 / MNT-202
Last completed item: Shot 1 complete-runtime packaging slice proven on a clean Windows CI runner
Current item: Land Shot 0, retarget/revalidate and land Shot 1, then perform owner-PC Gate 1 validation
Shot 0 head: 94d8925eb9d8f64bf255b965827f15c07b78f30a
Shot 1 validated code head: 748d5a069873961aa82a632d9556c2b06f14b45b
Exact-code-head focused CI: Mentat Runtime PASS (30207508662); Mentat Desktop complete install PASS (30207508634); Workflow Sanity PASS (30207508638); Periphery PASS
Clean-runner evidence: installer/runtime/wrapper present outside checkout; doctor 0 failures/1 expected warning; command no-spend 9/9 PASS; desktop no-spend PASS; paid compute used false
Local validation: desktop/packaging tests 11 passed; changed JavaScript syntax checks passed; workflow YAML parsed
Known proof gap: clean owner-PC installation, actual Docker tool isolation, credential-boundary/authentication, reject/timeout, and restart/shutdown recovery remain for Gate 1
Owner action required: merge PR #17, then merge the retargeted/revalidated PR #18; perform MNT-203 through MNT-206 on a clean owner Windows PC; private-repository migration remains required before real credentials or paid tests
Exact next task:
1. Merge PR #17 through the repository-native review/landing workflow.
2. Retarget PR #18 from agent/post-pr12-gate1-handoff to main and verify it remains mergeable.
3. Revalidate PR #18 against the resulting main tip, then merge it through the repository-native workflow.
4. Run MNT-203 through MNT-206 on a clean owner Windows PC and retain the machine-readable evidence.
Do not do: real credentials, paid compute, Kimi canary, Gate-1 completion claims, a new broker implementation feature that bypasses Gate 1, or deferred Program-7 work.
```

## Handoff template

```text
Date/time:
State reconciled against main commit:
Current main tip verified live:
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
