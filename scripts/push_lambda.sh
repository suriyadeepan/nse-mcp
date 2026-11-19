#!/usr/bin/env bash
set -euo pipefail

image_name="${LAMBDA_IMAGE:-kite-mcp-lambda:local}"
region="${AWS_REGION:-ap-south-1}"
repository="${ECR_REPOSITORY:-kite-mcp}"
tag="${ECR_TAG:-latest}"

for command_name in aws docker; do
  command -v "$command_name" >/dev/null || {
    echo "$command_name is required" >&2
    exit 1
  }
done

if ! docker image inspect "$image_name" >/dev/null 2>&1; then
  echo "Local image not found: $image_name (run scripts/build_lambda.sh first)" >&2
  exit 1
fi

architecture="$(docker image inspect --format '{{.Architecture}}' "$image_name")"
if [[ "$architecture" != arm64 ]]; then
  echo "Expected an ARM64 image, found: $architecture" >&2
  exit 1
fi

account_id="$(aws sts get-caller-identity --query Account --output text)"
registry="${account_id}.dkr.ecr.${region}.amazonaws.com"
image_uri="${registry}/${repository}:${tag}"

if ! aws ecr describe-repositories \
  --region "$region" \
  --repository-names "$repository" >/dev/null 2>&1; then
  if ! aws ecr create-repository \
    --region "$region" \
    --repository-name "$repository" >/dev/null; then
    echo "ECR repository $repository is missing or not accessible in $region." >&2
    echo "Grant the documented ECR permissions, then retry." >&2
    exit 1
  fi
fi

aws ecr get-login-password --region "$region" |
  docker login --username AWS --password-stdin "$registry" >/dev/null

docker tag "$image_name" "$image_uri"
docker push "$image_uri"

digest="$(aws ecr describe-images \
  --region "$region" \
  --repository-name "$repository" \
  --image-ids "imageTag=$tag" \
  --query 'imageDetails[0].imageDigest' \
  --output text)"

if [[ -z "$digest" || "$digest" == None ]]; then
  echo "Push completed, but ECR did not return an image digest for $image_uri" >&2
  exit 1
fi

echo "Published $image_uri"
echo "Digest: $digest"
