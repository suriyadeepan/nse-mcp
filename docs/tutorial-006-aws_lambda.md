# Tutorial 006: Upload the processed dataset to S3

This tutorial covers the implemented dataset upload, DuckDB-to-S3 development, partition pruning (T1–T4), local ARM64 Lambda image build (T6.3), manual local RIE smoke test (T6.4), and Terraform configuration for Lambda infrastructure (T8). Applying the deployment and verifying remote MCP access are still pending.

Run these commands from the repository root. Configure AWS CLI credentials and set the bucket name in `terraform/terraform.tfvars` (or pass it as a Terraform variable). The configured identity needs permission to manage the S3 bucket and upload objects.

```sh
export AWS_REGION=ap-south-1
aws sts get-caller-identity

terraform -chdir=terraform init
terraform -chdir=terraform apply
```

Terraform provisions the bucket and uploads `data/processed/` to the configured dataset prefix. To run the uploader directly, use the values exported by Terraform:

```sh
export DATA_BUCKET="$(terraform -chdir=terraform output -raw processed_data_bucket)"
export DATASET_PREFIX="$(terraform -chdir=terraform output -raw dataset_prefix)"

uv run python scripts/upload_processed_data.py \
  --data-dir data/processed \
  --bucket "$DATA_BUCKET" \
  --prefix "$DATASET_PREFIX"
```

The uploader preserves the `interval/year/month/symbol` partition directory structure in S3.

## Query S3 locally with DuckDB

Set the trusted dataset location and select S3 as the data source. DuckDB's AWS credential chain reads the configured AWS CLI profile or other standard AWS credentials; the application does not accept credentials as tool input.

```sh
export PROCESSED_DATA_SOURCE=s3
export PROCESSED_DATA_S3_BUCKET="nse-mcp-data"
export PROCESSED_DATA_S3_PREFIX="data/processed"
export AWS_REGION=ap-south-1
# Optional when using a named AWS CLI profile:
# export AWS_PROFILE=your-profile
```

Run a partition-filtered query for RELIANCE's August 2026 one-minute data. The script reports sessions, bar count, and the month's opening-to-closing move:

```sh
uv run python -m scripts.query_s3_summary \
  --symbol RELIANCE \
  --year 2026 \
  --month 8
```

The local connection uses DuckDB's `credential_chain`, which reads AWS CLI credentials. The deployed Lambda will use that same provider with its execution-role credentials.

## Build the ARM64 Lambda container locally

Build the Python 3.14 Lambda image for ARM64 from the repository root:

```sh
LAMBDA_PLATFORM=linux/arm64 ./scripts/build_lambda.sh
```

The image is tagged `kite-mcp-lambda:local`. The script defaults to `linux/arm64`; set `LAMBDA_PLATFORM` to override the target. This step builds the image; the manual container verification is documented separately in T6.4.

The image was manually smoke-tested both directly over HTTP and through RIE. See [the T6.4 smoke-test record](006-aws_lambda-smoke-test-docu.md) for commands, expected responses, and verified results.

## Verify partition pruning

Run a filtered query for one symbol and month. It checks that returned partition values match the requested symbol, year, and month, then prints DuckDB's query plan so you can inspect the Parquet `File Filters`:

```sh
uv run python -m scripts.verify_s3_partitions \
  --symbol RELIANCE \
  --year 2026 \
  --month 8
```
