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
- [ ] **T4 — Prune partition reads** — Ensure analytics queries filter by symbol, year, and month so DuckDB can prune partitions; verify symbol and date filtering returns correct results.
  - **Depends on:** T3.
- [ ] **T5 — Make the server Lambda compatible** — Update `src/server/main.py` to expose the existing MCP server through Lambda-compatible ASGI handling and Streamable HTTP.
  - **Depends on:** T3.
- [ ] **T6 — Build the Lambda package** — Add `requirements-lambda.txt`, `Dockerfile.lambda`, and `scripts/deploy_lambda.sh` to build/package Python 3.12 dependencies and DuckDB native libraries for the selected Lambda architecture; confirm the package builds for that runtime and architecture.
  - **Depends on:** T4, T5.
- [ ] **T7 — Apply least-privilege IAM** — Add `terraform/iam.tf` granting Lambda read-only access to the configured dataset prefix and required CloudWatch log permissions; use the execution role for S3 authentication.
  - **Depends on:** T1, T3.
- [ ] **T8 — Provision Lambda infrastructure** — Add Terraform configuration in `terraform/main.tf` and `terraform/variables.tf` for Lambda, Function URL, and CloudWatch logging, with configurable deployment values. S3 bucket provisioning is covered by T2.
  - **Depends on:** T6, T7.
- [ ] **T9 — Protect and expose the endpoint** — Validate a demo bearer token in the application for Function URL requests; reject missing or invalid tokens, and keep credentials out of source control, logs, and errors.
  - **Depends on:** T5, T8.
- [ ] **T10 — Add deployment outputs and teardown** — Add `terraform/outputs.tf` for the deployed MCP endpoint URL and `terraform/terraform.tfvars.example` for safe example settings; configure teardown to remove S3 objects so `terraform destroy` removes all demo resources.
  - **Depends on:** T2, T8.
- [ ] **T11 — Cover Lambda and HTTP behavior** — Add `tests/test_lambda.py` to verify Lambda/Streamable HTTP integration, authentication, and direct role-authenticated S3 querying without exposing credentials.
  - **Depends on:** T3, T4, T5, T7, T8, T9.
- [ ] **T12 — Verify deployment end to end** — Confirm Terraform creates infrastructure and uploads the full dataset, Lambda queries it with partition pruning, authenticated remote MCP requests work while unauthenticated requests fail, CloudWatch captures execution logs, Terraform outputs the endpoint, and destroy removes demo resources.
  - **Depends on:** T1–T11.

## Dependency mapping and audit

| Task | Depends on | Dependency reason |
| --- | --- | --- |
| T1 | None | Establishes trusted bucket and prefix configuration. |
| T2 | T1 | Provisions and fills the configured S3 location after AWS identity/access checks. |
| T3 | T1, T2 | Implements and locally exercises S3 reads against the configured, populated dataset; execution-role credentials are used once deployment exists. |
| T4 | T3 | Partition pruning applies to the direct S3 reader and its queries. |
| T5 | T3 | Wraps the existing server after its data path supports S3. |
| T6 | T4, T5 | Packages the finished query path and Lambda-compatible server. |
| T7 | T1, T3 | IAM must grant access to the configured prefix and support the reader's execution-role authentication. |
| T8 | T6, T7 | Lambda infrastructure needs a deployable package and its execution role. |
| T9 | T5, T8 | Application authentication is exposed through the provisioned Function URL. |
| T10 | T2, T8 | Outputs describe deployed resources; teardown must remove the uploaded objects and Lambda resources. |
| T11 | T3, T4, T5, T7, T8, T9 | Integration tests require the reader, query behavior, server, role, endpoint, and authentication. |
| T12 | T1–T11 | End-to-end verification exercises the complete deployment and teardown path. |

The audit found no circular dependency. Local DuckDB-to-S3 development happens in T3 using AWS CLI credentials, before Lambda provisioning in T8; T7 then supplies the Lambda execution role used by the deployed reader. AWS identity and bucket access are explicit prerequisites within T2. The test and end-to-end tasks depend on all components they exercise.

## Files

- `src/server/config.py` — trusted S3 bucket and dataset prefix settings (T1).
- `scripts/upload_dataset.sh`, `data/processed/` — full dataset upload and partition layout (T2).
- `src/server/config.py`, `src/server/data.py` — trusted local/S3 source selection, DuckDB `httpfs`, local AWS CLI credentials, deployed execution-role credentials, and direct S3 reads (T3).
- Existing analytics query implementation and `tests/` — partition pruning and symbol/date result verification (T4).
- `src/server/main.py` — Lambda-compatible ASGI and Streamable HTTP entry point (T5).
- `requirements-lambda.txt`, `Dockerfile.lambda`, `scripts/deploy_lambda.sh` — Lambda runtime dependencies and package build (T6).
- `terraform/iam.tf` — least-privilege Lambda S3 and CloudWatch permissions (T7).
- `terraform/main.tf`, `terraform/variables.tf` — Lambda, Function URL, CloudWatch, and configurable deployment resources (T8).
- `src/server/` authentication implementation and `terraform/main.tf` Function URL settings — bearer-token protection (T9).
- `terraform/outputs.tf`, `terraform/terraform.tfvars.example`, `terraform/` teardown configuration — endpoint output, safe example values, and resource cleanup (T10).
- `tests/test_lambda.py` — Lambda, Streamable HTTP, authentication, and role-authenticated S3 coverage (T11).
- Terraform deployment, `scripts/upload_dataset.sh`, `tests/test_lambda.py`, and AWS runtime checks — end-to-end deployment and teardown verification (T12).
