variable "region" {
  description = "AWS region for the demo deployment"
  type        = string
  default     = "ap-south-1"
}

variable "processed_data_bucket" {
  description = "Globally unique S3 bucket name for processed market data"
  type        = string
}

variable "dataset_prefix" {
  description = "S3 key prefix for processed Parquet objects"
  type        = string
  default     = "data/processed"

  validation {
    condition     = length(trim(var.dataset_prefix, "/")) > 0
    error_message = "dataset_prefix must identify a non-empty S3 key prefix."
  }
}

variable "lambda_function_name" {
  description = "Lambda function name, used to scope its execution role and CloudWatch log permissions"
  type        = string
  default     = "kite-mcp"
}

variable "lambda_image_uri" {
  description = "ECR image URI for the Lambda container, including its tag or digest"
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}\\.dkr\\.ecr\\.[a-z0-9-]+\\.amazonaws\\.com(/[^[:space:]]+)$", var.lambda_image_uri))
    error_message = "lambda_image_uri must be an ECR image URI including a repository and tag or digest."
  }
}

variable "lambda_function_url_host" {
  description = "Exact hostname of the Lambda Function URL, used by MCP DNS rebinding protection"
  type        = string

  validation {
    condition     = can(regex("^[A-Za-z0-9.-]+$", var.lambda_function_url_host))
    error_message = "lambda_function_url_host must be a hostname without a scheme, path, or port."
  }
}

variable "lambda_bearer_token" {
  description = "Bearer token required by the MCP HTTP endpoint; supply through a protected tfvars file or secure input"
  type        = string
  sensitive   = true

  validation {
    condition     = length(var.lambda_bearer_token) >= 32
    error_message = "lambda_bearer_token must contain at least 32 characters."
  }
}

variable "lambda_memory_size" {
  description = "Lambda memory allocation in MB"
  type        = number
  default     = 2048

  validation {
    condition     = var.lambda_memory_size >= 128 && var.lambda_memory_size <= 10240
    error_message = "lambda_memory_size must be between 128 and 10240 MB."
  }
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds"
  type        = number
  default     = 300

  validation {
    condition     = var.lambda_timeout >= 1 && var.lambda_timeout <= 900
    error_message = "lambda_timeout must be between 1 and 900 seconds."
  }
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log retention period in days"
  type        = number
  default     = 14
}
