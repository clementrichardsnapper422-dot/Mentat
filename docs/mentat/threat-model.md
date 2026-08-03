# Mentat 1.0 threat model

## Assets

The protected assets are the Vast spending credential, broker administration token, approval leases, local conversations and repositories, model/tool inputs and outputs, budget ledger, provider-resource identity, release evidence, installer signing key, and user-controlled configuration.

## Trust boundaries

1. **Electron renderer** — untrusted web content execution boundary; Node integration is disabled, context isolation and sandboxing are enabled, and navigation is constrained to loopback.
2. **OpenClaw Gateway and tools** — may handle user data and execute approved tools, but must never receive a credential capable of spending or broker administration.
3. **Local broker** — only process permitted to hold provider spending authority and make provider lifecycle calls.
4. **Docker tool sandbox** — network disabled by default, read-only root, all capabilities dropped, no-new-privileges, non-root UID, no Docker socket, and only the expected workspace may be writable.
5. **Remote inference/provider** — receives only the context required for inference; provider state and billing are treated as external, fallible observations.
6. **GitHub/CI/release pipeline** — no live provider credential; signing material is scoped only to the protected final-release job.

## Primary threats and controls

| Threat | Control | Required evidence |
| --- | --- | --- |
| Model starts paid compute | Models cannot issue approval leases; Spend Governor verifies a signed local lease immediately before reservation | Adversarial broker tests |
| Concurrent requests overcommit budget | `BEGIN IMMEDIATE` worst-case reservation and one-active-paid-session default | Concurrency tests and ledger events |
| Price changes after approval | Provider rate must be within both lease and policy ceiling before acquisition | Low-cost canary and bill reconciliation |
| Ambiguous create causes duplicate worker | Explicit ambiguous/reconciling state; idempotency key; remote identity reconciliation before retry | Failure injection and live canary |
| Credential reaches tools or prompts | Separate client/admin/provider credentials; environment stripping; Docker inspection; no credentials in URLs | Gate 1 owner report and manual surface inspection |
| Tool escapes host boundary | Docker network none, read-only root, dropped capabilities, non-root UID, no socket, expected mounts only | Actual OpenClaw tool execution report |
| Renderer gains host access | Node integration off, context isolation/sandbox on, loopback-only navigation, CSP | Desktop tests and security review |
| Malformed output becomes positive evidence | Protocol validation and explicit failed benchmark evidence | No-spend malformed-response test |
| Stale evidence promotes weak model | Model/runtime version binding, age penalties, conservative lower bounds, drift demotion | Routing tests and replay report |
| Fallback silently starts extra paid compute | Independent eligibility, remaining-budget check, lease fallback scope, one-session invariant | Fallback and Spend Governor tests |
| Database loss silently resets authority | SQLite WAL/FULL, corruption fails closed, atomic release evidence writes, backup runbook | Corruption/recovery tests |
| Kill switch bypass | All spend-increasing operations pass through one governor and read durable switch state inside the transaction | Lockout acceptance test |
| Unsigned/tampered installer | Authenticode verification, SHA-256 checksums, SBOM, provenance, protected release job | Gate 0 and Gate 5 artifacts |

## Residual risks requiring owner acceptance or closure

- The Windows user account and local machine remain a high-value trust anchor.
- Provider billing/status APIs can be delayed or inconsistent; Mentat must reconcile rather than guess.
- A compromised signing certificate can produce apparently trusted malware; certificate storage and revocation procedures are mandatory.
- Remote inference necessarily exposes submitted context to the selected provider endpoint; the UI and policy must make that boundary clear.
- The public repository cannot safely hold real credentials or live release evidence. Private-repository migration remains mandatory before paid validation.
