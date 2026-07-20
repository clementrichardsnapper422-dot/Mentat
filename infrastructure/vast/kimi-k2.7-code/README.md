# Kimi K2.7 Code on Vast.ai

This profile serves `moonshotai/Kimi-K2.7-Code` remotely while Mentat/OpenClaw remains on the operator's local PC.

```text
Local PC: Mentat gateway, tools, memory, approvals
    -> HTTPS OpenAI-compatible request
Vast.ai Serverless endpoint
    -> one 8-GPU H200 worker cluster
    -> vLLM
    -> Kimi K2.7 Code
```

## Why the profile uses one worker

A worker is already an entire 8-GPU cluster. `max_workers` is therefore set to `1`; allowing eight workers would mean allowing eight separate 8-GPU clusters.

The committed policy caps marketplace offers at `$32/hour` for the whole worker instance and permits a maximum four-hour session. Review `endpoint.json` before every deployment.

## Prerequisites

1. A Vast.ai account with sufficient credit.
2. A scoped Vast API key stored locally as `VAST_API_KEY`.
3. A Hugging Face read token stored in Vast account environment variables as `HF_TOKEN`.
4. The hash of Vast's official **vLLM (Serverless)** template.
5. Access to a verified offer containing eight H200 GPUs on one host.

Do not put API keys or Hugging Face tokens in this repository.

## Model runtime

The profile passes these required Kimi options through `VLLM_ARGS`:

```text
--tensor-parallel-size 8
--mm-encoder-tp-mode data
--trust-remote-code
--enable-auto-tool-choice
--tool-call-parser kimi_k2
--reasoning-parser kimi_k2
--served-model-name moonshotai/Kimi-K2.7-Code
--max-model-len 262144
--gpu-memory-utilization 0.90
```

Moonshot's deployment guidance verifies Kimi K2.7 Code on one H200 node with tensor parallelism 8. The `kimi_k2` tool-call and reasoning parsers are required.

## Review the planned cost

The CLI refuses estimates outside the committed policy:

```bash
python scripts/mentat/vast_endpoint.py estimate \
  --hourly-price 28 \
  --hours 2
```

## Create the endpoint

Find the official serverless vLLM template in Vast and copy its template hash. Then:

```bash
export VAST_API_KEY="set-locally"
export VAST_TEMPLATE_HASH="official-vllm-template-hash"

python scripts/mentat/vast_endpoint.py create \
  --accept-test-worker-cost
```

Vast may launch a full test worker to benchmark the workergroup. For this profile, that test worker is the complete 8×H200 cluster. The explicit acknowledgement flag is intentional.

The CLI stores only IDs and non-secret endpoint metadata in:

```text
~/.config/mentat/vast-endpoint.json
```

The state file is created with owner-only permissions.

## Start a work session

Keep one worker ready:

```bash
python scripts/mentat/vast_endpoint.py warm
```

Inspect endpoint and workergroup state:

```bash
python scripts/mentat/vast_endpoint.py status
```

Test the Vast endpoint directly:

```bash
python scripts/mentat/vast_endpoint.py test
```

Print the local environment needed by Mentat:

```bash
python scripts/mentat/vast_endpoint.py print-env
```

Then run the printed commands, ending with:

```bash
bash scripts/mentat/launch.sh
```

## End a work session

Allow the endpoint to scale to zero:

```bash
python scripts/mentat/vast_endpoint.py cool
```

`cool` sets the warm-worker floor to zero. A busy worker may remain active until Vast's autoscaler considers it idle. Storage or stopped-worker charges may still apply.

Completely remove the endpoint and its workergroup:

```bash
python scripts/mentat/vast_endpoint.py destroy --confirm
```

## Current limitations

Vast's OpenAI-compatible Serverless proxy supports text chat/completions and streaming. It does not currently proxy image, audio, embedding, or image-generation requests. Tool calling is supported by compatible vLLM models, but `parallel_tool_calls` is not supported.

For Kimi vision later, Mentat will need a compatible direct vLLM/SGLang endpoint instead of relying only on the Serverless OpenAI proxy.

## References

- Vast Serverless OpenAI-compatible API: https://docs.vast.ai/guides/serverless/openai-compatible-api
- Vast vLLM Serverless template: https://docs.vast.ai/guides/serverless/vllm
- Vast endpoint API: https://docs.vast.ai/api-reference/serverless/create-endpoint
- Vast workergroup API: https://docs.vast.ai/api-reference/serverless/create-workergroup
- Kimi K2.7 Code deployment guide: https://huggingface.co/moonshotai/Kimi-K2.7-Code/blob/main/docs/deploy_guidance.md
