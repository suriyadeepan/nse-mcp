# Step 9: Demo Preparation and Infrastructure Teardown Requirements

## Objective

Prepare a concise, repeatable portfolio demo, capture evidence of the completed workflow, and safely remove disposable AWS resources afterward.

## Requirements

- **R001 — Prepare the demo instructions**
  - **R001.1** Add a concise README section with exact commands to configure and run the local client, execute the Step 8 verification script, and inspect CloudWatch logs. Give the user simple browser instructions for checking Langfuse traces and a checklist to mark off during review.
  - **R001.2** Use existing Step 7 and Step 8 commands; do not duplicate their setup or implementation instructions.
  - **R001.3** Ensure the demo runs without source-code edits between steps.
- **R002 — Create the demo sequence and capture evidence**
  - **R002.1** Document a short sequence covering architecture and S3 dataset; Terraform-managed Lambda and Function URL; runtime MCP tool discovery; natural-language query and OpenAI tool selection; remote analytics result and Step 8 ground-truth comparison; invalid-symbol rejection; Langfuse trace and CloudWatch invocation; and Terraform teardown.
  - **R002.2** Capture concise screenshots or logs for key stages.
  - **R002.3** Reuse existing Step 7 and Step 8 verification evidence where suitable.
- **R003 — Verify and document safe teardown**
  - **R003.1** Review the existing Step 7 Terraform destroy procedure against the current Terraform configuration and state.
  - **R003.2** Confirm the exact project-owned resources to be destroyed and that the S3 bucket, processed objects, and pre-existing resources are preserved.
  - **R003.3** Document commands to create, inspect, and apply a saved destroy plan.
  - **R003.4** Require explicit human approval before applying the reviewed plan; do not run destruction automatically.
  - **R003.5** Document post-destroy checks for Terraform state, AWS resources, and the preserved S3 dataset.
- **R004 — Acceptance criteria**
  - **R004.1** README provides a repeatable demo and teardown procedure.
  - **R004.2** Demo evidence covers the complete workflow without repeating Step 7 or Step 8 tests.
  - **R004.3** The reviewed destroy plan contains no S3 deletion or unexpected resource changes.
  - **R004.4** Post-destroy checks confirm disposable resources are removed and the S3 dataset remains intact.
- **R005 — Scope exclusions**
  - **R005.1** No new application features, analytics tests, MCP client tests, Langfuse tests, or deployment changes.
  - **R005.2** Do not delete the S3 bucket or processed dataset.

## Planning observations

- Current read-only checks (2026-11-20) found seven managed Terraform resources and the matching Lambda, execution role, and CloudWatch log group. The processed prefix contains 2,781 objects totaling 326,546,421 bytes.
- `terraform/s3.tf` uses `removed` blocks with `destroy = false` for the former S3 bucket, public access block, and upload resource. The current state lists the processed bucket as a data source, not a managed resource.
- The teardown itself is destructive to the live demo endpoint and requires separate explicit approval after a saved plan is reviewed. This planning request does not authorize applying a destroy plan.
- The key evidence may be recorded as concise, redacted logs in the Step 9 implementation journal, reusing prior Step 7/8 evidence where it already proves a stage. No screenshot-only requirement is stated.
