# Tutorial 006: Upload the processed dataset to S3

This tutorial covers the implemented dataset upload and DuckDB-to-S3 development steps (T1–T3). Lambda provisioning and remote MCP access are still TODOs.

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
