# Mentat

**A Windows-native AI operator and evidence-driven model-and-compute broker built on OpenClaw.**

Mentat keeps the Gateway, tools, memory, repository access, approval gates, and user data on your computer. Remote inference is treated as a controlled resource: Mentat evaluates the task, selects an eligible model and compatible compute strategy, explains the expected tradeoffs, requires approval before new paid compute, records what actually happened, and uses verified evidence to improve future routing.

The long-term goal is not simply to run the strongest model or rent the cheapest GPU.

> **Mentat should obtain the best verified result for the lowest practical total cost while satisfying the required quality, context, capability, reliability, latency, risk, and spending limits.**

Kimi is an important dependable primary model, but Kimi is not Mentat. Vast.ai is an important compute marketplace, but Vast.ai is not Mentat. The broker, its policy boundaries, and its growing body of local evidence are what make Mentat different.

---

## Table of contents

- [What Mentat is](#what-mentat-is)
- [System architecture](#system-architecture)
- [How a request flows through Mentat](#how-a-request-flows-through-mentat)
- [Task analysis](#1-task-analysis)
- [Context estimation](#2-context-estimation)
- [Risk and verification analysis](#3-risk-and-verification-analysis)
- [Model registry](#4-model-registry)
- [Hardware planning](#5-hardware-planning)
- [Compute backends](#6-compute-backends)
- [Vast marketplace discovery](#7-vast-marketplace-discovery)
- [Host reputation](#8-host-reputation)
- [Direct instance provisioning](#9-direct-instance-provisioning)
- [Mentat workers](#10-mentat-workers)
- [Security and spending authority](#11-security-and-spending-authority)
- [Candidate generation and scoring](#12-candidate-generation-and-scoring)
- [Total-cost prediction](#13-total-cost-prediction)
- [Cold starts and reuse](#14-cold-starts-and-reuse)
- [Keep, stop, cool, or delete](#15-keep-stop-cool-or-delete)
- [Spend policy and approval](#16-spend-policy-and-approval)
- [Inference and tools](#17-inference-and-tools)
- [Verification](#18-verification)
- [Telemetry and execution history](#19-telemetry-and-execution-history)
- [Human ratings](#20-human-ratings)
- [Learning, promotion, and demotion](#21-learning-promotion-and-demotion)
- [Safe exploration](#22-safe-exploration)
- [Fallback](#23-fallback)
- [Watchdogs and failure recovery](#24-watchdogs-and-failure-recovery)
- [Example decisions](#example-decisions)
- [Current implementation versus target design](#current-implementation-versus-target-design)
- [Installation and operation](#install-in-a-few-minutes)

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
- How reliable are those hosts based on both marketplace data and Mentat's own history?
- How long will a cold start take?
- What will the entire job cost, not just the GPU hourly rate?
- Is the proposed spend permitted?
- Should compute remain warm, be cooled or stopped, or be destroyed afterward?

The system should become better at answering those questions as it operates.

A useful mental model is:

```text
Request
  -> requirements
  -> eligible models
  -> eligible hardware
  -> eligible compute backends
  -> candidate execution plans
  -> policy and approval
  -> execution
  -> verification
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
                         Candidate Plans
                                |
                                v
                         Broker Scoring
                                |
                                v
                         Spend Policy
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

**Mentat is the local operator, broker, policy boundary, evidence store, and learning loop that decides how those resources should be used.**

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
8. Compute backends produce live execution candidates
9. Broker scores candidates for quality, cost, latency, and reliability
10. Spend policy rejects anything outside hard limits
11. New paid compute waits for authenticated local approval
12. Approved compute is created, reused, or warmed
13. Inference runs
14. Tools run locally through the OpenClaw security boundary
15. Mentat verifies the result where possible
16. Runtime telemetry is recorded
17. Human quality feedback may be recorded separately
18. Compute is kept warm, cooled/stopped, or destroyed according to policy
19. The learning system updates evidence for future decisions
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
human review
```

This matters economically.

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

The broker should first determine the cheapest technically valid hardware class, then evaluate marketplace offers within that class.

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
  -> search Vast marketplace
  -> rent CUDA instance
  -> provision Mentat worker
  -> install/verify runtime
  -> load selected model
  -> start OpenAI-compatible API
  -> health check
  -> inference
```

Direct instances give Mentat finer control over the exact host, GPU, storage, runtime, provisioning path, and lifecycle.

**Important:** direct Vast instance support is a target architecture capability and should not be confused with the currently validated Serverless path unless and until it is implemented and tested.

---

# 7. Vast marketplace discovery

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

The broker therefore learns not merely that:

```text
RTX 5090 is good
```

but that a specific GPU class on a specific host with a specific storage/network profile has performed well or poorly for Mentat's real workload.

---

# 9. Direct instance provisioning

When the future direct-instance backend chooses a raw Vast CUDA worker, Mentat should automatically transform it into an inference service.

The target flow is:

```text
Rent instance
  -> CUDA container starts
  -> Mentat provisioning script runs
  -> verify runtime dependencies
  -> install vLLM/SGLang when needed
  -> acquire selected model
  -> load model
  -> start OpenAI-compatible server
  -> expose health endpoint
  -> health check
  -> mark worker ready
```

Vast's CUDA development environment supports a provisioning-script mechanism, which is a natural fit for this design.

A worker bootstrap can receive controlled configuration such as:

```text
MENTAT_MODEL=<registered model id>
MENTAT_RUNTIME=vllm
MENTAT_PORT=8000
MENTAT_JOB_ID=<job id>
MENTAT_LEASE_SECONDS=<bounded lease>
```

The provisioning path should be versioned, integrity checked, and treated as part of Mentat's supply chain.

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
  +-- selected model
  +-- OpenAI-compatible inference API
  +-- health monitor
  +-- metrics collector
  +-- lease/watchdog
  +-- shutdown controller
```

The worker is disposable muscle. The broker remains the brain.

The worker should expose only the capabilities required to serve inference and report health/telemetry. Infrastructure credentials and local user tools do not belong inside the model process.

---

# 11. Security and spending authority

Mentat has a hard security rule:

> **A language model cannot create, warm, resize, approve, or otherwise authorize paid compute.**

Spending authority belongs to the local broker and ultimately the local authenticated user.

The intended credential boundary is:

```text
                 Local PC

+-------------------------------------------+
| Broker process                            |
|   - Vast credential                       |
|   - spending policy                       |
|   - infrastructure lifecycle authority    |
+-------------------+-----------------------+
                    |
         non-spending authenticated API
                    |
+-------------------v-----------------------+
| OpenClaw Gateway / tools / Mentat.exe     |
|   - no Vast spending credential           |
+-------------------+-----------------------+
                    |
                    v
               Model endpoint
                    |
                    X
             no Vast API key
```

Approval credentials must never appear in:

- model prompts
- tool environments
- URLs
- logs
- Git history
- repository workspaces

The current Windows installation protects the Vast API key with Windows DPAPI for the current operating-system user.

---

# 12. Candidate generation and scoring

Mentat should score complete **execution plans**, not isolated GPUs.

A candidate is a combination of factors such as:

```text
Candidate
  |
  +-- model
  +-- model version
  +-- runtime
  +-- hardware configuration
  +-- compute backend
  +-- specific host or Serverless profile
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
Predicted cold start: 95 sec
Predicted inference: 22 sec
Predicted total cost: $0.014
```

versus:

```text
Candidate B

Model: Kimi
Backend: Vast Serverless
GPU: larger multi-GPU profile
Predicted quality: 4.9 / 5
Predicted startup: 30 sec
Predicted inference: 15 sec
Predicted total cost: $0.41
```

The correct choice depends on the task requirements.

A low-risk CSS change probably does not justify paying many times more for a small quality advantage. A repository-wide architecture or security task may justify exactly that premium.

Conceptually the broker is optimizing something like:

```text
expected useful result
  = quality
  x reliability
  x probability of successful completion

while minimizing:
  total cost
  latency
  failure risk
```

The production implementation should use explicit, testable scoring rules rather than a vague single formula.

---

# 13. Total-cost prediction

GPU hourly price is only one component of real task cost.

Mentat should estimate:

```text
TOTAL EXPECTED COST

instance or endpoint acquisition
+ container/image startup
+ provisioning
+ model download
+ model loading
+ inference runtime
+ retry probability
+ failed-start probability
+ warm idle time
+ storage
+ bandwidth
+ teardown overhead
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
```

A $0.30/hour GPU that takes ten minutes to become useful can be worse for an interactive job than a more expensive worker that is already warm.

Vast billing remains the source of truth for actual infrastructure charges. Mentat predictions are estimates that must later be reconciled with actual billing evidence.

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

Over time the broker can learn the economically useful warm window from actual request patterns.

---

# 15. Keep, stop, cool, or delete

Different backends expose different lifecycle choices.

## Serverless

A Serverless endpoint can remain reusable while its worker floor is cooled to zero when idle.

Conceptually:

```text
endpoint identity remains
workers cool to zero
future approved work can reuse endpoint identity
```

## Direct instance target

A direct Vast instance may support economically distinct choices such as:

### Keep warm

```text
GPU running
model loaded
fast next request
GPU billing continues
```

### Stop

```text
GPU compute stops
persistent storage may remain
storage charges may continue
future restart may avoid downloading everything again
```

### Delete

```text
instance removed
associated instance storage removed according to Vast lifecycle semantics
all avoidable charges end
next job requires a cold start
```

The broker should eventually compare the expected cost of keeping compute warm, retaining storage, or destroying the worker based on the probability and timing of future tasks.

Example:

```text
Expected next task: 4 minutes
  -> keep warm may win

Expected next task: several hours
  -> stop/cool may win

Expected next task: tomorrow or unknown
  -> delete may win
```

These are policy decisions backed by measured evidence, not hard-coded guesses forever.

---

# 16. Spend policy and approval

Before any paid compute is started, the candidate must pass hard policy limits.

Examples include:

```text
maximum hourly rate
maximum estimated job cost
maximum session cost
maximum session duration
maximum simultaneous paid model sessions
approved providers
approved GPU classes
approved model profiles
```

New paid sessions require authenticated local approval.

A decision UI should explain what is being purchased before money is spent.

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

Estimated task cost:
$0.28

Maximum approved cost:
$0.50

Reason:
Repository-scale reasoning requires the highest validated quality tier.

[ APPROVE ]   [ REJECT ]
```

Approval is a **bounded lease**, not unlimited permission.

For example:

```text
Model: Kimi
Maximum total cost: $0.50
Maximum hourly rate: $4.00
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

A malformed or failed upstream result must not become a successful learning sample.

Verification evidence is especially important when cheaper models are being considered for promotion.

---

# 19. Telemetry and execution history

Every completed decision should create a structured operational record.

A future record may contain fields such as:

```text
Task ID:                 82174
Task class:              coding-medium
Model:                   Qwen
Model version:           pinned version
Backend:                 Vast Direct
GPU:                     RTX 5090
Host:                    402342
Marketplace price:       $0.300/hr
Startup time:            18.4 sec
Provision time:          21.8 sec
Model download:          48.1 sec
Model load:              32.6 sec
Time to first token:     0.77 sec
Generation throughput:   84.2 tok/sec
Inference duration:      21.4 sec
Total worker lifetime:   143.7 sec
Estimated cost:          $0.012
Actual reconciled cost:  pending
Result:                  success
Verification:            passed
Human rating:            5/5
```

Runtime measurements and human quality ratings are deliberately separate forms of evidence.

The history should answer questions such as:

- Which model is best for TypeScript debugging?
- Which model is cheapest for simple code edits without reducing success rate?
- Which hosts fail most often?
- Does H100 beat RTX 5090 after cold-start time is included?
- Is Serverless or a direct instance better for Kimi?
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
hardware/runtime context
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
  second instance required
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

Result:
promote for coding-medium
```

## Demotion

Promotion is reversible.

If a model version, host class, runtime, or workload begins producing worse outcomes, Mentat should reduce its preference or remove it from eligibility until revalidated.

Every promotion and demotion should have an audit trail.

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
```

A high-risk repository-scale task must not silently fall back to a tiny cheap model solely because the preferred endpoint became unavailable.

Fallback should also avoid silently starting a second paid cluster outside the user's approved spending boundary.

---

# 24. Watchdogs and failure recovery

Paid compute must fail safely when Mentat, Windows, the network, or Vast behaves unexpectedly.

The system must account for failures such as:

```text
Windows restart
user logoff
broker crash
Gateway crash
network loss
ambiguous create response
Vast API timeout
worker startup failure
model-server crash
stream interruption
disk full
SQLite corruption
context overflow
runaway tool loop
```

## Local lifecycle reconciliation

The broker should use idempotent or explicitly reconciled lifecycle operations, write local state atomically, and fail closed on duplicate or orphaned remote resources.

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
Maximum approved cost: $0.50

Approve?
```

This is exactly the kind of task where premium compute is justified.

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
- Windows and Ubuntu CI coverage for the no-spend path

## Target broker capabilities still being completed or validated

The complete design also calls for work such as:

- repository- and attachment-aware task estimation
- explicit blast-radius and verification-availability classification
- versioned experimental/approved/retired model lifecycle
- richer candidate scoring with uncertainty
- real cold-start prediction
- real total-cost prediction
- direct Vast instance backend
- automatic CUDA worker provisioning
- worker leases/watchdogs
- host-specific reputation and bad-host suppression
- warm/stop/delete optimization for direct instances
- canonical benchmark corpus and grading harness
- quality prediction with confidence bounds
- safe exploration
- promotion and demotion policy
- routing-regret reporting
- Kimi-only baseline cost comparison
- actual Vast billing reconciliation
- low-cost live canary
- Kimi canary
- clean Windows target-machine validation
- long-running soak and adversarial failure testing
- signed reproducible release pipeline

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
AND SPENDING LIMITS
```

That is the central Mentat design principle.

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

On Windows, the key is DPAPI-encrypted in `%LOCALAPPDATA%\Mentat\config\config.json`. On macOS and Linux, the local environment file is created with owner-only permissions.

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

The no-spend acceptance path is intentionally separate from live Vast canaries. Passing a no-spend test proves local broker behavior against the simulator; it does not prove real Vast billing or real GPU behavior.

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
