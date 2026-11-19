data "aws_s3_bucket" "processed_data" {
  bucket = var.processed_data_bucket
}

removed {
  from = aws_s3_bucket.processed_data

  lifecycle {
    destroy = false
  }
}

removed {
  from = aws_s3_bucket_public_access_block.processed_data

  lifecycle {
    destroy = false
  }
}

removed {
  from = terraform_data.processed_data_upload

  lifecycle {
    destroy = false
  }
}
