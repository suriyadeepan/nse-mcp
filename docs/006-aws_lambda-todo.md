# Step 6: AWS Lambda Deployment TODO

## Objective

Deploy the existing MCP server and DuckDB analytics layer to AWS Lambda using Terraform. Keep the MCP client and OpenAI agent outside Lambda.

## TODO

- [x] **T1 — Configure the trusted dataset location** — Add configurable S3 bucket and dataset prefix settings to `src/server/config.py`. Keep them in trusted application/deployment configuration and never derive them from user or LLM input.
  - **Depends on:** None (initial setup).
- [x] **T2 — Verify AWS access and upload the complete dataset** — Run `aws sts get-caller-identity` to confirm the AWS CLI can authenticate and identify the configured AWS account. Verify access to the target S3 bucket. Provision the bucket using Terraform, then run `scripts/upload_dataset.sh` to upload `data/processed/` to the configured bucket and dataset prefix, preserving its partition structure. Confirm all 50 NIFTY50 symbols and their partition directories are present.
  - **Depends on:** T1.
- [x] **T3 — Read Parquet directly from S3 with DuckDB** — Update `src/server/data.py` to use DuckDB `httpfs` to read Parquet objects directly from S3; do not copy the dataset into Lambda `/tmp`. Select local or S3 data through trusted `PROCESSED_DATA_SOURCE` configuration. Support local development with AWS CLI credentials before Lambda is provisioned. After deployment, authenticate S3 reads with the Lambda execution-role credentials.
  - **Depends on:** T1, T2.
- [x] **T4 — Prune partition reads** — Ensure analytics queries filter by symbol, year, and month so DuckDB can prune partitions; verify symbol and date filtering returns correct results with `scripts/verify_s3_partitions.py` and inspect DuckDB's file filters.
  - **Depends on:** T3.
- [x] **T5.1 — Implement ASGI support** — Update `src/server/main.py` to expose the existing MCP server as an ASGI application compatible with Lambda. `app` is the ASGI application entry point created from `mcp.streamable_http_app()`.
  - **Depends on:** T3.
- [x] **T5.2 — Implement Streamable HTTP** — Configure the MCP server in `src/server/main.py` to support Streamable HTTP transport at `/mcp` for remote MCP clients.
  - **Depends on:** T5.1.
- [x] **T5.3 — Test ASGI and MCP integration** — Add tests verifying ASGI HTTP responses, MCP initialization, tool discovery, and tool execution over Streamable HTTP in `tests/test_http.py`.

  - **Depends on:** T5.1, T5.2.
- [x] **T6.1 — Configure Lambda dependencies** — Create `requirements-lambda.txt` with Python 3.14-compatible dependencies, including DuckDB and its required libraries.
  - **Depends on:** T3, T4, T5.1, T5.2.
- [x] **T6.2 — Create Lambda Docker image** — Create `Dockerfile.lambda` to build the application with Python 3.14 and compatible DuckDB native libraries for the selected Lambda architecture.
  - **Depends on:** T6.1, T5.3.
- [x] **T6.3 — Build Lambda container** — Create `scripts/build_lambda.sh` to build the Docker image locally for ARM64 (`linux/arm64`).
  - **Depends on:** T6.1, T6.2.
- [x] **T6.4 — Smoke-test Lambda container locally** — Manually verified successful startup and MCP initialization through an RIE invocation using the ARM64 (`linux/arm64`) image. Direct HTTP testing also verified MCP tool discovery and a `compare_symbols` call against the S3-backed dataset. See [the smoke-test record](006-aws_lambda-smoke-test-docu.md). No AWS deployment required.

  - **Depends on:** T5.3, T6.3.
- [x] **T7 — Give Lambda only the AWS permissions it needs (IAM)** — Add `terraform/iam.tf` with a Lambda execution role, which is like a limited work badge the function uses when it runs. Let it read the dataset files under the configured S3 prefix and write its logs to CloudWatch. Keep these permissions scoped to that dataset and those logs; Lambda must not need saved AWS access keys. The application uses the role automatically to access S3. Verify the trust policy and permission scope with `terraform/iam.tftest.hcl`.
  - **Depends on:** T1, T3.
- [x] **T8 — Provision Lambda infrastructure** — Add Terraform configuration in `terraform/main.tf` and `terraform/variables.tf` for an ARM64 container-image Lambda, Function URL, and retained CloudWatch log group. Configure the ECR image URI, function name, memory, timeout, and log retention; attach `aws_iam_role.lambda_execution` and pass the S3 dataset settings to the application. The Function URL allows requests through so T9 can enforce bearer authentication in the app. Verify the deployment plan with `terraform/main.tftest.hcl`. This provisions infrastructure in code; applying it to AWS remains part of end-to-end deployment verification.
  - **Depends on:** T6.4, T7.
- [x] **T9 — Protect and expose the endpoint** — Require a configured bearer token for HTTP requests, reject missing or invalid tokens without echoing them, and pass the token to Lambda as a sensitive Terraform input. Verify configured, missing, malformed, and incorrect token behavior in `tests/test_auth.py`.
  - **Depends on:** T5.1, T5.2, T8.
- [x] **T10 — Add deployment outputs and teardown** — Output the MCP endpoint URL and provide safe example settings. Terraform removes uploaded objects under the configured dataset prefix during destroy; see [T10 deployment notes](006-aws_lambda-T10-docu.md).
  - **Depends on:** T2, T8.
- [x] **T11 — Cover Lambda and HTTP behavior** — Verify authenticated Streamable HTTP tool execution, rejected unauthenticated requests, and S3 query configuration through the execution-role credential chain without static keys; see [T11 test record](006-aws_lambda-T11-docu.md).
  - **Depends on:** T3, T4, T5.1, T5.2, T5.3, T7, T8, T9.
- [ ] **T12 — Verify deployment end to end** — Confirm Terraform creates infrastructure and uploads the full dataset, Lambda queries it with partition pruning, authenticated remote MCP requests work while unauthenticated requests fail, CloudWatch captures execution logs, Terraform outputs the endpoint, and destroy removes demo resources.
  - **Depends on:** T1–T4, T5.1–T5.3, T6.1–T6.4, T7–T11.

## Dependency mapping and audit

| Task | Depends on | Dependency reason |
| --- | --- | --- |
| T1 | None | Establishes trusted bucket and prefix configuration. |
| T2 | T1 | Provisions and fills the configured S3 location after AWS identity/access checks. |
| T3 | T1, T2 | Implements and locally exercises S3 reads against the configured, populated dataset; execution-role credentials are used once deployment exists. |
| T4 | T3 | Partition pruning applies to the direct S3 reader; the verification script checks requested partition values and exposes DuckDB's file filters. |
| T5.1 | T3 | Exposes the existing server through ASGI after the S3 data path is available. |
| T5.2 | T5.1 | Adds remote Streamable HTTP transport to the ASGI server. |
| T5.3 | T5.1, T5.2 | Verifies the ASGI and MCP behavior before packaging or deployment. |
| T6.1 | T3, T4, T5.1, T5.2 | Defines dependencies for the S3 query path and ASGI/Streamable HTTP server. |
| T6.2 | T6.1, T5.3 | Builds the application image after dependencies and HTTP integration are defined. |
| T6.3 | T6.1, T6.2 | Builds the local ARM64 Lambda container using the configured dependencies and image definition. |
| T6.4 | T5.3, T6.3 | Uses RIE to verify that the ARM64 container starts and serves MCP requests locally. |
| T7 | T1, T3 | The dataset location and S3 reader determine which data Lambda needs to read; the execution role gives it that access without stored keys. |
| T8 | T6.4, T7 | Lambda infrastructure needs a locally tested container and its execution role. |
| T9 | T5.1, T5.2, T8 | Application authentication protects the Streamable HTTP application exposed through the Function URL. |
| T10 | T2, T8 | Outputs describe deployed resources; teardown must remove the uploaded objects and Lambda resources. |
| T11 | T3, T4, T5.1, T5.2, T5.3, T7, T8, T9 | Lambda integration tests require the reader, partitioned queries, tested HTTP server, role, endpoint, and authentication. |
| T12 | T1–T4, T5.1–T5.3, T6.1–T6.4, T7–T11 | End-to-end verification exercises the complete deployment and teardown path. |

The audit found no circular dependency. Local DuckDB-to-S3 development happens in T3 using AWS CLI credentials, before Lambda provisioning in T8; T7 then supplies the Lambda execution role used by the deployed reader. AWS identity and bucket access are explicit prerequisites within T2. The test and end-to-end tasks depend on all components they exercise.

## Files

- `src/server/config.py` — trusted S3 bucket and dataset prefix settings (T1).
- `scripts/upload_dataset.sh`, `data/processed/` — full dataset upload and partition layout (T2).
- `src/server/config.py`, `src/server/data.py` — trusted local/S3 source selection, DuckDB `httpfs`, local AWS CLI credentials, deployed execution-role credentials, and direct S3 reads (T3).
- Existing analytics query implementation and `scripts/verify_s3_partitions.py` — partition pruning and symbol/date result verification (T4).
- `src/server/main.py` — Lambda-compatible ASGI application (T5.1) and Streamable HTTP transport (T5.2).
- `tests/test_http.py` (preferred) or `tests/test_lambda.py` — ASGI responses, MCP initialization, tool discovery, and Streamable HTTP tool execution (T5.3).
- `requirements-lambda.txt` — Python 3.14-compatible Lambda dependencies, including DuckDB and required libraries (T6.1).
- `Dockerfile.lambda` — Python 3.14 application image with DuckDB native libraries for the selected architecture (T6.2).
- `scripts/build_lambda.sh`, `.dockerignore`, `Dockerfile.lambda` — local ARM64 Lambda container build with a focused Docker build context (T6.3).
- `docs/006-aws_lambda-smoke-test-docu.md` — manual local ARM64 container and RIE verification record (T6.4).
- `tests/test_lambda.py` — Lambda/HTTP/authentication and role-authenticated S3 coverage (T11).
- `terraform/iam.tf` — least-privilege Lambda S3 and CloudWatch permissions (T7).
- `terraform/iam.tftest.hcl` — mocked-provider checks for the execution role, S3 scope, and CloudWatch log scope (T7).
- `terraform/main.tf`, `terraform/variables.tf`, `terraform/main.tftest.hcl` — Lambda, Function URL, CloudWatch, configurable deployment resources, and mocked-plan coverage (T8).
- `src/server/auth.py`, `tests/test_auth.py`, `terraform/main.tf`, and `terraform/variables.tf` — bearer-token protection and sensitive runtime configuration (T9).
- `terraform/outputs.tf`, `terraform/terraform.tfvars.example`, `terraform/` teardown configuration — endpoint output, safe example values, and resource cleanup (T10).
- `docs/006-aws_lambda-T10-docu.md` — endpoint output, example configuration, cleanup process, and validation results (T10).
- `tests/test_lambda.py`, `docs/006-aws_lambda-T11-docu.md` — authenticated Lambda HTTP/tool integration, role credential-chain query configuration, and test results (T11).
- Terraform deployment, `scripts/upload_dataset.sh`, `tests/test_http.py`, `tests/test_lambda.py`, and AWS runtime checks — end-to-end deployment and teardown verification (T12).
