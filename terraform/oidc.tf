# Real network call (not a local computation): fetches GitHub's OIDC issuer
# TLS cert so AWS can verify it is talking to the genuine issuer via the
# fingerprint below, not an impersonator.
data "tls_certificate" "github" {
  url = "https://token.actions.githubusercontent.com"
}

resource "aws_iam_openid_connect_provider" "github" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"] # the only "aud" value this provider will accept as valid
  thumbprint_list = [data.tls_certificate.github.certificates[0].sha1_fingerprint]

  tags = {
    Name = "github-action-oidc"
  }
}

data "aws_iam_policy_document" "github_actions_assume_role" {
  statement {
    effect  = "Allow"
    actions = ["sts:AssumeRoleWithWebIdentity"]

    principals {
      type        = "Federated" # not an AWS account or IAM user — an external OIDC identity provider (below)
      identifiers = [aws_iam_openid_connect_provider.github.arn]
    }

    condition {
      test = "StringEquals"
      # "<issuer-host>:<claim>" is an AWS-defined naming convention, not something
      # chosen here: AWS exposes every claim of the verified JWT under a context
      # key built from the OIDC provider's URL (above) and the claim's own name.
      variable = "token.actions.githubusercontent.com:aud"
      values   = ["sts.amazonaws.com"]
    }

    # Scoped to one repository and one branch: a workflow running anywhere else —
    # a fork, a pull request, another branch — cannot assume this role.
    condition {
      test     = "StringEquals"
      variable = "token.actions.githubusercontent.com:sub"
      values   = ["repo:${var.github_repository}:ref:refs/heads/${var.github_deploy_branch}"]
    }
  }
}

resource "aws_iam_role" "github_actions_deploy_role" {
  name               = "github-actions-airflow-deploy"
  assume_role_policy = data.aws_iam_policy_document.github_actions_assume_role.json
}

data "aws_iam_policy_document" "github_actions_deploy_policy" {
  # 1. ECR access (authentication and image push)
  statement {
    effect = "Allow"
    actions = [
      "ecr:GetAuthorizationToken"
    ]
    resources = ["*"] # GetAuthorizationToken does not support resource-level restrictions
  }

  statement {
    effect = "Allow"
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:GetDownloadUrlForLayer",
      "ecr:BatchGetImage",
      "ecr:InitiateLayerUpload",
      "ecr:UploadLayerPart",
      "ecr:CompleteLayerUpload",
      "ecr:PutImage"
    ]

    resources = [aws_ecr_repository.airflow.arn]
  }
  statement {
    effect = "Allow"
    actions = [
      "ecs:DescribeTaskDefinition",
      "ecs:RegisterTaskDefinition"
    ]
    resources = ["*"] # RegisterTaskDefinition creates a new resource, hence "*"
  }

  statement {
    effect = "Allow"
    actions = [
      "ecs:UpdateService",
      "ecs:DescribeServices"
    ]
    resources = [
      aws_ecs_service.airflow_service.id
    ]
  }

  statement {
    effect = "Allow"
    actions = [
      "iam:PassRole"
    ]
    resources = [
      aws_iam_role.ecs_execution_role.arn,
      aws_iam_role.airflow_task_role.arn
    ]
  }
}

resource "aws_iam_policy" "github_actions_deploy" {
  name   = "github-actions-airflow-deploy-policy"
  policy = data.aws_iam_policy_document.github_actions_deploy_policy.json
}

resource "aws_iam_role_policy_attachment" "github_actions_deploy" {
  role       = aws_iam_role.github_actions_deploy_role.name # this attribute takes a role NAME, not an ARN
  policy_arn = aws_iam_policy.github_actions_deploy.arn
}

output "github_actions_role_arn" {
  value       = aws_iam_role.github_actions_deploy_role.arn
  description = "ARN of the IAM Role for GitHub Actions OIDC"
}