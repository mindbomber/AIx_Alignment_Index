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

The `staging` GitHub environment also requires:

```text
KUBECONFIG_B64
AIX_E2E_ORG
AIX_E2E_EMAIL
AIX_E2E_PASSWORD
```

The configurator creates a namespace-scoped `aix-deployer` service account and
stores its kubeconfig in GitHub. Before deployment,
create `aix-secrets` in the `aix-staging` namespace with the values
listed above. The database principal should be allowed to create and drop the
temporary `<database>_restore_drill` database used by staging acceptance.
Private GHCR packages also require a cluster image-pull secret or equivalent
registry integration.

After copying `.env.staging.example` to the ignored `.env.staging` file and
filling its values, configure both Kubernetes and GitHub in one command:

```powershell
.\scripts\configure_staging.ps1 -EnvFile .env.staging
```

Use `-KubeContext CONTEXT_NAME` when the desired cluster is not already active.

Publish a release candidate, deploy it, and run acceptance:

```bash
gh workflow run candidate.yml --ref codex/productize-aix-platform \
  -f tag=v0.2.0-rc.1
gh workflow run deploy.yml --ref codex/productize-aix-platform \
  -f environment=staging -f tag=v0.2.0-rc.1
gh workflow run staging-acceptance.yml \
  --ref codex/productize-aix-platform
```
