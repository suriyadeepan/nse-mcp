# Remote MCP analytics demo

## Context

This walkthrough demonstrates the end-to-end remote path: NSE market data in the preserved S3 dataset, analytics tools served through an authenticated AWS Lambda MCP endpoint, a local AI client that discovers and calls those tools, and independent verification through local calculations, Langfuse traces, and CloudWatch logs. It assumes the repository's existing code and processed dataset; no source edits are needed between stages.

The disposable Lambda endpoint is currently torn down. Restore it using [step 5 of the consolidated tutorial](tutorial.md) before starting. The [project documentation](documentation.md) summarizes the architecture and verification evidence. Run every command from the repository root.

Prerequisites for the remote stages include AWS access, a restored Terraform deployment, local verification data, and private credentials in `.env`. Do not commit or expose credentials. The processed S3 dataset is preserved and should remain read-only throughout this demo.

## Walkthrough

1. **Review the architecture and dataset.** Read the [ingestion and S3 dataset tutorial](tutorial-001-ingestion.md) and [AWS Lambda deployment notes](006-aws_lambda.md) for the data path and architecture.

2. **Confirm the Terraform endpoint.** Follow the [Step 7 deployment walkthrough](tutorial-007-remote-mcp-client.md) to confirm the deployed Lambda and Function URL. From the repository root, export the endpoint from Terraform state:

   ```sh
   export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
   ```

3. **Configure and run the local client.** Use the Step 7 guide to install dependencies and create or edit the ignored `.env`:

   ```sh
   uv sync
   if [ ! -e .env ]; then (umask 077 && touch .env); fi
   ${EDITOR:-vi} .env
   ```

   Set `MCP_BEARER_TOKEN` and `OPENAI_API_KEY` as described in “Configure credentials locally” in the Step 7 guide; Langfuse values are optional. The endpoint exported from Terraform takes precedence over any `MCP_SERVER_URL` in `.env`. Run the single-tool query:

   ```sh
   uv run python -m client.main \
     --prompt 'For RELIANCE on 2025-01-02, report the open, close, return, VWAP, and number of bars.'
   ```

   The client discovers MCP tools at runtime. Inspect its output for the model-selected tool and analytics answer. The Step 7 guide also includes a multi-tool query.

4. **Compare with local ground truth and check invalid-symbol handling.** The Step 8 verification command compares remote results with local data, submits an invalid symbol, and correlates both calls with CloudWatch logs:

   ```sh
   (
     set -eu
     set -a
     . ./.env
     set +a
     export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
     export MCP_LAMBDA_LOG_GROUP=/aws/lambda/kite-mcp
     export AWS_REGION=ap-south-1
     export AWS_DEFAULT_REGION="$AWS_REGION"
     uv run python scripts/verify_remote_analytics.py
   )
   ```

5. **Inspect the Langfuse trace.** Sign in to the Langfuse project configured in `.env`, open **Traces**, and select the trace for the query. Confirm:

   - [ ] The query trace is present.
   - [ ] The model request and response are present.
   - [ ] MCP tool inputs, results, and the final answer are present.
   - [ ] Credentials are absent from trace inputs and outputs.

6. **Inspect CloudWatch.** View recent Lambda log events in the configured AWS region:

   ```sh
   aws logs tail /aws/lambda/kite-mcp --since 1h --region ap-south-1
   ```

7. **Tear down the demo while keeping the dataset.** Follow “Safely tear down the demo” in the [consolidated tutorial](tutorial.md). Create and inspect a saved destroy plan, obtain explicit human approval for that exact plan, then apply it and verify Terraform state, AWS resource absence, and the preserved S3 dataset. Reject any plan that deletes S3 data or includes unexpected resource actions.
