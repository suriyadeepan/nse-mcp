# Step 9: Demo Preparation and Infrastructure Teardown Plan

## Scope and approach

- **P001 — README demo flow [R001.1–R001.3, R002.1]**: Add a concise Step 9 section to `README.md` with a numbered, repeatable sequence from architecture/dataset overview through teardown. Point to existing Step 7 and Step 8 tutorials for setup and established commands. Include exact commands for local client configuration/queries, the existing Step 8 verification script, and CloudWatch log review. Give simple browser instructions for Langfuse trace review and ask the user to check off a short list covering the query, model exchange, MCP tool inputs/results, final answer, and absence of credentials. Keep the sequence runnable without source edits.
- **P002 — Reusable evidence [R002.2–R002.3, R004.2]**: Add `docs/009-demo-preparation.md` as a durable implementation journal. Record concise, sanitized command output for stages that need fresh evidence and reference existing Step 7/8 live verification records for stages already proven. Do not copy credentials, raw sensitive plan data, or unredacted logs. Do not add new tests or implementation features.
- **P003 — Reviewed teardown procedure [R003.1–R003.5, R004.3–R004.4, R005.2]**: Verify the saved destroy procedure against Terraform configuration and state; document a saved-plan create/show/apply sequence, the expected resource addresses, strict no-S3-delete/no-unexpected-action review criteria, and post-destroy state/AWS/S3 checks. Applying the plan is a separate human-approval gate. Do not perform it as part of implementation without explicit approval of the exact reviewed plan.
- **P004 — Exclusions [R005.1–R005.2]**: Make documentation-only changes. No application, tests, Terraform configuration, infrastructure deployment, or dataset mutation is planned.

## Affected files and dependencies

- `README.md` — concise demo and teardown entry points.
- `docs/009-demo-preparation.md` — execution evidence, current resource/state review and teardown verification record.
- `docs/009-demo-preparation-requirements.md` — canonical requirements.
- `docs/009-demo-preparation-plan.md` — this approved plan.
- Existing interfaces/evidence to reuse: `docs/tutorial-007-remote-mcp-client.md`, `docs/tutorial-008-independent-analytics-verification.md`, `docs/007-remote-mcp-client.md`, `docs/008-independent-analytics-verification.md`, `terraform/`.
- No new dependencies.

## Teardown resource scope confirmed at planning

Current Terraform state lists seven managed resources:

1. `aws_cloudwatch_log_group.lambda` — `/aws/lambda/kite-mcp`.
2. `aws_iam_role.lambda_execution` — `kite-mcp-execution`.
3. `aws_iam_role_policy.lambda_runtime` — `kite-mcp-runtime` inline policy.
4. `aws_lambda_function.mcp` — `kite-mcp` Lambda.
5. `aws_lambda_function_url.mcp` — the Lambda Function URL.
6. `aws_lambda_permission.function_url` — `AllowPublicFunctionUrlInvoke` permission.
7. `aws_lambda_permission.function_url_invoke` — `AllowFunctionUrlInvoke` permission.

The state also lists `data.aws_caller_identity.current`, `data.aws_partition.current`, and `data.aws_s3_bucket.processed_data`; these are data sources, not destroyable managed resources. `terraform/s3.tf` declares `destroy = false` removed blocks for the old bucket, public access block and upload resource. The processed dataset is read-only Lambda input. Current AWS read-only checks confirmed the Lambda, role, and log group exist; S3 inventory is 2,781 objects and 326,546,421 bytes under `data/processed/`. The destroy plan must still be generated and inspected at execution time; its exact resource actions cannot be presumed from this planning snapshot.

## Compatibility matrix

| Area | Status | Evidence / constraint |
| --- | --- | --- |
| Local client runtime | VERIFIED | Step 7 journal records Python 3.15.2 and `uv`; `pyproject.toml` requires Python `>=3.15`. |
| Remote Lambda runtime and CPU | VERIFIED | Step 6/7 records use of the AWS Lambda container image on ARM64; current Terraform sets `architectures = ["arm64"]`. This plan does not alter the image or target. |
| Container format | VERIFIED | Terraform `package_type = "Image"`; Step 7 records a successful `linux/arm64` image build and deployment. |
| Native dependencies | VERIFIED | Demo documentation reuses existing commands and dependencies; no package or native dependency changes are planned. |
| AWS deployment/state | VERIFIED (point in time) | On 2026-11-20, `terraform state list` showed the seven managed demo resources; read-only AWS checks found the named Lambda, role, and log group. |
| S3 preservation | VERIFIED (configuration and baseline) | Terraform references the bucket as a data source; removed blocks specify `destroy = false`; current inventory is 2,781 objects / 326,546,421 bytes. Verify again against the reviewed destroy plan and after any approved apply. |
| Automated compatibility checks | NOT REQUIRED | Scope is documentation and read-only review; no code or runtime changes. Existing Step 7/8 test evidence is referenced rather than rerun as duplicate feature testing. |

## Risks and mitigations

- **RISK P001 — Destroy plan drift:** Current state can change between planning and execution. Generate a fresh saved plan; inspect resource actions and apply only that exact saved plan after explicit human approval.
- **RISK P002 — Accidental data deletion:** Reject any plan with S3 delete actions, unexpected actions, or unexpected resources. Verify the S3 baseline immediately before and after approved teardown; never run upload/cleanup scripts.
- **RISK P003 — Sensitive material in evidence:** Terraform plans/state and logs can contain sensitive values. Keep saved plan local, inspect a filtered action summary, and record only redacted evidence in the journal.
- **RISK P004 — Demo prerequisite drift:** The live endpoint, local `.env`, AWS permissions, Langfuse project, and local dataset may differ later. Link to established setup docs and state prerequisites; use stored prior evidence when a live service is unavailable rather than asserting a fresh run.

## Acceptance and validation

- **P005 — Repeatable instructions [R001, R002.1, R004.1]**: README has exact existing commands/links for client configuration and execution, Step 8 verification, CloudWatch, and teardown; Langfuse has simple browser instructions and a user-checkable trace checklist. No source edits are required between stages.
- **P006 — Complete evidence [R002.1–R002.3, R004.2]**: The eight requested demo stages are represented by concise evidence or a precise reference to verified Step 7/8 evidence; outputs contain no secrets.
- **P007 — Safe teardown [R003, R004.3–R004.4]**: The procedure describes the saved plan lifecycle and explicit approval gate; the reviewed plan has only the seven expected demo resource removals (or safely documented state-only `forget` actions for legacy removed resources), no S3 delete and no unexpected changes. After a separately approved apply, state and AWS checks confirm removal and the preserved prefix matches its pre-destroy baseline. If approval is not given, post-destroy success must remain explicitly pending rather than claimed.
- **P008 — Scope [R005]**: No source, test, Terraform, deployment, or dataset changes are included.

## Approval boundary

Human approval is required before applying any saved destroy plan. Approval must follow presentation of the concrete plan’s filtered action summary and confirmation that it contains no S3 deletion or unexpected resource change. The current planning request does not authorize destruction. No `terraform apply`/`destroy` is planned before that separate approval.
