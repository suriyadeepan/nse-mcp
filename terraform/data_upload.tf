locals {
  processed_data_dir      = "${path.module}/../data/processed"
  processed_parquet_files = fileset(local.processed_data_dir, "**/*.parquet")
  processed_dataset_hash = sha256(join("", [
    for file in local.processed_parquet_files : filesha256("${local.processed_data_dir}/${file}")
  ]))
}

# Keep object creation in the deployment flow while letting the AWS CLI sync
# preserve every Hive partition path as the corresponding S3 key.
resource "terraform_data" "processed_data_upload" {
  input = {
    dataset_hash = local.processed_dataset_hash
    bucket       = var.processed_data_bucket
    prefix       = var.dataset_prefix
  }

  triggers_replace = [
    local.processed_dataset_hash,
    var.dataset_prefix,
  ]

  depends_on = [aws_s3_bucket_public_access_block.processed_data]

  provisioner "local-exec" {
    command = join(" ", [
      "python3",
      "${path.module}/../scripts/upload_processed_data.py",
      "--data-dir",
      "${local.processed_data_dir}",
      "--bucket",
      var.processed_data_bucket,
      "--prefix",
      var.dataset_prefix,
    ])
  }

  provisioner "local-exec" {
    when    = destroy
    command = "python3 ${path.module}/../scripts/upload_processed_data.py --delete"
    environment = {
      S3_BUCKET = self.input.bucket
      S3_PREFIX = self.input.prefix
    }
  }
}
