# T9 — Protect the Function URL

## Implementation

`src/server/auth.py` wraps the MCP ASGI application and requires `Authorization: Bearer <token>` on HTTP requests. It reads `MCP_BEARER_TOKEN` at request time, compares tokens with `hmac.compare_digest`, returns `401` for missing, malformed, or incorrect credentials, and returns `503` if no token is configured. Rejection responses do not include the submitted token. Non-HTTP ASGI traffic is passed through.

Terraform now accepts required sensitive input `lambda_bearer_token` and supplies it to the Lambda runtime as `MCP_BEARER_TOKEN`. Provide a unique token of at least 32 characters through the ignored `terraform/terraform.tfvars` file or another secure Terraform input; never commit it. Terraform marks the input sensitive in CLI output, but it is stored in Terraform state and Lambda configuration, so protect state access and use an encrypted backend. `.gitignore` excludes tfvars files while allowing safe `*.tfvars.example` templates.

## Verification

`tests/test_auth.py` covers requests with no configured token, missing and malformed headers, an incorrect token, and a valid token. Rejections return only a generic message and a `WWW-Authenticate: Bearer` header; a valid token reaches the app. The existing Streamable HTTP integration tests use a test-only token.

Terraform's mocked tests also verify that the runtime receives the token setting. Run the checks with:

```sh
uv run pytest tests/test_auth.py tests/test_http.py
cd terraform
terraform fmt -check
terraform validate -no-color
terraform test -no-color
```

Results: `uv run --with pytest pytest tests/test_auth.py tests/test_http.py` passed (8 tests); `terraform fmt -recursive`, `terraform validate -no-color`, and `terraform test -no-color` passed (2 Terraform tests). No AWS deployment was performed; the Function URL still has Terraform `authorization_type = "NONE"`, with bearer validation handled by the application.
