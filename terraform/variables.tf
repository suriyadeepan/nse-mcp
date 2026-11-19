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
