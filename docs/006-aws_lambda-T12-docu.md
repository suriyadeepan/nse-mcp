# AWS Lambda T12: end-to-end verification

The deployment configuration targets `ap-south-1`, an ARM64 image, a 2,048 MB Lambda with a 300-second timeout, and a 14-day CloudWatch log group. Terraform exposes the MCP endpoint as the Function URL with `/mcp`; its execution role is scoped to the configured dataset prefix and Lambda log group. The existing T2 S3 dataset is the deployment input; this step does not run the upload script. Terraform destroy is configured to remove only objects beneath that dataset prefix.

The HTTP middleware now logs request method, path, and response status without recording headers, query strings, or tokens. The integration test checks successful authenticated MCP tool execution, missing and incorrect token rejection (401), and that log output contains no supplied tokens. Tool exceptions continue to be logged for CloudWatch.

Local validation: `uv run --with pytest pytest tests/test_lambda.py tests/test_http.py tests/test_auth.py tests/test_s3_data.py` passed (18 tests). `terraform fmt -check -recursive`, `terraform -chdir=terraform validate -no-color`, and `terraform -chdir=terraform test -no-color` passed (2 mocked Terraform tests). No AWS apply, remote S3 query, CloudWatch inspection, endpoint invocation, Terraform output, or destroy was run; live deployment and teardown results remain unverified.
