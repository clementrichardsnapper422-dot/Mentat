# Mentat model and compute broker

The broker is the local policy layer between OpenClaw and model endpoints. It is intentionally deterministic and binds to `127.0.0.1` only.

It provides:

- a versioned model registry
- live Vast offer discovery
- benchmark persistence in SQLite
- task classification and value routing
- explicit approval before a paid endpoint is created or warmed
- approved-session reuse
- 30-minute idle scale-to-zero
- fallback chains among already approved endpoints
- an OpenAI-compatible `/v1/chat/completions` proxy
- a local decision dashboard at `/ui/decisions`

Bootstrap quality numbers in `config/model-registry.json` are policy priors, not benchmark claims. After a model has enough local rated runs, the router uses the measured score.

## Development

```bash
cd services/model-broker
python -m mentat_broker.server --root ../.. --check
python -m unittest discover -s tests
python -m mentat_broker.server --root ../..
```

## Safety contract

The broker never launches paid compute merely because a model asked for it. A pending decision must be approved by the local user. Reuse is automatic only inside an already approved session and within the configured time and cost caps.
