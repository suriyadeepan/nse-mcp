#!/usr/bin/env bash
set -euo pipefail

AWS_REGION="${AWS_REGION:-ap-south-1}"
REPOSITORY="${ECR_REPOSITORY:-kite-mcp}"

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

export AWS_DEFAULT_REGION="$AWS_REGION"

echo "Checking ECR repository: $REPOSITORY"

# Create repository if it doesn't exist
if ! aws ecr describe-repositories \
  --repository-names "$REPOSITORY" \
  --region "$AWS_REGION" >/dev/null 2>&1; then

  echo "Creating ECR repository..."
  aws ecr create-repository \
    --repository-name "$REPOSITORY" \
    --region "$AWS_REGION"
else
  echo "ECR repository already exists."
fi

# Verify repository
aws ecr describe-repositories \
  --repository-names "$REPOSITORY" \
  --region "$AWS_REGION"

# Publish Docker image
echo "Publishing Lambda image..."
"$SCRIPT_DIR/push_lambda.sh"

echo "Deployment publishing steps completed."
