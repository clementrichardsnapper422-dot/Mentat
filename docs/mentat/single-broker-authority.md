# Mentat single broker authority

## Purpose

Mentat must have one component that can say **yes** to paid compute. Routing code, desktop code, provider adapters, and LLMs may supply information or perform delegated work, but none of them may independently authorize money, create provider resources, or declare a route ready.

The production authority is `BrokerAuthority`, backed by `MentatV1Runtime`'s durable spend and execution stores.

## System boundary

```text
OpenClaw request
    |
    v
legacy production router
(candidate proposal only)
    |
    v
BrokerAuthority
(final capability, policy, state, and spend acceptance)
    |
    +--> signed approval lease
    +--> atomic worst-case reservation
    +--> durable execution record
    |
    v
Vast Serverless adapter
(delegated provider operation only)
    |
    v
provider resource identity + health proof
    |
    v
BrokerAuthority READY gate
    |
    v
LLM inference
```

## Inputs and outputs

### 1. Candidate proposal

**Inputs**

- task class and prompt size
- required capabilities
- enabled model registry
- measured quality evidence
- live or reusable provider offer
- caller and desktop budget ceilings

**Output**

- a proposed `Decision`

The established production router remains in this step because it contains the proven Vast Serverless selection behavior. It is not allowed to authorize provider mutation.

### 2. Authority acceptance

**Inputs**

- proposed decision
- immutable registry policy
- current desktop privacy and budget policy
- model capabilities, context limit, and enabled state
- existing authoritative execution state

**Output**

- an authoritative execution in `AWAITING_APPROVAL`, or a rejection

A legacy session row by itself is not authority. A route marked approved without a matching authoritative `READY` execution fails closed.

### 3. Paid approval

**Inputs**

- explicit owner approval
- selected model and backend
- approved hourly and session ceilings
- global kill-switch state
- current daily, monthly, and active exposure

**Outputs**

- signed, scoped, expiring `ApprovalLease`
- atomic worst-case spend reservation
- execution bound to the lease and reservation
- short-lived `ProviderMutationGrant`

No Vast mutation is legal before all outputs exist.

### 4. Provider operation

**Inputs**

- valid mutation grant
- exact decision, model, backend, and price
- approved endpoint profile

**Outputs**

- durable endpoint and workergroup identity
- observed hourly price
- endpoint URL retained only inside the broker boundary
- provider lifecycle state

The Vast adapter verifies the grant before calling the provider. Direct calls into the old session manager without the grant are rejected.

### 5. Readiness

**Inputs**

- saved provider identity
- successful model health probe
- active spend reservation
- unexpired approval authority

**Output**

- authoritative `READY` execution

A machine allocation, running container, or legacy `ready` session row is not sufficient by itself.

### 6. Inference

**Inputs**

- OpenAI-compatible request
- selected model
- authoritative `READY` execution
- active spend authority for paid backends

**Outputs**

- normalized LLM response
- decision ID and model headers
- latency, usage, and benchmark evidence

The proxy checks the authority immediately before forwarding the request.

### 7. Cooling and reconciliation

**Inputs**

- manual Cool now, idle timeout, shutdown, or recovery action
- saved provider identity
- current provider and session observations

**Outputs**

- provider cool command
- saved session status
- authority transition through `COOLING` to `COOLED`, or `AMBIGUOUS`
- retained spend reservation until actual billing reconciliation

Sending a cool command is not treated as billing proof. The reservation remains fail-closed until a later provider bill is reconciled.

## Rules that prevent two brains

1. The legacy router may propose; `BrokerAuthority` accepts or rejects.
2. The legacy session manager may operate Vast only with a valid mutation grant.
3. `SpendGovernor` is the only component that reserves paid exposure.
4. `ExecutionStore` is the only authoritative provider/execution state ledger.
5. The legacy decision store remains request history and quality evidence; it is not spending authority.
6. A disabled model cannot receive new work, but remains visible to lifecycle cleanup.
7. A fallback model requires its own authoritative ready state; the proxy cannot silently launch or use it.
8. Missing, expired, mismatched, or ambiguous authority fails closed.
9. The desktop policy can only lower immutable limits, never raise them.
10. Real provider billing remains external evidence and cannot be manufactured in CI.

## Known release boundary

This design removes the overlapping control authority in repository code. It does not prove the live Vast path. Production proof still requires the capped owner-approved canary, provider-state reconciliation, actual billing reconciliation, restart recovery, and retained release-gate evidence defined by the README and production contract.
