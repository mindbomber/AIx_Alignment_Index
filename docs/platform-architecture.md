# AIx Platform Architecture

The `aix` package remains the deterministic, paper-grounded measurement kernel.
The `aix_platform` package owns product concerns: persistence, identity,
authorization, evidence, workflow, policy, audit, and API delivery.

## Trust Boundaries

1. API clients authenticate with a random opaque bearer credential.
2. Credentials resolve to one user and one organization.
3. Tenant resources are always queried with `organization_id`.
4. Finalization validates and scores the submitted assessment, evaluates active
   policies, stores canonical JSON snapshots, and records SHA-256 hashes.
5. Each audit event includes the previous event hash for that organization,
   producing a verifiable append-only chain.

## Lifecycle

Assessments move through:

```text
draft -> in_review -> approved -> finalized
                  \-> rejected
```

Only drafts can be edited. Finalized assessments are immutable. A changed
assessment is represented as a new version linked to its predecessor.

## Storage

PostgreSQL is required in deployed environments. SQLite is supported only for
local development and isolated unit tests. Alembic owns schema evolution.

Evidence payloads use an object-store abstraction. The database stores
provenance, content hashes, classification, retention, and object keys rather
than unbounded binary content.

## Product Topology

- React/Vite web application for authoring, evidence, workflow, comparison, and
  report download.
- FastAPI API instances for synchronous tenant-scoped operations.
- Worker instances for reports, webhook delivery, retention, and privacy jobs.
- PostgreSQL as the system of record.
- Redis for distributed request admission.
- S3-compatible object storage for evidence payloads.
- Prometheus metrics and optional OTLP traces for external observability systems.
