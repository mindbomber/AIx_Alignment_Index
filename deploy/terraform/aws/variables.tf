variable "aws_region" {
  type = string
}

variable "name" {
  type    = string
  default = "aix"
}

variable "environment" {
  type = string
  validation {
    condition     = contains(["staging", "production"], var.environment)
    error_message = "environment must be staging or production"
  }
}

variable "vpc_id" {
  type = string
}

variable "private_subnet_ids" {
  type = list(string)
}

variable "application_security_group_id" {
  type = string
}

variable "database_username" {
  type    = string
  default = "aix"
}

variable "database_instance_class" {
  type    = string
  default = "db.t4g.medium"
}

variable "redis_node_type" {
  type    = string
  default = "cache.t4g.small"
}

variable "tags" {
  type    = map(string)
  default = {}
}
