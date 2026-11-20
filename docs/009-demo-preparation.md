# Step 9: Demo Preparation Journal

## T002 — Workflow evidence

Evidence combines the fresh local client run on 2026-11-20 with the previously verified Step 7 and Step 8 records. The prior results are dated and linked below; they are not presented as new runs. No credentials, endpoints, raw CloudWatch messages, or trace payloads are reproduced here.

### Fresh runtime discovery and query (2026-11-20)

The first local query attempt used the malformed `MCP_SERVER_URL` value in `.env` and failed before MCP initialization. The value is omitted. Using the endpoint from the current Terraform output, authenticated MCP discovery succeeded and returned six runtime tools: `get_bars`, `intraday_stats`, `get_price_extremes`, `get_volume_stats`, `compute_indicators`, and `compare_symbols`. No tool catalogue was hardcoded in the client.

The client was then run with the Terraform endpoint exported into the shell:

```sh
export MCP_SERVER_URL="$(terraform -chdir=terraform output -raw mcp_endpoint_url)"
uv run python -m client.main \
  --prompt 'For RELIANCE on 2025-01-02, report the open, close, return, VWAP, and number of bars.'
```

Sanitized output:

```text
Open: ₹1221.25
Close: ₹1240.80
Return: ₹19.55 (1.60%)
VWAP: ₹1234.29
Number of bars: 375
```

The matching Step 7 single-tool run records OpenAI selection of `intraday_stats` and the same rounded analytics result. Its Langfuse inspection recorded a complete four-observation trace with the query, model exchange, MCP tool input/result, and final answer; the configured endpoint and credentials were absent from trace inputs and outputs. See [Step 7 live verification](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19). On 2026-11-20, the user also manually inspected the current query trace in Langfuse and confirmed that all README checklist items passed.

### Evidence map for the demo sequence

| Stage | Evidence and date | Status |
| --- | --- | --- |
| Architecture and S3 dataset | [Ingestion tutorial](tutorial-001-ingestion.md) and the verified data/deployment context in [Step 7 journal](007-remote-mcp-client.md) | Prior documentation and implementation evidence |
| Terraform Lambda and Function URL | [Step 7 deployment and live verification](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19) | Prior verified deployment; current plan/state review is tracked separately under T003 |
| Runtime MCP tool discovery | Six tools returned from the Terraform endpoint | Fresh live observation, 2026-11-20 |
| Natural-language query and model tool selection | Fresh query output above; `intraday_stats` selection recorded in the matching [Step 7 trace evidence](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19) | Fresh query; selection and trace inspection reused from prior verified run |
| Remote analytics and ground-truth comparison | [Step 8 live verification](008-independent-analytics-verification.md) compares remote INFY results with independent local PyArrow results | Prior live verification, PASS, 2026-11-19 |
| Invalid-symbol rejection | [Step 8 live verification](008-independent-analytics-verification.md) records clean rejection of `__KITE_INVALID_SYMBOL__` | Prior live verification, PASS, 2026-11-19 |
| Langfuse trace and CloudWatch invocation | [Step 7 Langfuse trace inspection](007-remote-mcp-client.md#step-7-approved-host-configuration-update-deployment-and-live-verification-2026-11-19) and [Step 8 correlated CloudWatch evidence](008-independent-analytics-verification.md) | Prior invocation correlation PASS, 2026-11-19; user manually confirmed current trace checklist PASS, 2026-11-20 |
| Terraform teardown | The saved-plan, review, approval, apply, and preservation procedure is in the [Step 7 teardown guide](tutorial-007-remote-mcp-client.md#destroy-the-demo-deployment-and-keep-the-dataset); T003 and T004 evidence follows | Plan reviewed and explicitly approved; seven resources destroyed; post-destroy checks passed and S3 baseline preserved |

### T003 — Current teardown review (2026-11-20)

Read-only checks before planning:

```sh
terraform -chdir=terraform state list
aws lambda get-function-configuration --function-name kite-mcp --region ap-south-1 --query '{FunctionName:FunctionName,State:State,LastUpdateStatus:LastUpdateStatus,Architectures:Architectures}' --output json
aws lambda get-function-url-config --function-name kite-mcp --region ap-south-1 --query '{FunctionUrl:FunctionUrl,AuthType:AuthType}' --output json
aws iam get-role --role-name kite-mcp-execution --query 'Role.RoleName' --output text
aws iam get-role-policy --role-name kite-mcp-execution --policy-name kite-mcp-runtime --query 'PolicyName' --output text
aws lambda get-policy --function-name kite-mcp --region ap-south-1 --query 'Policy' --output text | jq -r '[.Statement[].Sid] | sort'
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/kite-mcp --region ap-south-1 --query 'logGroups[].{name:logGroupName,retention:retentionInDays}' --output json
aws s3api list-objects-v2 --bucket nse-mcp-data --prefix data/processed/ --query '[length(Contents[]),sum(Contents[].Size)]' --output json
```

Terraform state contains the seven expected managed addresses (`aws_cloudwatch_log_group.lambda`, `aws_iam_role.lambda_execution`, `aws_iam_role_policy.lambda_runtime`, `aws_lambda_function.mcp`, `aws_lambda_function_url.mcp`, `aws_lambda_permission.function_url`, and `aws_lambda_permission.function_url_invoke`) plus three data sources. Read-only AWS checks found the Lambda active with successful last update and ARM64 architecture, the Function URL configured with `AuthType=NONE`, the named role and inline policy, both URL permission statements, and the log group with 14-day retention. The S3 baseline immediately before planning was **2,781 objects / 326,546,421 bytes** under `data/processed/`, matching the prior recorded baseline. `terraform/s3.tf` still has `destroy = false` on the removed bucket, public access block, and upload addresses.

Saved plan and filtered review:

```sh
terraform -chdir=terraform plan -destroy -no-color -out=/tmp/kite-mcp-t003-destroy.tfplan
terraform -chdir=terraform show -json /tmp/kite-mcp-t003-destroy.tfplan \
  | jq -c '{format_version, resource_changes: [.resource_changes[]? | {address, actions: .change.actions}], output_changes: [.output_changes // {} | to_entries[] | {name: .key, actions: .value.actions}]}'
shasum -a 256 /tmp/kite-mcp-t003-destroy.tfplan
```

The saved plan hash is `9a1d4826f8ba48fa0ff4f9b5864dc2479d49812232f698dc45f129ba24a113c3`. Its complete resource action list is seven `delete` actions, one for each managed demo address above. There are no S3 resource changes, `forget` actions, or unexpected resource actions; the S3 data source is not a managed resource. The three output changes (`dataset_prefix`, `mcp_endpoint_url`, and `processed_data_bucket`) are state outputs removed along with the deployment. This filtered summary omits plan configuration values. The saved plan was kept local through review and approval, then applied under T004.

The plan was presented for human review. The user explicitly approved applying this exact plan/hash in the T004 request; no replacement plan was generated.

### T004 — Approved apply and post-destroy verification (2026-11-20)

Immediately before apply, the saved plan hash still matched T003, Terraform state still listed the same seven managed resources, the Lambda/role/log group were present, and the S3 baseline was unchanged. After the user's explicit approval of the exact plan, it was applied with:

```sh
terraform -chdir=terraform apply -no-color /tmp/kite-mcp-t003-destroy.tfplan
```

Terraform reported `Apply complete! Resources: 0 added, 0 changed, 7 destroyed.` Post-destroy checks:

```sh
terraform -chdir=terraform state list
aws lambda get-function-configuration --function-name kite-mcp --region ap-south-1 --query '{FunctionName:FunctionName,State:State}' --output json
aws lambda get-function-url-config --function-name kite-mcp --region ap-south-1 --query '{FunctionUrl:FunctionUrl}' --output json
aws lambda get-policy --function-name kite-mcp --region ap-south-1 --query 'Policy' --output text
aws iam get-role --role-name kite-mcp-execution --query 'Role.RoleName' --output text
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/kite-mcp --region ap-south-1 --query 'logGroups[].logGroupName' --output json
aws s3api list-objects-v2 --bucket nse-mcp-data --prefix data/processed/ --query '[length(Contents[]),sum(Contents[].Size)]' --output json
```

`terraform state list` returned no entries. Targeted Lambda configuration, Function URL, invoke policy, and IAM role reads returned resource-not-found/no-such-entity; the CloudWatch query returned `[]`. Together with Terraform's seven-destroyed result, this confirms the seven disposable resources are absent. An account-wide `aws lambda list-functions` check was denied because this identity lacks `lambda:ListFunctions`; the targeted function check was used instead. The S3 inventory returned `[2781, 326546421]`, exactly matching the pre-destroy object and byte baseline. No S3 bucket or object was deleted. After verification, the local plan and captured Terraform logs were removed as directed by the teardown guide.

### T005 — Documentation and lineage audit (2026-11-20)

The README sequence covers architecture and S3, the Terraform Lambda and Function URL, runtime MCP discovery, a natural-language query and tool selection, Step 8 ground-truth and invalid-symbol checks, Langfuse and CloudWatch review, and saved-plan teardown. Its setup and verification commands reuse the existing Step 7/8 guides; no code edits between stages are required. The journal's evidence map distinguishes fresh observations from prior Step 7/8 evidence. The TODO lineage audit maps R001–R005 through P001–P008 to T001–T005 and the corresponding README, journal, plan-review, and post-destroy evidence. No lineage gaps or pending approval/post-destroy checks remain. Scope stayed within documentation and the explicitly approved T004 teardown; no application, test, Terraform configuration, deployment, or dataset changes were made.

### Verification record

- Implementation: T001 README sequence, T002 workflow evidence, T003 saved-plan review, and T004 approved teardown are documented above.
- Automated tests: none run for T001–T004. This documentation and infrastructure lifecycle scope adds no tests or application changes; existing tests were not rerun.
- Live verification: authenticated MCP discovery and the natural-language client query passed on 2026-11-20. Step 8 analytics, invalid-symbol, and CloudWatch checks are reused from their recorded 2026-11-19 pass.
- Langfuse: prior complete traces are verified in Step 7; the user manually inspected the current query trace in the browser on 2026-11-20 and confirmed all checklist items passed.
- Teardown: the user approved the exact T003 plan; Terraform applied it and reported seven destroyed. Post-destroy Terraform/AWS checks confirmed no managed demo resources remain, and the processed S3 inventory matches baseline. The account-wide Lambda listing was unavailable due to missing permission; targeted resource checks confirmed absence.
