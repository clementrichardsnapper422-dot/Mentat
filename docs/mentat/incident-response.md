# Mentat incident response and recovery

## Immediate containment

1. Enable the local paid-compute kill switch.
2. Disconnect Mentat from the network if credential compromise or uncontrolled provider activity is suspected.
3. Do not delete local state, logs, or release evidence.
4. From a separate trusted browser, inspect provider resources and cool/stop them using the safest validated action.
5. Revoke or rotate affected provider, broker, GitHub, and signing credentials.

## Incident classes

### Unexpected spend or duplicate resource

- Keep the kill switch enabled.
- Export spend reservations, execution events, provider-resource identifiers, approval lease IDs, and provider billing.
- Reconcile every ambiguous resource before retrying anything.
- Treat an actual amount above the reserved ceiling as a P0 security failure.

### Credential exposure

- Rotate the credential before further investigation.
- Identify whether exposure occurred in a prompt, URL, renderer, log, crash report, tool environment, workspace, Git history, CI log, or artifact.
- Purge public history only after a forensic copy and rotation; never assume deletion makes an exposed credential safe.

### Corrupt or unavailable local database

- Keep paid compute locked out.
- Copy the damaged database, WAL, and SHM files before repair.
- Confirm provider state independently.
- Restore from the latest verified backup; do not create a new empty authority database while a remote resource may exist.

### Bad release or update

- Enable the kill switch and stop Mentat.
- Preserve `%LOCALAPPDATA%\Mentat`.
- Verify the previous installer signature and checksum.
- Roll back and run doctor/no-spend acceptance.
- Do not re-enable paid compute until saved executions and provider resources reconcile.

## Evidence package

Retain timestamps, machine identity, Mentat/source versions, installer hash/signature, release-gate report, relevant SQLite copies, JSON acceptance reports, sanitized logs, provider resource IDs/status, billing records, credential-rotation timestamps, containment actions, root cause, corrective changes, and reviewer approval.

## Recovery exit criteria

- All provider resources are known and safely cooled/stopped/destroyed.
- Spending credentials are rotated when exposure is possible.
- Local databases pass integrity checks or are restored from verified backup.
- Doctor, no-spend acceptance, Docker isolation, and restart recovery pass.
- Security findings are closed or explicitly accepted by the release owner.
- The kill switch is disabled only for a deliberate approved operation.
