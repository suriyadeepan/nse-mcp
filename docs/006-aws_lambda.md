# AWS Lambda MCP deployment

This guide combines the implementation notes, setup steps, terminal walkthrough, validation results, and remaining work for the AWS Lambda MCP feature.

## Current deployment

- Region: `ap-south-1`
- Lambda: `kite-mcp`, ARM64 container, 2,048 MB, 300-second timeout
- MCP endpoint: `https://onznjliuy5yjpzwozpjrjepwa40nzdhe.lambda-url.ap-south-1.on.aws/mcp`
- Dataset: `s3://nse-mcp-data/data/processed`
- Current image: `025232685609.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp@sha256:2e05ee9f1203542058a1dcf76c528b7afe1e9367ec248e9510854993549b18cd`
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

MCP DNS rebinding protection allows the deployed Function URL hostname and narrow localhost development patterns. It does not allow arbitrary hosts. This fixed HTTP 421 `Invalid Host header` for authenticated requests while preserving rejection of an unrelated host.

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

## Validation record

- Host allowlist tests: `uv run --with pytest pytest tests/test_http.py tests/test_lambda.py` — 5 passed.
- Previous application validation: `uv run --with pytest pytest tests/test_lambda.py tests/test_http.py tests/test_auth.py tests/test_s3_data.py` — 18 passed.
- Terraform formatting, validation, and mocked tests passed during implementation. The image digest update plan showed only an in-place `aws_lambda_function.mcp.image_uri` change: 0 added, 1 changed, 0 destroyed.
