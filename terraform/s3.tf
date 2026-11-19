resource "aws_s3_bucket" "processed_data" {
  bucket        = var.processed_data_bucket
  force_destroy = true

  tags = {
    Name      = "${var.processed_data_bucket}-processed-data"
    ManagedBy = "Terraform"
  }
}

resource "aws_s3_bucket_public_access_block" "processed_data" {
  bucket                  = aws_s3_bucket.processed_data.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
