# Lambda container build failure report

## Summary

The local Lambda image build did not produce a usable image. The failure occurred during Docker's image export, after Docker pulled the Python 3.14 Lambda base image and the AWS Lambda Web Adapter image. The available output points to a Docker legacy builder/content-store export problem; it does not establish the underlying cause. No evidence from this attempt shows a failure in the Python dependencies or application startup because the image was never successfully exported and run.

## Build setup

- Build command: `scripts/build_lambda.sh`
- Dockerfile: `Dockerfile.lambda`
- Default image tag: `kite-mcp-lambda:local`
- Default target platform: `linux/amd64` (`LAMBDA_IMAGE` and `LAMBDA_PLATFORM` can override these values)
- Base image: `public.ecr.aws/lambda/python:3.14`
- Lambda adapter source: `public.ecr.aws/awsguru/aws-lambda-adapter:1.1.0`
- Builder in use: Docker's legacy builder. Docker printed a deprecation notice recommending Buildx/BuildKit.

## What happened

1. The first build sent a 1.437 GB context to the Docker daemon. This repository includes local processed data, which is not needed to assemble the image.
2. That attempt was stopped before completion. A root `.dockerignore` was added to exclude local data, tests, Terraform files, docs, scripts, virtual environments, and other non-image inputs.
3. The next build sent a 356.4 KB context, pulled the Python 3.14 Lambda base image, and pulled the Lambda Web Adapter image.
4. Docker then reported:

   ```text
   failed to export image: NotFound: content digest sha256:4c287ec31b9c794d88413f7c37b833ef26ab7d471503d9f47f7e51bdd7ecb543: not found
   ```

5. `docker buildx version` reported `docker: unknown command: docker buildx`, so the recommended Buildx builder was not available in this Docker installation.

## Why it failed

The observed final error is an image export failure: the legacy builder could not find a content digest it needed while exporting the image. This happened after base-image downloads. The output does not identify why the digest was missing. A legacy builder or Docker daemon content-store/cache problem is a plausible explanation, but it is not confirmed by the available evidence.

The oversized context was a separate issue, not the cause of the final failure: it was reduced from 1.437 GB to 356.4 KB, but the second build still failed at export. The missing Buildx command prevented trying the BuildKit path recommended by Docker's deprecation warning. There is not enough output to conclude that `Dockerfile.lambda`, its dependency installation, or its app entrypoint is defective.

## Impact and verification status

- No successfully exported `kite-mcp-lambda:local` image was confirmed.
- The container was not started, so startup and MCP behavior were not tested.
- At the time of the original failure, no image was available and T6.3/T6.4 were pending. The later ARM64 build result is recorded below.
- T6.4 remains pending; it depends on a successful T6.3 build before RIE can be used for the container smoke test.
- Script syntax (`bash -n scripts/build_lambda.sh`) and whitespace validation (`git diff --check`) passed. These checks do not validate Docker image construction.

## Next diagnostic steps

1. Install or enable Docker Buildx/BuildKit for the current Docker installation, then rerun `scripts/build_lambda.sh`.
2. If export still fails, capture the complete build output and inspect Docker daemon logs and builder/cache state around the reported digest.
3. Confirm the image exists with `docker image inspect kite-mcp-lambda:local` after a successful build.
4. Run the planned T6.4 RIE smoke test only after the image is available; verify startup, an HTTP response, MCP initialization, tool discovery, and tool execution.

## ARM64 build result

The T6.3 and T6.4 target changed to ARM64 (`linux/arm64`). The build script now defaults to that platform. The user confirmed that this command completes successfully:

```bash
LAMBDA_PLATFORM=linux/arm64 ./scripts/build_lambda.sh
```

This completes T6.3. The successful ARM64 build does not establish why the earlier `linux/amd64` build failed at export; that cause remains undetermined. T6.4 remains pending until the ARM64 image is started with RIE and an invocation verifies startup and MCP behavior.

The Dockerfile references a DuckDB extension directory named `linux_amd64`. Although the ARM64 image build succeeded, runtime compatibility of the included extension binaries still needs to be checked as part of T6.4.
