mock_provider "aws" {}

run "execution_role_is_lambda_assumable_and_scoped" {
  command = plan

  override_resource {
    target          = aws_s3_bucket.processed_data
    override_during = plan
    values = {
      arn = "arn:aws:s3:::unit-test-market-data"
    }
  }

  override_data {
    target          = data.aws_partition.current
    override_during = plan
    values = {
      partition = "aws"
    }
  }

  override_data {
    target          = data.aws_caller_identity.current
    override_during = plan
    values = {
      account_id = "123456789012"
    }
  }

  variables {
    processed_data_bucket = "unit-test-market-data"
    lambda_image_uri      = "123456789012.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp:latest"
    dataset_prefix        = "market/processed"
    lambda_function_name  = "kite-mcp-unit-test"
  }

  assert {
    condition = contains(
      try(tolist(jsondecode(local.lambda_assume_role_policy).Statement[0].Principal.Service), [jsondecode(local.lambda_assume_role_policy).Statement[0].Principal.Service]),
      "lambda.amazonaws.com",
    )
    error_message = "The execution role must be assumable by the Lambda service."
  }

  assert {
    condition = length([
      for statement in jsondecode(local.lambda_runtime_policy).Statement : statement
      if contains(try(tolist(statement.Action), [statement.Action]), "s3:ListBucket")
      && contains(try(tolist(statement.Resource), [statement.Resource]), "arn:aws:s3:::unit-test-market-data")
      && try(contains(statement.Condition.StringLike["s3:prefix"], "market/processed/*"), false)
    ]) == 1
    error_message = "S3 listing must be limited to the configured dataset prefix."
  }

  assert {
    condition = length([
      for statement in jsondecode(local.lambda_runtime_policy).Statement : statement
      if contains(try(tolist(statement.Action), [statement.Action]), "s3:GetObject")
      && contains(try(tolist(statement.Resource), [statement.Resource]), "arn:aws:s3:::unit-test-market-data/market/processed/*")
      ]) == 1 && length([
      for statement in jsondecode(local.lambda_runtime_policy).Statement : statement
      if anytrue([for action in try(tolist(statement.Action), [statement.Action]) : startswith(action, "s3:")])
      && anytrue([for action in try(tolist(statement.Action), [statement.Action]) : contains(["s3:PutObject", "s3:DeleteObject", "s3:*"], action)])
    ]) == 0
    error_message = "S3 object access must be read-only and limited to the configured dataset prefix."
  }

  assert {
    condition = length([
      for statement in jsondecode(local.lambda_runtime_policy).Statement : statement
      if contains(try(tolist(statement.Action), [statement.Action]), "logs:CreateLogGroup")
      && contains(try(tolist(statement.Resource), [statement.Resource]), "arn:aws:logs:ap-south-1:123456789012:log-group:/aws/lambda/kite-mcp-unit-test")
      ]) == 1 && length([
      for statement in jsondecode(local.lambda_runtime_policy).Statement : statement
      if contains(try(tolist(statement.Action), [statement.Action]), "logs:PutLogEvents")
      && contains(try(tolist(statement.Resource), [statement.Resource]), "arn:aws:logs:ap-south-1:123456789012:log-group:/aws/lambda/kite-mcp-unit-test:log-stream:*")
    ]) == 1
    error_message = "CloudWatch log permissions must be scoped to this Lambda function's log group and streams."
  }
}
