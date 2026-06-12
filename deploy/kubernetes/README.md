# Kubernetes Deployment

The manifests assume managed PostgreSQL, Redis, and S3-compatible storage.
Create an `aix-secrets` Secret outside source control with:

```text
AIX_DATABASE_URL
AIX_REDIS_URL
AIX_TOKEN_PEPPER
AIX_WEBHOOK_SECRET_PEPPER
AIX_S3_BUCKET
AIX_S3_REGION
AIX_S3_ACCESS_KEY_ID
AIX_S3_SECRET_ACCESS_KEY
AIX_S3_SERVER_SIDE_ENCRYPTION
AIX_S3_KMS_KEY_ID
AIX_CORS_ORIGINS
```

Render and validate before deployment:

```bash
kubectl kustomize deploy/kubernetes/staging
kubectl kustomize deploy/kubernetes/production
```

Run the rendered migration Job before rolling out API and worker deployments.
Replace image repositories and immutable tags with the release images used by
your registry.

For an authenticated cluster, the deployment helper performs the migration
phase first and blocks on completion before rolling workloads:

```bash
python scripts/deploy_kubernetes.py staging \
  --api-image ghcr.io/OWNER/REPO:v0.1.0 \
  --web-image ghcr.io/OWNER/REPO-web:v0.1.0 \
  --deploy
```

GitHub's `deploy` workflow uses protected `staging` and `production`
environments and expects a base64-encoded kubeconfig in `KUBECONFIG_B64`.
