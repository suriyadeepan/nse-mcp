# T6.5 — Publish the tested Lambda image to ECR

`scripts/deploy_lambda.sh` checks for the ECR repository, creates it if necessary, and invokes `scripts/push_lambda.sh`. The push script checks that the local `kite-mcp-lambda:local` image exists and is ARM64, authenticates Docker through the AWS CLI credential chain, pushes the image, and verifies the resulting digest. Defaults are repository `kite-mcp`, region `ap-south-1`, and tag `latest`; environment variables can override them. The scripts do not store credentials.

## IAM permission added

The AWS IAM user needed explicit ECR permissions. The policy added for the push workflow was:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "ECRPushAccess",
      "Effect": "Allow",
      "Action": [
        "ecr:DescribeRepositories",
        "ecr:CreateRepository",
        "ecr:GetAuthorizationToken",
        "ecr:BatchCheckLayerAvailability",
        "ecr:InitiateLayerUpload",
        "ecr:UploadLayerPart",
        "ecr:CompleteLayerUpload",
        "ecr:PutImage",
        "ecr:DescribeImages",
        "ecr:BatchGetImage"
      ],
      "Resource": "*"
    }
  ]
}
```

`Resource: "*"` is the scope of the supplied policy. The policy enables repository inspection/creation, registry authentication, image upload, and post-push digest verification.

Run the deployment publishing script after `scripts/build_lambda.sh`:

```bash
./scripts/deploy_lambda.sh
```

## Result

Before this permission was added, AWS CLI identity lookup succeeded but ECR repository inspection was denied in `ap-south-1`. After the policy was added, the deployment publishing steps completed successfully:

- Image URI: `025232685609.dkr.ecr.ap-south-1.amazonaws.com/kite-mcp:latest`
- Digest: `sha256:59dc577616d61164bdb0fe59c385c46fe7024e162d772bc77de2768c594ab466`

T6.5 is complete. This confirms publication to ECR; deploying Lambda remains tracked under T12.
