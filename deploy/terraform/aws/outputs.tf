output "evidence_bucket" {
  value = aws_s3_bucket.evidence.id
}

output "evidence_kms_key_arn" {
  value = aws_kms_key.evidence.arn
}

output "database_endpoint" {
  value = aws_db_instance.database.endpoint
}

output "database_master_secret_arn" {
  value = aws_db_instance.database.master_user_secret[0].secret_arn
}

output "redis_primary_endpoint" {
  value = aws_elasticache_replication_group.redis.primary_endpoint_address
}
