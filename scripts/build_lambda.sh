#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
image_name="${LAMBDA_IMAGE:-kite-mcp-lambda:local}"
platform="linux/arm64"

command -v docker >/dev/null || { echo "Docker is required" >&2; exit 1; }
[[ -f "$repo_root/Dockerfile.lambda" ]] || {
  echo "Dockerfile not found: $repo_root/Dockerfile.lambda" >&2
  exit 1
}

docker buildx build \
  --progress=plain \
  --provenance=false \
  --sbom=false \
  --load \
  --platform "$platform" \
  --file "$repo_root/Dockerfile.lambda" \
  --tag "$image_name" \
  "$repo_root"

echo "Built Lambda image $image_name for $platform"
