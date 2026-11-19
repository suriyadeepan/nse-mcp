locals {
  dataset_key_prefix = trim(var.dataset_prefix, "/")
  lambda_log_group   = "/aws/lambda/${var.lambda_function_name}"
  lambda_assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowLambdaServiceToAssumeRole"
      Effect    = "Allow"
      Action    = "sts:AssumeRole"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  lambda_runtime_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListOnlyTheDatasetPrefix"
        Effect   = "Allow"
        Action   = "s3:ListBucket"
        Resource = data.aws_s3_bucket.processed_data.arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              local.dataset_key_prefix,
              "${local.dataset_key_prefix}/*",
            ]
          }
        }
      },
      {
        Sid      = "ReadOnlyDatasetObjects"
        Effect   = "Allow"
        Action   = "s3:GetObject"
        Resource = "${data.aws_s3_bucket.processed_data.arn}/${local.dataset_key_prefix}/*"
      },
      {
        Sid      = "CreateLambdaLogGroup"
        Effect   = "Allow"
        Action   = "logs:CreateLogGroup"
        Resource = "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:${local.lambda_log_group}"
      },
      {
        Sid      = "WriteLambdaLogs"
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:${data.aws_partition.current.partition}:logs:${var.region}:${data.aws_caller_identity.current.account_id}:log-group:${local.lambda_log_group}:log-stream:*"
      },
    ]
  })
}

resource "aws_iam_role" "lambda_execution" {
  name               = "${var.lambda_function_name}-execution"
  assume_role_policy = local.lambda_assume_role_policy
}

data "aws_partition" "current" {}

data "aws_caller_identity" "current" {}

resource "aws_iam_role_policy" "lambda_runtime" {
  name   = "${var.lambda_function_name}-runtime"
  role   = aws_iam_role.lambda_execution.id
  policy = local.lambda_runtime_policy
}
