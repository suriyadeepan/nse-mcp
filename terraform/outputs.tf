output "processed_data_bucket" {
  description = "S3 bucket containing the processed Parquet dataset"
  value       = data.aws_s3_bucket.processed_data.bucket
}

output "dataset_prefix" {
  description = "S3 key prefix containing the processed Parquet dataset"
  value       = var.dataset_prefix
}

output "mcp_endpoint_url" {
  description = "Authenticated Streamable HTTP MCP endpoint URL"
  value       = "${trimsuffix(aws_lambda_function_url.mcp.function_url, "/")}/mcp"
}
