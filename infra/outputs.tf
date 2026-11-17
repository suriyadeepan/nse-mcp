output "cluster_name" {
  description = "ECS cluster hosting the MCP server"
  value       = aws_ecs_cluster.market_data_mcp.name
}

output "log_group_name" {
  description = "CloudWatch log group for server logs"
  value       = aws_cloudwatch_log_group.market_data_mcp.name
}