# AWS Lambda T10: outputs and teardown

`terraform/outputs.tf` exposes `mcp_endpoint_url`, the Function URL with `/mcp` appended. After deployment, retrieve it with `terraform -chdir=terraform output -raw mcp_endpoint_url`. The committed `terraform/terraform.tfvars.example` uses a placeholder bucket, sample ECR URI, and a clearly marked token placeholder; copy it to the ignored `terraform/terraform.tfvars`, then replace each placeholder before applying.

The processed upload resource remembers its bucket and dataset prefix. On destroy (including replacement), its destroy provisioner runs the AWS CLI recursive removal only for that prefix, before Terraform removes the bucket and Lambda resources. The deploying identity needs permission to remove those S3 objects. No AWS deployment was run for this change, so no live endpoint or teardown result is claimed.

Validation: `uv run --with pytest pytest tests/test_upload_processed_data.py` passed (6 tests), covering exact-prefix removal and rejection of an empty prefix. `terraform fmt -check -recursive`, `terraform validate -no-color`, and `terraform test -no-color` passed (2 Terraform plan tests).
