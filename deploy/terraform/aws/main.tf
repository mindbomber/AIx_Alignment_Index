locals {
  prefix = "${var.name}-${var.environment}"
}

resource "aws_kms_key" "evidence" {
  description             = "AIx ${var.environment} evidence encryption"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}

resource "aws_kms_alias" "evidence" {
  name          = "alias/${local.prefix}-evidence"
  target_key_id = aws_kms_key.evidence.key_id
}

resource "aws_s3_bucket" "evidence" {
  bucket_prefix       = "${local.prefix}-evidence-"
  object_lock_enabled = true
}

resource "aws_s3_bucket_versioning" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    apply_server_side_encryption_by_default {
      kms_master_key_id = aws_kms_key.evidence.arn
      sse_algorithm     = "aws:kms"
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "evidence" {
  bucket                  = aws_s3_bucket.evidence.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_lifecycle_configuration" "evidence" {
  bucket = aws_s3_bucket.evidence.id
  rule {
    id     = "noncurrent-retention"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.environment == "production" ? 2555 : 365
    }
  }
}

resource "aws_security_group" "database" {
  name_prefix = "${local.prefix}-database-"
  vpc_id      = var.vpc_id
  ingress {
    protocol        = "tcp"
    from_port       = 5432
    to_port         = 5432
    security_groups = [var.application_security_group_id]
  }
  egress {
    protocol    = "-1"
    from_port   = 0
    to_port     = 0
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_db_subnet_group" "database" {
  name       = "${local.prefix}-database"
  subnet_ids = var.private_subnet_ids
}

resource "aws_db_instance" "database" {
  identifier                   = "${local.prefix}-postgres"
  engine                       = "postgres"
  engine_version               = "17"
  instance_class               = var.database_instance_class
  allocated_storage            = 50
  max_allocated_storage        = 500
  storage_encrypted            = true
  kms_key_id                   = aws_kms_key.evidence.arn
  db_name                      = "aix"
  username                     = var.database_username
  manage_master_user_password  = true
  db_subnet_group_name         = aws_db_subnet_group.database.name
  vpc_security_group_ids       = [aws_security_group.database.id]
  backup_retention_period      = var.environment == "production" ? 35 : 7
  deletion_protection          = var.environment == "production"
  multi_az                     = var.environment == "production"
  performance_insights_enabled = true
  auto_minor_version_upgrade   = true
  publicly_accessible          = false
  skip_final_snapshot          = var.environment != "production"
  final_snapshot_identifier    = var.environment == "production" ? "${local.prefix}-final" : null
}

resource "aws_security_group" "redis" {
  name_prefix = "${local.prefix}-redis-"
  vpc_id      = var.vpc_id
  ingress {
    protocol        = "tcp"
    from_port       = 6379
    to_port         = 6379
    security_groups = [var.application_security_group_id]
  }
}

resource "aws_elasticache_subnet_group" "redis" {
  name       = "${local.prefix}-redis"
  subnet_ids = var.private_subnet_ids
}

resource "aws_elasticache_replication_group" "redis" {
  replication_group_id       = "${local.prefix}-redis"
  description                = "AIx ${var.environment} distributed controls and jobs"
  node_type                  = var.redis_node_type
  port                       = 6379
  parameter_group_name       = "default.redis7"
  subnet_group_name          = aws_elasticache_subnet_group.redis.name
  security_group_ids         = [aws_security_group.redis.id]
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  automatic_failover_enabled = var.environment == "production"
  multi_az_enabled           = var.environment == "production"
  num_cache_clusters         = var.environment == "production" ? 2 : 1
  snapshot_retention_limit   = var.environment == "production" ? 7 : 1
}
