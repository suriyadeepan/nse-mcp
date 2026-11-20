# Step 9: Demo Preparation Journal

## T002 — Workflow evidence

Evidence combines the fresh local client run on 2026-11-20 with the previously verified Step 7 and Step 8 records. The prior results are dated and linked below; they are not presented as new runs. No credentials, endpoints, raw CloudWatch messages, or trace payloads are reproduced here.

### Fresh runtime discovery and query (2026-11-20)

The first local query attempt used the malformed `MCP_SERVER_URL` value in `.env` and failed before MCP initialization. The value is omitted. Using the endpoint from the current Terraform output, authenticated MCP discovery succeeded and returned six runtime tools: `get_bars`, `intraday_stats`, `get_price_extremes`, `get_volume_stats`, `compute_indicators`, and `compare_symbols`. No tool catalogue was hardcoded in the client.

The client was then run with the Terraform endpoint exported into the shell:

```sh
export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
uv run python -m client.main \
  --prompt 'For RELIANCE on 2025-01-02, report the open, close, return, VWAP, and number of bars.'
```

Sanitized output:

```text
Open: ₹1221.25
Close: ₹1240.80
Return: ₹19.55 (1.60%)
VWAP: ₹1234.29
Number of bars: 375
```

The matching Step 7 single-tool run records OpenAI selection of `intraday_stats` and the same rounded analytics result. Its Langfuse inspection recorded a complete four-observation trace with the query, model exchange, MCP tool input/result, and final answer; the configured endpoint and credentials were absent from trace inputs and outputs. See [Step 7 live verification](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19). On 2026-11-20, the user also manually inspected the current query trace in Langfuse and confirmed that all README checklist items passed.

### Evidence map for the demo sequence

| Stage | Evidence and date | Status |
| --- | --- | --- |
| Architecture and S3 dataset | [Ingestion tutorial](tutorial-001-ingestion.md) and the verified data/deployment context in [Step 7 journal](007-remote-mcp-client.md) | Prior documentation and implementation evidence |
| Terraform Lambda and Function URL | [Step 7 deployment and live verification](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19) | Prior verified deployment; current plan/state review is tracked separately under T003 |
| Runtime MCP tool discovery | Six tools returned from the Terraform endpoint | Fresh live observation, 2026-11-20 |
| Natural-language query and model tool selection | Fresh query output above; `intraday_stats` selection recorded in the matching [Step 7 trace evidence](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19) | Fresh query; selection and trace inspection reused from prior verified run |
| Remote analytics and ground-truth comparison | [Step 8 live verification](008-independent-analytics-verification.md) compares remote INFY results with independent local PyArrow results | Prior live verification, PASS, 2026-11-19 |
| Invalid-symbol rejection | [Step 8 live verification](008-independent-analytics-verification.md) records clean rejection of `__KITE_INVALID_SYMBOL__` | Prior live verification, PASS, 2026-11-19 |
| Langfuse trace and CloudWatch invocation | [Step 7 Langfuse trace inspection](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19) and [Step 8 correlated CloudWatch evidence](008-independent-analytics-verification.md) | Prior invocation correlation PASS, 2026-11-19; user manually confirmed current trace checklist PASS, 2026-11-20 |
| Terraform teardown | The saved-plan, review, approval, apply, and preservation procedure is in the [Step 7 teardown guide](tutorial-007-remote-mcp-client.md#destroy-the-demo-deployment-and-keep-the-dataset) and the [README demo sequence](../README.md#demo-remote-mcp-analytics) | Procedure documented; teardown not run, pending T003 review and explicit approval under T004 |

### Verification record

- Automated tests: none run for T002; this task captures and reuses evidence and adds no application or test changes.
- Live verification: authenticated MCP discovery and the natural-language client query passed on 2026-11-20. Step 8 analytics, invalid-symbol, and CloudWatch checks are reused from their recorded 2026-11-19 pass.
- Langfuse: prior complete traces are verified in Step 7; the user manually inspected the current query trace in the browser on 2026-11-20 and confirmed all checklist items passed.
- Teardown: not run. It remains subject to the saved-plan review and explicit approval required by T003/T004.
