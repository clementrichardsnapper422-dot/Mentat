# Mentat 1.0 one-shot release campaign

## Objective

Collapse the remaining Mentat 1.0 engineering program into one release-candidate branch without weakening the production contract or manufacturing live evidence. This campaign finishes every repository-controlled capability and produces a single evidence-driven path from source to a signed release.

## Definition of done

Mentat 1.0 is released only when the local Control Center reports `production_ready: true`. That value is derived from retained evidence for Gates 0–5 in `docs/mentat/production-contract.md`; it is not a manually editable marketing flag.

The campaign has two outcomes:

1. **Engineering-complete release candidate** — all code, tests, desktop surfaces, packaging, runbooks, checksums, SBOM/provenance generation, and fail-closed gates are merged.
2. **Production release** — owner-machine, credential, provider, billing, signing, security-review, and soak evidence is subsequently recorded and every gate passes.

## One-shot workstreams

### 1. Safety authority

- Signed, expiring, authenticated `ApprovalLease` contracts.
- One `SpendGovernor` as the only component permitted to increase paid exposure.
- Atomic worst-case reservations before acquisition.
- Hourly, session, daily, monthly, retry, fallback, and exploration caps.
- Emergency local paid-compute kill switch.
- Overspend detection that enters reconciliation and activates the kill switch.

### 2. Durable execution

- Explicit paid-execution state machine with enumerated legal transitions.
- Compare-and-swap version checks for racing actors.
- Provider lifecycle stored separately from Mentat execution state.
- Unique provider-resource identity to prevent double ownership.
- Restart plans that reconcile remote state before any repeated paid mutation.
- Append-only execution event evidence.

### 3. Backend boundary

- Provider-neutral `ComputeBackend` contract.
- Guarded Vast Serverless adapter boundary for the frozen 1.0 path.
- Deterministic fake backend for zero-dollar acceptance.
- Direct Vast instances remain an explicit, non-production-eligible stop sign.

### 4. Routing and learning

- Structured task requirements including context, tools, repository size, reversibility, risk, verification, latency, and budget.
- Versioned model/runtime profiles and timestamped provider snapshots.
- Quality, success, cost, and latency ranges with uncertainty.
- Hard eligibility before economic scoring.
- Best, Balanced, Economy, and Manual preferences that cannot bypass safety.
- Low-risk capped exploration only inside the eligible set.
- Independent fallback validation, drift penalties, circuit breakers, failure classification, replayable explanations, and routing-regret measurement.

### 5. Desktop product

- Authenticated local Mentat Control Center.
- Release-gate status and exact blockers.
- Paid-compute exposure, limits, and recent events.
- Emergency lockout control.
- Saved executions and startup-recovery actions.
- Backend production eligibility.
- Existing compute-decision and no-spend diagnostic surfaces remain intact.

### 6. Release engineering

- Versioned RC installer.
- Clean Windows build and smoke install.
- Zero-dollar release-candidate acceptance.
- SHA-256 checksums.
- CycloneDX file SBOM.
- in-toto/SLSA-shaped provenance statement.
- Authenticode verification required for the final release job.
- Operator, incident, backup, recovery, and rollback runbooks.

## Evidence sequence

1. Merge the release-candidate engineering branch with focused CI green.
2. Move the repository to a standalone private repository and protect `main`.
3. Build/install on the owner’s clean Windows PC.
4. Run `mentat test gate1-owner`; retain its JSON report.
5. Record app close, forced process kill, logoff, and reboot recovery.
6. Validate current Vast API assumptions and least-privilege permissions.
7. Run one capped low-cost canary; reconcile the actual bill.
8. Run the Kimi canary with tool, reasoning, context, streaming, and cap evidence.
9. Complete 100-session, 24-hour, and multi-day soak/adversarial testing.
10. Close or explicitly accept security findings.
11. Build with the Authenticode certificate, verify signature, checksums, SBOM, and provenance.
12. Install the signed artifact and record the final Gate 5 evidence.

## Non-negotiable stop conditions

- No real credential enters a public repository, prompt, tool environment, log, URL, or CI job.
- No paid resource starts without a valid local approval lease and atomic reservation.
- No ambiguous paid mutation is blindly retried.
- No failed, malformed, interrupted, stale, or unverified result becomes positive learning evidence.
- No direct-instance capability is described as Mentat 1.0 production functionality.
- No release is announced while the evidence ledger reports a pending required gate.
