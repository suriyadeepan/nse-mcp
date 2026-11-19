# AWS Lambda T11: Lambda and HTTP tests

`tests/test_lambda.py` runs an isolated Streamable HTTP MCP server with the Lambda authentication middleware. It verifies that a request without a bearer token is rejected, while an authenticated client can initialize, discover `get_bars`, and execute it. The S3 query test configures the deployment bucket and prefix, removes static AWS access-key variables, and checks DuckDB uses `PROVIDER credential_chain` for the requested S3 Parquet glob. This models Lambda execution-role credential discovery without embedding credentials or contacting AWS.

Validation: `uv run --with pytest pytest tests/test_lambda.py tests/test_http.py tests/test_auth.py tests/test_s3_data.py` passed (18 tests). No live Lambda invocation or AWS S3 query was performed; live execution-role access remains part of T12.
