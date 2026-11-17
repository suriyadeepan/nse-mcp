# Step 6: AWS Lambda Deployment TODO

## Objective

Deploy the existing MCP server and DuckDB analytics layer to AWS Lambda using Terraform. Keep the MCP client and OpenAI agent outside Lambda.

## TODO

- [x] **T1 — Configure trusted dataset location:** Add configurable S3 bucket and dataset prefix settings to `src/server/config.py`; keep them in trusted application/deployment configuration and never derive them from user or LLM input.
- [x] **T2 — Upload the complete dataset:**
  - [x] **T2.1 — Verify AWS connectivity:** Run `aws sts get-caller-identity` to confirm that the AWS CLI can authenticate and identify the configured AWS account. Verify access to the target S3 bucket before uploading.
  - [x] **T2.2 — Upload the dataset:** Provision the S3 bucket using Terraform, then run `scripts/upload_dataset.sh` to upload `data/processed/` to the configured bucket and dataset prefix, preserving its partition structure. Confirm all 50 NIFTY50 symbols and their partition directories are present.
- [ ] **T3 — Query Parquet directly from S3:** Update `src/server/data.py` to use DuckDB `httpfs` to read Parquet objects directly from S3, authenticating with Lambda execution-role credentials; do not copy the dataset into Lambda `/tmp`.
- [ ] **T4 — Prune partition reads:** Ensure analytics queries filter by symbol, year, and month so DuckDB can prune partitions; verify symbol and date filtering returns correct results.
- [ ] **T5 — Make the server Lambda compatible:** Update `src/server/main.py` to expose the existing MCP server through Lambda-compatible ASGI handling and Streamable HTTP.
- [ ] **T6 — Build the Lambda package:** Add `requirements-lambda.txt`, `Dockerfile.lambda`, and `scripts/deploy_lambda.sh` to build/package Python 3.12 dependencies and DuckDB native libraries for the selected Lambda architecture; confirm the package builds for that runtime and architecture.
- [ ] **T7 — Provision Lambda infrastructure:** Add Terraform configuration in `terraform/main.tf` and `terraform/variables.tf` for Lambda, Function URL, and CloudWatch logging, with configurable deployment values. S3 bucket provisioning is covered by T2.
- [ ] **T8 — Apply least-privilege IAM:** Add `terraform/iam.tf` granting Lambda read-only access to the configured dataset prefix and required CloudWatch log permissions; use the execution role for S3 authentication.
- [ ] **T9 — Protect and expose the endpoint:** Validate a demo bearer token in the application for Function URL requests; reject missing or invalid tokens, and keep credentials out of source control, logs, and errors.
- [ ] **T10 — Add deployment outputs and teardown:** Add `terraform/outputs.tf` for the deployed MCP endpoint URL and `terraform/terraform.tfvars.example` for safe example settings; configure teardown to remove S3 objects so `terraform destroy` removes all demo resources.
- [ ] **T11 — Cover Lambda and HTTP behavior:** Add `tests/test_lambda.py` to verify Lambda/Streamable HTTP integration, authentication, and direct role-authenticated S3 querying without exposing credentials.
- [ ] **T12 — Verify deployment end to end:** Confirm Terraform creates infrastructure and uploads the full dataset, Lambda queries it with partition pruning, authenticated remote MCP requests work while unauthenticated requests fail, CloudWatch captures execution logs, Terraform outputs the endpoint, and destroy removes demo resources.

## Files

- `terraform/main.tf`, `terraform/variables.tf`, `terraform/outputs.tf`, `terraform/iam.tf`, `terraform/terraform.tfvars.example` — AWS infrastructure and deployment configuration.
- `scripts/upload_dataset.sh` — upload the complete processed dataset to the configured S3 bucket and prefix.
- `scripts/deploy_lambda.sh` — build and package the Lambda deployment.
- `src/server/main.py`, `src/server/config.py`, `src/server/data.py` — Lambda entry point, trusted S3 configuration, and direct S3 analytics access.
- `tests/test_lambda.py` — Lambda and HTTP integration coverage.
- `requirements-lambda.txt`, `Dockerfile.lambda` — Lambda dependencies and compatible build environment.
