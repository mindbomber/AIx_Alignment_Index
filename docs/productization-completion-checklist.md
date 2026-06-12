# AIx Productization Completion Checklist

This checklist defines engineering completion for a production-capable AIx
service. It does not claim empirical validation or regulatory certification.

## Requested Capability Audit

- [x] Enterprise OIDC/SSO, SCIM, MFA, invitations, and role-management UI.
- [x] S3-compatible evidence uploads, AES-256 or customer-managed KMS
      encryption, malware scanning, retention, and legal holds.
- [x] Redis-backed rate limiting, distributed jobs, and session controls.
- [x] OpenTelemetry, Prometheus metrics, structured logging, and alert rules.
- [x] Privacy export/deletion and legal-hold workflows.
- [x] Systems, rubrics, policies, audit, comparison, and reports web screens.
- [x] Webhooks and generated Python and TypeScript client operation maps.
- [x] Automated load, security-probe, backup/restore, disaster-recovery, and
      accessibility test harnesses.
- [x] Terraform infrastructure, Kubernetes staging/production overlays,
      migration-first deployment automation, and container release workflows.
- [x] Reproducible calibration tooling, dataset schemas, development benchmark,
      holdout metrics, and reliability analysis.

Independent penetration testing, a real hosted rollout, and collection of
independent empirical validation datasets are execution and research gates.
The repository provides the engineering required to perform them but does not
represent that those external activities have occurred.

## Platform

- [x] PostgreSQL is the production system of record, with tested migrations.
- [x] Every customer-owned record is tenant-scoped and tenant isolation is tested.
- [x] The versioned REST API publishes an OpenAPI contract and stable error format.
- [x] Authentication supports expiring sessions, revocation, API keys, and OIDC SSO.
- [x] RBAC covers owner, admin, assessor, reviewer, approver, and viewer roles.
- [x] Finalized assessments are immutable, hashed, attributable, and auditable.
- [x] Rubrics and scoring configurations are versioned and publishable.
- [x] Evidence has provenance, integrity hashes, retention metadata, and object storage.
- [x] Policies can gate approval using score, domain, evidence, confidence, and review rules.
- [x] Long-running work uses durable jobs with retry and idempotency controls.

## User Product

- [x] The web application supports system registration, assessment authoring,
      evidence management, review, approval, comparison, and reporting.
- [x] Accessibility, responsive layout, empty/error/loading states, and browser
      tests cover the critical workflow.
- [x] Python and TypeScript clients are generated or contract-tested.
- [x] Import/export and webhook integrations are documented and tested.

## Operations And Security

- [x] Configuration is environment-based and secrets are never stored in source.
- [x] Structured logs, metrics, traces, health checks, and alerting are available.
- [x] Rate limits, request limits, CORS, secure headers, and abuse controls are enforced.
- [x] Dependency, secret, static, and container scans run in CI.
- [x] Data export, retention, deletion, and privacy workflows are implemented.
- [x] Backups and point-in-time recovery are documented and restore-tested.
- [x] Container and infrastructure deployment manifests have staging and production paths.
- [x] Load, migration, disaster-recovery, and tenant-isolation tests pass.

## Release

- [ ] Package artifacts are reproducible and published with trusted publishing.
- [x] Database and API compatibility policies are documented.
- [ ] A release candidate passes local and remote CI, security checks, and acceptance tests.
- [x] Operational runbooks and a support/escalation process are present.
- [x] Product limitations clearly separate measurement software from validated certification.

The two remaining release items require external GitHub/PyPI configuration and
a tagged remote release. Reproducible local artifacts and the trusted-publishing
workflow are implemented; they are not marked complete until a release is
actually published and remote CI is green.
