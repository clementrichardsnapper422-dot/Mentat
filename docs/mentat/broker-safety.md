# Broker spending and approval safety

The model broker is designed around a simple rule: no language model may rent GPU compute directly.

## Price shown versus worker selected

The marketplace row shown in Mentat is a compatible live reference offer. Vast Serverless may choose another compatible worker rather than that exact listing ID. Before creation or warming, Mentat rewrites the workergroup query so the selected worker cannot exceed the hourly price the user approved. The worker may be cheaper, but not more expensive.

## Session budget

A model approval is bounded by all of the following:

- the model-specific hourly cap
- the global hourly cap
- the total-dollar cap
- the maximum session duration
- the 30-minute idle timeout

The approval expiration is shortened automatically when `total budget / hourly price` is less than the configured maximum session duration. Expired sessions are cooled even when they are not idle.

Only one paid Vast model session is active by default. This avoids accidentally warming Kimi and Qwen at the same time. Advanced operators may change `MENTAT_MAX_ACTIVE_PAID_SESSIONS`, but increasing it can create overlapping hourly charges.

## Approval security

The local broker accepts state-changing bodies only as JSON. The Compute Decisions page also receives an unpredictable approval token created for that broker process. The token is included with an approval but is not exposed by the public status endpoints. An unrelated website therefore cannot silently approve paid compute through a loopback request.

## New endpoint warning

A decision records whether the selected model already has saved endpoint state. When it does not, the decision explains that first approval may create the endpoint and run a paid benchmark worker before the task session begins.

## Broker-first setup

The committed Kimi endpoint identity may be configured before the endpoint exists. It can remain offline without GPU charges. The broker creates or warms it only after a matching decision is approved. Fresh Unix installs receive that endpoint identity from `config/mentat.env.example`; Windows setup uses the same endpoint name shown in the committed Kimi profile.
