mock_provider "aws" {}

run "lambda_uses_image_role_s3_config_and_function_url" {
  command = plan

  override_data {
    target          = data.aws_s3_bucket.processed_data
    override_during = plan
    values = {
      arn    = "arn:aws:s3:::unit-test-market-data"
      bucket = "unit-test-market-data"
    }
  }

  override_resource {
    target          = aws_iam_role.lambda_execution
    override_during = plan
    values = {
      arn = "arn:aws:iam::123456789012:role/kite-mcp-unit-test-execution"
    }
  }

  override_resource {
    target          = aws_lambda_function_url.mcp
    override_during = plan
    values = {
      function_url = "https://unit-test.lambda-url.ap-south-1.on.aws/"
    }
  }

  override_data {
    target          = data.aws_partition.current
    override_during = plan
    values          = { partition = "aws" }
  }

  override_data {
    target          = data.aws_caller_identity.current
    override_during = plan
    values          = { account_id = "123456789012" }
  }

  variables {
    processed_data_bucket    = "unit-test-market-data"
    lambda_image_uri         = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp:latest"
    lambda_function_url_host = "unit-test.lambda-url.ap-south-1.on.aws"
    lambda_bearer_token      = "unit-test-token-with-at-least-32-characters"
    lambda_function_name     = "kite-mcp-unit-test"
    dataset_prefix           = "market/processed"
  }

  assert {
    condition = alltrue([
      aws_lambda_function.mcp.function_name == "kite-mcp-unit-test",
      aws_lambda_function.mcp.role == aws_iam_role.lambda_execution.arn,
      aws_lambda_function.mcp.package_type == "Image",
      aws_lambda_function.mcp.image_uri == "123456789012.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp:latest",
      contains(aws_lambda_function.mcp.architectures, "arm64"),
    ])
    error_message = "Lambda must use the configured image, shared function name, ARM64 architecture, and T7 execution role."
  }

  assert {
    condition = alltrue([
      aws_lambda_function.mcp.environment[0].variables.PROCESSED_DATA_SOURCE == "s3",
      aws_lambda_function.mcp.environment[0].variables.PROCESSED_DATA_S3_BUCKET == "unit-test-market-data",
      aws_lambda_function.mcp.environment[0].variables.PROCESSED_DATA_S3_PREFIX == "market/processed",
      aws_lambda_function.mcp.environment[0].variables.MCP_BEARER_TOKEN == "unit-test-token-with-at-least-32-characters",
      aws_lambda_function.mcp.environment[0].variables.MCP_FUNCTION_URL_HOST == "unit-test.lambda-url.ap-south-1.on.aws",
    ])
    error_message = "Lambda must receive the S3 dataset settings and bearer token at runtime."
  }

  assert {
    condition = alltrue([
      aws_lambda_function_url.mcp.authorization_type == "NONE",
      aws_lambda_permission.function_url.principal == "*",
      aws_lambda_permission.function_url.action == "lambda:InvokeFunctionUrl",
      aws_lambda_permission.function_url_invoke.principal == "*",
      aws_lambda_permission.function_url_invoke.action == "lambda:InvokeFunction",
      aws_lambda_permission.function_url_invoke.invoked_via_function_url,
    ])
    error_message = "The Function URL must be publicly reachable so the application can enforce bearer authentication in T9."
  }

  assert {
    condition = alltrue([
      aws_cloudwatch_log_group.lambda.name == "/aws/lambda/kite-mcp-unit-test",
      aws_cloudwatch_log_group.lambda.retention_in_days == 14,
    ])
    error_message = "Lambda logs must use a function-specific CloudWatch log group with configurable retention."
  }

  assert {
    condition     = output.mcp_endpoint_url == "https://unit-test.lambda-url.ap-south-1.on.aws/mcp"
    error_message = "Terraform must output the MCP Streamable HTTP endpoint path."
  }
}
