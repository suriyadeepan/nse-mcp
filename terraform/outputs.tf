output "processed_data_bucket" {
  description = "S3 bucket containing the processed Parquet dataset"
  value       = aws_s3_bucket.processed_data.bucket
}

output "dataset_prefix" {
  description = "S3 key prefix containing the processed Parquet dataset"
  value       = var.dataset_prefix
}
