# AWS Lambda MCP deployment

This guide combines the implementation notes, setup steps, terminal walkthrough, validation results, and remaining work for the AWS Lambda MCP feature.

## Current deployment

- Region: `ap-south-1`
- Lambda: `kite-mcp`, ARM64 container, 2,048 MB, 300-second timeout
- MCP endpoint: `https://cyrosvlkokbjjafuulwooidvw40xopcd.lambda-url.ap-south-1.on.aws/mcp`
- Dataset: `s3://nse-mcp-data/data/processed`
- Current image: `025232685609.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp@sha256:2c3407c4fcf2f711122132cb4ef961fd76eb8fa5aeb197eb83dcbf89c9e12aa1`
- Dataset objects are existing read-only input to Lambda. Terraform detaches the bucket and public access block from its state and has no upload or object-deletion provisioner. Do not upload the dataset again unless an upload is explicitly intended.

## Try MCP from a terminal

These commands were run successfully against the deployed endpoint. They require Bash, `curl`, `jq`, Terraform outputs, and the bearer token. The token is entered without echo and is sent to curl through its standard input configuration, rather than placed in shell history or command arguments.

```bash
export MCP_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
read -r -s -p 'Bearer token: ' MCP_TOKEN
printf '\n'

mcp_post() {
  local json="$1" session_id="${2:-}"
  local session_header=()
  [[ -n "$session_id" ]] && session_header=(-H "MCP-Session-Id: $session_id")
  printf 'header = "Authorization: Bearer %s"\n' "$MCP_TOKEN" |
    curl -sS --config - -D /tmp/kite-mcp-headers \
      -H 'Content-Type: application/json' \
      -H 'Accept: application/json, text/event-stream' \
      -H 'MCP-Protocol-Version: 2025-03-26' \
      "${session_header[@]}" \
      --data "$json" "$MCP_URL"
}
```

Initialize a session and save its ID:

```bash
initialize='{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-03-26","capabilities":{},"clientInfo":{"name":"terminal","version":"1.0"}}}'
response="$(mcp_post "$initialize")"
SESSION_ID="$(awk 'tolower($1)=="mcp-session-id:" {gsub("\r", "", $2); print $2}' /tmp/kite-mcp-headers)"
printf '%s\n' "$response" | sed -n 's/^data: //p' | jq '.result.serverInfo'
```

List the tools and query a few RELIANCE bars from S3:

```bash
response="$(mcp_post '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' "$SESSION_ID")"
printf '%s\n' "$response" | sed -n 's/^data: //p' | jq -r '.result.tools[].name'

query='{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"get_bars","arguments":{"arguments":{"symbol":"RELIANCE","start_datetime":"2025-01-01T00:00:00+05:30","end_datetime":"2025-01-03T23:59:59+05:30","limit":10}}}}'
response="$(mcp_post "$query" "$SESSION_ID")"
printf '%s\n' "$response" | sed -n 's/^data: //p' | jq -r '.result.content[0].text' | jq '{returned_count, bars: [.bars[] | {timestamp, close}]}'
unset MCP_TOKEN SESSION_ID
```

Verified live results: unauthenticated requests return HTTP 401; authenticated initialize and tools/list return HTTP 200; the query returns Parquet-backed data. The terminal commands above have also been run successfully.

## Build and publish the Lambda image

Build a single-platform ARM64 image locally:

```bash
./scripts/build_lambda.sh
docker image inspect --format '{{.Os}}/{{.Architecture}}' kite-mcp-lambda:local
```

The expected architecture is `linux/arm64`. The script uses `docker buildx build --platform linux/arm64 --load --provenance=false --sbom=false` and preserves the local tag `kite-mcp-lambda:local`. These flags avoid an OCI image index, which Lambda cannot deploy. `.dockerignore` keeps local data, tests, Terraform, and documentation out of the image context.

Publish the image to ECR:

```bash
./scripts/deploy_lambda.sh
```

This runs the push workflow, which checks the local architecture, logs Docker into ECR using the AWS CLI credential chain, pushes the image, and prints its digest. The IAM identity needs ECR repository read/create, registry authorization, layer upload, `PutImage`, and image inspection permissions. The permission set used for this deployment was named `ECRPushAccess`; its supplied policy used `Resource: "*"`.

### Pin deployments to an image digest

Terraform configures `aws_lambda_function.mcp.image_uri` from `lambda_image_uri`. Reusing a mutable `:latest` tag does not change that string, so Terraform can report no changes even when ECR's tag points to a new image. Lambda resolves tags to a digest at deployment and does not follow later tag changes automatically.

After each push, set `lambda_image_uri` in the ignored local `terraform/terraform.tfvars` to the exact digest URI printed by the push script, then inspect the plan:

```hcl
lambda_image_uri = "025232685609.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp@sha256:REPLACE_WITH_PUSHED_DIGEST"
```

The intended plan for an image release is an in-place Lambda image update only. Review it before applying. For this deployment, the digest pinned was `sha256:2e05ee9f1203542058a1dcf76c528b7afe1e9367ec248e9510854993549b18cd`.

## Terraform settings and safety

1. Copy `terraform/terraform.tfvars.example` to the Git-ignored `terraform/terraform.tfvars`.
2. Set region `ap-south-1`, bucket `nse-mcp-data`, prefix `data/processed`, the digest-pinned image URI, and a unique random bearer token of at least 32 characters.
3. Keep the bearer token only in a protected local or secure Terraform input. It is a sensitive variable, but Terraform state and Lambda configuration contain it; protect state access.
4. Initialize, plan, review resource actions, then apply only when the plan is expected.

Terraform provisions the ARM64 image Lambda, execution role, scoped runtime policy, Function URL, invoke permissions, and a retained CloudWatch log group. The Function URL has `AuthType=NONE` so requests reach application middleware, which requires `Authorization: Bearer …`. Terraform keeps the `lambda:InvokeFunctionUrl` permission and a second URL-scoped `lambda:InvokeFunction` permission (`invoked_via_function_url = true`).

MCP DNS rebinding protection reads the exact deployed Function URL hostname from `MCP_FUNCTION_URL_HOST` and also allows narrow localhost development patterns. Terraform supplies `lambda_function_url_host` as a Lambda environment setting; arbitrary hosts remain rejected. Set this value to the current Function URL hostname when provisioning or restoring the Function URL.

The existing S3 bucket and public access block are detached from Terraform state using `removed` blocks with `destroy = false`; the legacy destroy-time upload cleanup provisioner was removed. Dataset uploads remain a separate explicit operation using `scripts/upload_dataset.sh`.

## Local image smoke test

The ARM64 image was tested directly over HTTP and with the AWS Lambda Runtime Interface Emulator (RIE). Both paths started Uvicorn and initialized MCP; direct HTTP testing also listed tools and successfully called `compare_symbols` against the S3-backed dataset. RIE testing used a valid API Gateway HTTP API v2 event targeting `/mcp`; an earlier `{}` event was invalid and returned `null`/404. The RIE binary used was `.aws-lambda/aws-lambda-rie`.

The initial legacy Docker builder attempt failed during image export after a 1.437 GB context was reduced to 356.4 KB. Buildx was unavailable at that time, and the legacy export reported a missing content digest. The cause was not confirmed. Buildx was subsequently enabled and the ARM64 single-image build completed; the earlier error did not establish an application or dependency failure.

## Deployed verification status

T1–T11 and T12 are complete. After T12.7 smoke testing and T12.8 endpoint verification, `terraform destroy` removed the seven demo resources: Lambda, Function URL, two invoke permissions, IAM role and inline policy, and CloudWatch log group. The post-destroy AWS checks confirmed that the Lambda function, IAM role, and log group were absent and Terraform state was empty. The S3 bucket remained available with all four public access block settings enabled. The `data/processed/` prefix retained all 2,781 objects (326,546,421 bytes), matching the pre-destroy inventory. No dataset upload or deletion was performed.

T12.7 live checks:

| Check | Result |
| --- | --- |
| Unauthenticated POST to `/mcp` | HTTP 401 from bearer middleware |
| Authenticated MCP initialize | HTTP 200; session ID returned |
| Authenticated `tools/list` | HTTP 200; six tools returned |
| S3-backed `get_bars` | HTTP 200; RELIANCE Parquet data returned for 2025-01-01 through 2025-01-03 |
| CloudWatch review | Last 24 hours: 143 events, 14 authorized-request entries, 9 successful HTTP 200 requests; no bearer-token match or common credential pattern found |

The CloudWatch check was completed after `logs:FilterLogEvents` was added to the caller's permissions. That permission is for log review; it is separate from the Lambda execution role.

## Step 7 restoration (2026-11-19)

After review and explicit approval of the saved Terraform plan (`/tmp/kite-mcp-t009.tfplan`, SHA-256 `70c8a13c9efcdb5a8e4124bc3aa8fc313cea5d2e20922df416d1b2d6ed361d3c`), `terraform -chdir=terraform apply -no-color /tmp/kite-mcp-t009.tfplan` created the seven planned demo resources: the CloudWatch log group, Lambda execution role and inline policy, Lambda function, Function URL, and two Function URL invoke permissions. The final plan had 7 creates, 0 updates, and 0 deletes. No S3 resources or dataset objects were changed.

The restored Lambda is active in `ap-south-1` on ARM64, with a 300-second timeout and 2,048 MB memory. The Function URL is `https://cyrosvlkokbjjafuulwooidvw40xopcd.lambda-url.ap-south-1.on.aws/mcp`. Its AWS URL authorization type is `NONE`, with public URL invoke permissions; application bearer middleware still requires the configured token. A POST to `/mcp` without credentials returned HTTP 401, confirming network reachability and authentication enforcement. Authenticated tool discovery and S3-backed analytics are recorded separately after live client verification.

The post-apply S3 inventory returned 2,781 objects totaling 326,546,421 bytes under `data/processed/`, matching the pre-apply baseline. The restored log group is `/aws/lambda/kite-mcp` with 14-day retention. The runtime IAM policy remains scoped to `s3:ListBucket` on `nse-mcp-data` conditioned to `data/processed` and its descendants, `s3:GetObject` on `data/processed/*`, `logs:CreateLogGroup` on `/aws/lambda/kite-mcp`, and `logs:CreateLogStream` plus `logs:PutLogEvents` on its log streams. The role trust policy grants `sts:AssumeRole` to `lambda.amazonaws.com`.

## Step 7 host allowlist correction and live verification (2026-11-19)

The first authenticated attempt after restoration returned HTTP 421 `Invalid Host header`: the image still allowed the old Function URL hostname. `src/server/main.py` now derives the permitted hostname from `MCP_FUNCTION_URL_HOST`; Terraform configures it from `lambda_function_url_host`. The regression test confirms the restored hostname initializes successfully and an unrelated hostname returns 421. The corrected ARM64 image was pushed as digest `sha256:2c3407c4fcf2f711122132cb4ef961fd76eb8fa5aeb197eb83dcbf89c9e12aa1`. The reviewed Terraform plan changed only `aws_lambda_function.mcp` in place (image and host environment value): 0 added, 1 changed, 0 destroyed. No IAM, Function URL, or S3 changes were planned.

The deployment completed successfully. Authenticated runtime discovery returned all six analytics tools. The MCP client used separate authenticated discovery and execution sessions with the same endpoint and token. Live calls, all schema-valid, returned results for `get_bars`, `intraday_stats`, `get_price_extremes`, `get_volume_stats`, `compute_indicators`, and `compare_symbols`; the exact arguments and concise result values are recorded in the Step 7 journal.

Natural-language live checks returned the RELIANCE Jan 2 session open/close, 1.60% return, VWAP and 375 bars using `intraday_stats`. A second query combined `get_price_extremes` and `get_volume_stats` for RELIANCE over Jan 1–3, reporting high 1,262.05 at 2025-01-03 08:04 UTC, low 1,211.60 at 2025-01-01 04:24 UTC, and daily volumes for all three dates. Langfuse contained two complete traces (4 and 5 observations) with root inputs/answers, two model generations each, and the expected tool observations. The MCP bearer token, OpenAI API key, Langfuse secret key, and MCP endpoint were absent from trace inputs/outputs. Langfuse adds its public project identifier to SDK-generated `scope.attributes.public_key` metadata; it did not appear in the observed inputs or outputs.

## Validation record

- Host allowlist tests: `uv run --with pytest pytest tests/test_http.py tests/test_lambda.py` — 5 passed.
- Previous application validation: `uv run --with pytest pytest tests/test_lambda.py tests/test_http.py tests/test_auth.py tests/test_s3_data.py` — 18 passed.
- Terraform formatting, validation, and mocked tests passed during implementation. The image digest update plan showed only an in-place `aws_lambda_function.mcp.image_uri` change: 0 added, 1 changed, 0 destroyed.

## Step 7 endpoint restoration plan review (2026-11-19)

Read-only AWS checks confirmed that the `kite-mcp` Lambda function, `kite-mcp-execution` IAM role, and `/aws/lambda/kite-mcp` log group are absent. The local Terraform state has no managed resources. The S3 prefix `s3://nse-mcp-data/data/processed/` still contains 2,781 objects totaling 326,546,421 bytes.

`terraform -chdir=terraform plan -no-color -out=/tmp/kite-mcp-t008.tfplan` planned these seven creates: `aws_cloudwatch_log_group.lambda`, `aws_iam_role.lambda_execution`, `aws_iam_role_policy.lambda_runtime`, `aws_lambda_function.mcp`, `aws_lambda_function_url.mcp`, `aws_lambda_permission.function_url`, and `aws_lambda_permission.function_url_invoke`. There are no S3 resource changes, upload/deletion provisioners, or dataset mutations in the plan. The S3 bucket appears only as a read-only data source.

The IAM changes in that plan are:

- `aws_iam_role.lambda_execution` (`kite-mcp-execution`): trust policy allows `sts:AssumeRole` by `lambda.amazonaws.com`.
- `aws_iam_role_policy.lambda_runtime` (`kite-mcp-runtime`): `s3:ListBucket` on `arn:aws:s3:::nse-mcp-data`, restricted to `data/processed` and its descendants; `s3:GetObject` on `arn:aws:s3:::nse-mcp-data/data/processed/*`; `logs:CreateLogGroup` on `arn:aws:logs:ap-south-1:<account>:log-group:/aws/lambda/kite-mcp`; and `logs:CreateLogStream` plus `logs:PutLogEvents` on that log group’s `:log-stream:*` resources.

Verification commands: `terraform -chdir=terraform state list` (empty); `aws lambda get-function-configuration --function-name kite-mcp --region ap-south-1` (function not found); `aws iam get-role --role-name kite-mcp-execution` (role not found); `aws logs describe-log-groups --log-group-name-prefix /aws/lambda/kite-mcp --region ap-south-1` (empty); `aws s3api list-objects-v2 --bucket nse-mcp-data --prefix data/processed/ --query '[length(Contents[]),sum(Contents[].Size)]'` (2,781; 326,546,421); `terraform -chdir=terraform test` (2 passed); and the read-only Terraform plan above. The saved plan file is local under `/tmp` and is not committed. No apply was run. Human approval is required before applying this plan, including its IAM role and policy creation.
