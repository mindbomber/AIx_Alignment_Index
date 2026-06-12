# AIx Operations Runbook

## Service Objectives

- API availability target: 99.9% per calendar month.
- API p95 latency target: under 500 ms excluding uploads and report jobs.
- Recovery point objective: 15 minutes.
- Recovery time objective: 4 hours.

These are operating targets, not guarantees.

## Dependencies

Production requires PostgreSQL with point-in-time recovery, Redis, private
S3-compatible object storage with versioning, and an OpenTelemetry collector.
The API must run with `AIX_ENVIRONMENT=production`; startup validation rejects
local object storage, missing Redis, and development secrets.

## Deployment

1. Build immutable API and web images from a signed release tag.
2. Run `aix-db upgrade head` as a one-shot migration job.
3. Run smoke tests against `/health/ready`, `/v1/me`, and a test assessment.
4. Roll out workers, API, then web. Keep the previous image available.
5. Verify error rate, p95 latency, job backlog, and webhook failures.

Do not automatically downgrade a database after a failed application rollout.
Roll the application back only when the previous version supports the migrated
schema. Otherwise apply a reviewed forward-fix migration.

## Alerts

Page the service owner for:

- readiness failure for five minutes;
- HTTP 5xx rate above 2% for ten minutes;
- p95 latency above one second for fifteen minutes;
- pending jobs older than ten minutes;
- failed webhook deliveries above 10% for fifteen minutes;
- PostgreSQL storage, replication, or backup failure;
- Redis unavailability;
- object-store write failure.

## Backup And Restore

PostgreSQL must use encrypted daily snapshots plus continuous WAL archiving.
The object bucket must enable versioning and lifecycle retention. Configuration
and release manifests must be retained with the backup.

Quarterly restore drill:

1. Provision an isolated database and bucket.
2. Restore PostgreSQL to the selected timestamp.
3. Restore or expose the matching versioned object prefix.
4. Deploy the exact release recorded in the backup manifest.
5. Run `alembic check`, tenant-isolation tests, and a finalized-report smoke test.
6. Verify evidence hashes against stored objects and audit-chain integrity.
7. Record actual RPO/RTO and remediate misses.

`scripts/restore_drill.sh` verifies schema and seeded organization/assessment
data against an isolated restore database. `scripts/s3_restore_drill.py`
exercises encrypted object backup, deletion, restoration, and hash validation
against an isolated S3-compatible service in CI. Provider point-in-time version
selection remains part of the quarterly hosted-environment drill.

## Load Smoke Test

Run a low-cost authenticated read test after deployment:

```bash
python scripts/load_smoke.py --token "$AIX_SMOKE_TOKEN"
```

This is a release smoke test, not a substitute for workload-specific capacity
testing. Tune concurrency and thresholds to the deployment's service objective.

CI runs 500 authenticated requests at concurrency 25 and fails above a 1%
error rate or 1.5 second p95. Production release qualification should use
representative assessment and evidence workloads at expected peak traffic.

## Security And Accessibility Gates

`scripts/security_probe.py` runs authenticated and unauthenticated live probes
for token injection, route traversal, metadata-service SSRF, SCIM authorization,
unsafe HTTP methods, and required response headers. Browser E2E tests run axe
against the assessment and systems surfaces and fail on serious or critical
WCAG 2.1 AA violations. These automated checks supplement, rather than replace,
an independent penetration test before a major public or enterprise release.

Never run a restore drill against production endpoints or credentials.

## Incident Response

1. Declare severity and assign incident commander.
2. Preserve logs, audit records, release identifiers, and affected tenant IDs.
3. Revoke exposed credentials and rotate peppers through a coordinated
   credential invalidation procedure.
4. Contain writes if integrity is uncertain.
5. Restore service, document customer impact, and complete a blameless review.

Security reports follow [SECURITY.md](../SECURITY.md). General support follows
[SUPPORT.md](../SUPPORT.md).
