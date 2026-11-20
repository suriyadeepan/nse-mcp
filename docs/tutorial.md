# Project tutorial

Run commands from the repository root. Use `uv` for Python commands. The remote AWS demo was torn down; local workflows work independently, while remote steps require an operator-restored deployment.

## 1. Set up data

Install dependencies and ingest the raw files listed in `data/index/NIFTY50.csv`:

```sh
uv sync
uv run python scripts/ingestion.py
```

Ingestion leaves raw data unchanged, writes validated Parquet to `data/processed/`, and reports rejected rows and file errors. If the processed dataset is already present, skip ingestion.

## 2. Query analytics

Check available symbols, then use one found in your dataset and a date range that exists:

```sh
uv run python -c 'from server.data import list_symbols; from server.config import ANALYTICS_CONFIG; print(sorted(list_symbols(ANALYTICS_CONFIG.processed_data_dir)))'
uv run examples/002-analytics/get_bars.py --symbol RELIANCE --start 2025-03-03T09:15:00+05:30 --end 2025-03-03T10:00:00+05:30 --limit 10
uv run examples/002-analytics/intraday_stats.py --symbol RELIANCE --date 2025-03-03
uv run examples/002-analytics/price_extremes.py --symbol RELIANCE --start 2025-03-01T00:00:00+05:30 --end 2025-03-07T23:59:59+05:30
uv run examples/002-analytics/volume_stats.py --symbol RELIANCE --start 2025-03-03T09:15:00+05:30 --end 2025-03-03T15:30:00+05:30 --bucket hourly
uv run examples/002-analytics/compute_indicators.py --symbol RELIANCE --start 2025-03-03T09:15:00+05:30 --end 2025-03-10T15:30:00+05:30
uv run examples/002-analytics/compare_symbols.py --symbols RELIANCE TCS INFY --start 2025-03-01T00:00:00+05:30 --end 2025-03-31T23:59:59+05:30 --interval daily
```

Replace sample symbols and dates with available data. Ranges are inclusive; timestamps accept ISO-8601 offsets. Session dates and volume buckets use India time.

## 3. Run the local MCP server and client

In one terminal, start the Streamable HTTP server:

```sh
uv run uvicorn server.main:app --host 127.0.0.1 --port 8000
```

In another terminal, launch MCP Inspector if you want to inspect the server tools:

```sh
npx -y @modelcontextprotocol/inspector
```

Open the local Inspector page and connect with the Streamable HTTP transport to `http://127.0.0.1:8000/mcp`. Then set the OpenAI key:

```sh
read -r -s -p 'OpenAI API key: ' OPENAI_API_KEY
export OPENAI_API_KEY
printf '\n'
```

Ask a question using symbols and dates in your local data:

```sh
uv run python -m client.main --server http://127.0.0.1:8000/mcp \
  --prompt 'Summarize RELIANCE on January 15, 2025, including open, close, return, VWAP, and number of bars.'
```

The client discovers MCP tools at runtime and asks the model to select and call them. Try a request needing multiple analytics results to see multiple tool calls. When finished, stop the server and run `unset OPENAI_API_KEY`.

## 4. Inspect Langfuse traces (optional)

Add `OPENAI_API_KEY`, `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, and the project `LANGFUSE_HOST` to a private root `.env`; never commit or share it. Run a client query as above. In Langfuse, open **Traces** and inspect the query, model exchange, MCP tool inputs/results and final answer. Confirm credentials are absent before sharing a trace.

## 5. Restore the remote demo (deployment operator)

The endpoint is currently torn down. Restoration requires AWS/ECR access and a protected `terraform/terraform.tfvars`. Build and publish an ARM64 image, then pin the digest printed by the push script in `lambda_image_uri`:

```sh
./scripts/build_lambda.sh
docker image inspect --format '{{.Os}}/{{.Architecture}}' kite-mcp-lambda:local
./scripts/deploy_lambda.sh
if [ ! -e terraform/terraform.tfvars ]; then cp terraform/terraform.tfvars.example terraform/terraform.tfvars; fi
```

Set the bucket, image digest, exact Function URL hostname, and a random bearer token of at least 32 characters in the ignored tfvars file. Protect the file and Terraform state because they contain the token. Initialize and save a plan; inspect it and obtain explicit approval before applying:

```sh
terraform -chdir=terraform init
terraform -chdir=terraform plan -out=/tmp/kite-mcp-restore.tfplan
terraform -chdir=terraform show -json /tmp/kite-mcp-restore.tfplan \
  | jq -r '[.resource_changes[] | {address, actions: .change.actions}]'
```

Apply only that reviewed plan after explicit approval with `terraform -chdir=terraform apply /tmp/kite-mcp-restore.tfplan`, then obtain the endpoint from `terraform -chdir=terraform output -raw mcp_endpoint_url`. Do not upload or modify the existing dataset as part of restoration.

## 6. Verify a restored remote deployment

This section requires an available endpoint, its bearer token, local verification data, and AWS log access. Configure `MCP_SERVER_URL`, `MCP_BEARER_TOKEN`, and optional Langfuse values in the ignored `.env`. The token must not be passed as a command-line argument.

Run the independent analytics, invalid-symbol, and CloudWatch correlation check:

```sh
(
  set -eu
  set -a
  . ./.env
  set +a
  export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
  export MCP_LAMBDA_LOG_GROUP=/aws/lambda/kite-mcp
  export AWS_REGION=ap-south-1 AWS_DEFAULT_REGION=ap-south-1
  uv run python scripts/verify_remote_analytics.py
)
```

Run a remote natural-language query through the authenticated client:

```sh
uv run python -m client.main \
  --prompt 'For RELIANCE on 2025-01-02, report the open, close, return, VWAP, and number of bars.'
```

For the full portfolio sequence, inspect the architecture and S3 dataset, confirm the Lambda Function URL, compare remote results with local ground truth, check invalid-symbol rejection, and review the Langfuse trace. Inspect recent Lambda logs with:

```sh
aws logs tail /aws/lambda/kite-mcp --since 1h --region ap-south-1
```

## 7. Safely tear down the demo

From the repository root, create and inspect a saved destroy plan using the protected deployment variables:

```sh
terraform -chdir=terraform plan -destroy -out=/tmp/kite-mcp-destroy.tfplan
terraform -chdir=terraform show -json /tmp/kite-mcp-destroy.tfplan \
  | jq -r '[.resource_changes[] | {address, actions: .change.actions}]'
```

Expected changes are only the seven disposable Lambda, Function URL, invoke permission, IAM and log group resources. Do not proceed if the plan deletes S3 data or includes unexpected actions. A person authorized to remove the deployment must review and explicitly approve that exact plan before applying:

```sh
terraform -chdir=terraform apply /tmp/kite-mcp-destroy.tfplan
```

Afterward, verify Terraform state and AWS resource absence, and compare the read-only `data/processed/` S3 inventory with its pre-destroy baseline. The targeted AWS commands should report the Lambda and role absent and no matching log group; the S3 count/byte result should remain 2,781 / 326,546,421:

```sh
terraform -chdir=terraform state list
aws lambda get-function-configuration --function-name kite-mcp --region ap-south-1
aws lambda get-function-url-config --function-name kite-mcp --region ap-south-1
aws iam get-role --role-name kite-mcp-execution
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/kite-mcp --region ap-south-1
aws s3api list-objects-v2 --bucket nse-mcp-data --prefix data/processed/ \
  --query '[length(Contents[]),sum(Contents[].Size)]' --output json
```

The targeted AWS commands return not-found responses for removed resources; the log-group command returns an empty list. Remove the local plan after verification:

```sh
rm /tmp/kite-mcp-destroy.tfplan
```

Never run dataset upload or cleanup as part of teardown. See [consolidated feature documentation](documentation.md) for architecture, interfaces, constraints and evidence.
