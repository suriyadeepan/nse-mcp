variable "name" {
  description = "Name prefix for all created resources"
  type        = string
  default     = "market-data-mcp"
}

variable "region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1"
}

variable "log_retention_days" {
  description = "CloudWatch log retention in days"
  type        = number
  default     = 14
}

variable "container_image" {
  description = "Container image for the MCP server"
  type        = string
  default     = ""
}

variable "desired_count" {
  description = "Number of server tasks to run"
  type        = number
  default     = 1
}