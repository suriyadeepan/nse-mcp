# T8 — Lambda Infrastructure

Terraform now provisions an ARM64 container-image Lambda using the configured ECR image and the T7 execution role. It passes the S3 bucket and dataset prefix to the app, and creates a function-specific CloudWatch log group with configurable retention. Function name, image URI, memory, timeout, and log retention are deployment settings.

The mocked test uses these sample deployment values:

```hcl
processed_data_bucket    = "unit-test-market-data"
dataset_prefix           = "market/processed"
lambda_function_name     = "kite-mcp-unit-test"
lambda_image_uri         = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp:latest"
lambda_memory_size       = 2048
lambda_timeout           = 300
lambda_log_retention_days = 14
```

The account ID, bucket, and ECR repository above are test placeholders; set `lambda_image_uri` to an image that exists in your ECR repository before applying. The code defaults `region` to `ap-south-1`, `lambda_function_name` to `kite-mcp`, `dataset_prefix` to `data/processed`, memory to 2048 MB, timeout to 300 seconds, and log retention to 14 days. `processed_data_bucket`, `lambda_image_uri`, and (since T9) `lambda_bearer_token` must be supplied.

The Function URL is configured with `authorization_type = "NONE"` and a public invoke permission. This lets requests reach the application, where T9 will check the bearer token. Until T9 is implemented, the URL has no application-level authentication.

`terraform/main.tftest.hcl` checks the Lambda image, architecture, role, S3 settings, Function URL permissions, and log group in a mocked plan. `terraform validate` passed, and `terraform test` passed (2 tests, 0 failures). No AWS apply was performed, so there is no deployed Function URL yet.
