#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
data_dir="$repo_root/data/processed"
terraform_dir="$repo_root/terraform"

: "${PROCESSED_DATA_S3_BUCKET:?Set PROCESSED_DATA_S3_BUCKET to the configured dataset bucket}"
dataset_prefix="${PROCESSED_DATA_S3_PREFIX:-data/processed}"
dataset_prefix="${dataset_prefix#/}"
dataset_prefix="${dataset_prefix%/}"

command -v aws >/dev/null || { echo "aws CLI is required" >&2; exit 1; }
command -v terraform >/dev/null || { echo "Terraform is required" >&2; exit 1; }
[[ -d "$data_dir" ]] || { echo "Dataset directory not found: $data_dir" >&2; exit 1; }

export TF_VAR_processed_data_bucket="$PROCESSED_DATA_S3_BUCKET"
export TF_VAR_dataset_prefix="$dataset_prefix"

terraform -chdir="$terraform_dir" init -input=false
terraform -chdir="$terraform_dir" apply -input=false -auto-approve \
  -target=aws_s3_bucket_public_access_block.processed_data

aws sts get-caller-identity >/dev/null
aws s3api head-bucket --bucket "$PROCESSED_DATA_S3_BUCKET"

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT
find "$data_dir" -type f -name '*.parquet' -print \
  | sed "s|^$data_dir/||" | LC_ALL=C sort > "$tmp_dir/local-objects"

[[ -s "$tmp_dir/local-objects" ]] || { echo "No Parquet files found in $data_dir" >&2; exit 1; }
awk -F/ '{ for (i = 1; i <= NF; i++) if ($i ~ /^symbol=/) { sub(/^symbol=/, "", $i); print $i } }' \
  "$tmp_dir/local-objects" | LC_ALL=C sort -u > "$tmp_dir/local-symbols"
awk -F, 'NR > 1 && $3 != "" { print $3 }' "$repo_root/data/index/NIFTY50.csv" \
  | LC_ALL=C sort -u > "$tmp_dir/expected-symbols"
symbol_count="$(wc -l < "$tmp_dir/expected-symbols" | tr -d ' ')"
[[ "$symbol_count" -eq 50 ]] || {
  echo "Expected 50 symbols in data/index/NIFTY50.csv, found $symbol_count" >&2
  exit 1
}
if ! diff -u "$tmp_dir/expected-symbols" "$tmp_dir/local-symbols"; then
  echo "Processed dataset symbol partitions do not match data/index/NIFTY50.csv" >&2
  exit 1
fi

destination="s3://$PROCESSED_DATA_S3_BUCKET"
if [[ -n "$dataset_prefix" ]]; then
  destination="$destination/$dataset_prefix"
fi
aws s3 sync "$data_dir/" "$destination/" --exclude '*.DS_Store'

if [[ -n "$dataset_prefix" ]]; then
  aws s3api list-objects-v2 --bucket "$PROCESSED_DATA_S3_BUCKET" \
    --prefix "$dataset_prefix/" --query 'Contents[].Key' --output text \
    | tr '\t' '\n' | sed "s|^$dataset_prefix/||" | LC_ALL=C sort \
    > "$tmp_dir/remote-objects"
else
  aws s3api list-objects-v2 --bucket "$PROCESSED_DATA_S3_BUCKET" \
    --query 'Contents[].Key' --output text \
    | tr '\t' '\n' | LC_ALL=C sort > "$tmp_dir/remote-objects"
fi

if ! comm -23 "$tmp_dir/local-objects" "$tmp_dir/remote-objects" > "$tmp_dir/missing"; then
  echo "Could not compare uploaded object keys" >&2
  exit 1
fi
if [[ -s "$tmp_dir/missing" ]]; then
  echo "Upload is missing partition objects:" >&2
  cat "$tmp_dir/missing" >&2
  exit 1
fi

echo "Uploaded $(wc -l < "$tmp_dir/local-objects" | tr -d ' ') Parquet objects for $symbol_count symbols to $destination"
