# Verification

See the [consolidated project documentation](docs/documentation.md) and [tutorial](docs/tutorial.md) for the feature overview and end-to-end workflows.

Run the test suite with pytest supplied by `uv`:

```sh
uv run --no-project --with pytest --python .venv/bin/python -- python -m pytest tests/ -q
```

## Demo: Remote MCP analytics

The remote Lambda endpoint is currently torn down. Restore it using step 5 of the [consolidated tutorial](docs/tutorial.md), then run this walkthrough from the repository root. The [consolidated project documentation](docs/documentation.md) summarizes the architecture and verification evidence. No source edits are needed between stages.

1. **Architecture and dataset:** Review the [ingestion and S3 dataset tutorial](docs/tutorial-001-ingestion.md) and [AWS Lambda deployment notes](docs/006-aws_lambda.md) for the data path and architecture.
2. **Terraform endpoint:** Confirm the deployed Lambda and Function URL with the [Step 7 deployment walkthrough](docs/tutorial-007-remote-mcp-client.md). From the repository root, export the endpoint from the current Terraform state:

   ```sh
   export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
   ```

3. **Configure and run the local client:** Use the Step 7 commands to install dependencies and create/edit the ignored `.env`:

   ```sh
   uv sync
   if [ ! -e .env ]; then (umask 077 && touch .env); fi
   ${EDITOR:-vi} .env
   ```

   Set `MCP_BEARER_TOKEN` and `OPENAI_API_KEY` as described in “Configure credentials locally” in the Step 7 guide (plus optional Langfuse values). The exported Terraform endpoint takes precedence over any `MCP_SERVER_URL` value in `.env`. Then run the existing single-tool query:

   ```sh
   uv run python -m client.main \
     --prompt 'For RELIANCE on 2025-01-02, report the open, close, return, VWAP, and number of bars.'
   ```

   The client discovers MCP tools at runtime; inspect its output for the model-selected tool and analytics answer. The guide also has a multi-tool query if you want to show multiple tool calls.
4. **Ground truth and invalid-symbol rejection:** Run the existing Step 8 verification command. It checks the remote result against local data, submits an invalid symbol, and correlates both calls with CloudWatch logs:

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

5. **Inspect the trace in Langfuse:** Sign in to the Langfuse project configured in `.env`, open **Traces**, and select the trace for the query you just ran. Check off each item:

   - [ ] The query trace is present.
   - [ ] The model request and response are present.
   - [ ] MCP tool inputs and results, and the final answer, are present.
   - [ ] No credentials appear in trace inputs or outputs.

6. **Inspect CloudWatch:** View recent Lambda log events in the configured AWS region:

   ```sh
   aws logs tail /aws/lambda/kite-mcp --since 1h --region ap-south-1
   ```

7. **Tear down when the demo is no longer needed:** Follow “Destroy the demo deployment and keep the dataset” in the Step 7 guide. Create and inspect a saved destroy plan, obtain explicit human approval for that exact plan, then apply it and verify the Terraform state and preserved S3 dataset. Never approve a plan that deletes S3 data or changes unexpected resources.
