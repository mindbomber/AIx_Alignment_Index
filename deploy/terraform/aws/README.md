# AWS Managed Dependencies

This Terraform root provisions the production data plane expected by the AIx
Kubernetes manifests:

- KMS-encrypted, versioned, object-lock-enabled evidence storage;
- private PostgreSQL 17 with managed master credentials, backups, and Multi-AZ
  in production;
- private encrypted Redis with automatic failover in production;
- security groups restricted to the application security group.

Supply an existing VPC, private subnets, and application security group:

```bash
terraform init
terraform plan \
  -var aws_region=us-east-1 \
  -var environment=staging \
  -var vpc_id=vpc-... \
  -var 'private_subnet_ids=["subnet-a","subnet-b"]' \
  -var application_security_group_id=sg-...
```

Use a remote encrypted Terraform backend with locking in hosted environments.
Database connection material should be assembled from the managed RDS secret
and injected into the external `aix-secrets` Kubernetes Secret.
