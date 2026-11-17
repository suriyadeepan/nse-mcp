terraform {
  required_version = ">= 1.6"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = var.region
}

resource "aws_ecs_cluster" "market_data_mcp" {
  name = "${var.name}-cluster"
}

resource "aws_cloudwatch_log_group" "market_data_mcp" {
  name              = "/ecs/${var.name}"
  retention_in_days = var.log_retention_days
}