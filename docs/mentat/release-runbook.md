# Mentat 1.0 release runbook

## Roles

- **Release owner:** approves scope, paid canaries, security risk acceptance, and final release.
- **Operator:** performs clean Windows installation, recovery, canary, and soak evidence collection.
- **Reviewer:** verifies code head, CI, unresolved threads, threat model, and evidence integrity.
- **Signing custodian:** controls the Authenticode certificate and protected release job.

## Release-candidate procedure

1. Verify GitHub `main`, the active PR head, README, production contract, work items, ledger, and current state agree.
2. Confirm no real provider credential exists in Git history, CI variables exposed to PRs, logs, fixtures, or artifacts.
3. Require focused Broker, Runtime, Desktop, Workflow Sanity, CodeQL, and Mentat 1.0 acceptance checks on the exact head.
4. Build the Windows installer on a clean hosted Windows runner.
5. Smoke-install and run installed `mentat doctor` plus `mentat test no-spend`.
6. Generate and retain release-candidate checksum, SBOM, provenance, installer, and acceptance JSON artifacts.
7. Merge only when exact-head CI is green and review threads are resolved.

## Owner-machine Gate 1

1. Use a clean supported Windows account with Docker Desktop active.
2. Install only from the generated installer; do not use a source checkout.
3. Run `mentat doctor`.
4. Run `mentat test no-spend`.
5. Run `mentat test gate1-owner`.
6. Inspect renderer, prompt, URL, log, crash, workspace, Gateway, and tool surfaces for forbidden credentials.
7. Test normal app close, forced process termination, user logoff, and Windows reboot.
8. Copy evidence from `%LOCALAPPDATA%\Mentat\state` to protected release storage and calculate SHA-256 digests.

## Live canary controls

1. Confirm repository and credentials are private and least privilege has been measured.
2. Set tiny hourly and total ceilings and enable the global kill switch by default.
3. Disable the kill switch only for the planned canary window.
4. Approve exactly one low-cost session from `Mentat.exe`.
5. Verify rejection starts nothing; reuse does not request another approval; cooling reaches zero workers.
6. Import the actual provider bill and reconcile it to the reservation and displayed ceiling.
7. Re-enable the kill switch immediately after the test.
8. Repeat for Kimi only after Gate 2 passes.

## Final signed release

1. Tag the exact reviewed commit with `mentat-v1.0.0` from protected `main`.
2. Run the protected release workflow with the signing certificate and password.
3. Require Authenticode status `Valid` for the installer and executable.
4. Verify `SHA256SUMS`, CycloneDX SBOM, provenance, source commit, and installer version.
5. Install the signed artifact on a clean Windows machine and rerun doctor/no-spend plus a non-spending startup test.
6. Record final evidence in the Control Center/evidence ledger.
7. Publish only when `production_ready` is true.

## Rollback

- Enable the kill switch before rollback.
- Cool/reconcile all saved provider resources.
- Back up `%LOCALAPPDATA%\Mentat\state` and configuration.
- Install the previously signed known-good artifact.
- Preserve local user data unless the incident procedure explicitly requires quarantine.
- Run doctor and no-spend acceptance before re-enabling paid compute.
