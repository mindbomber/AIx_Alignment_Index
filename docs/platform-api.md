# Platform API And Integrations

The versioned REST API is defined by [`spec/openapi.json`](../spec/openapi.json).
Errors use:

```json
{"error": {"code": "invalid_request", "message": "...", "context": {}}}
```

## Authentication

Password login and OIDC issue expiring opaque bearer sessions. API keys are
created with `POST /v1/api-keys`. Store returned credentials in a secret manager;
the service stores only a peppered hash and cannot recover a credential.

OIDC requires issuer discovery, client credentials, callback URI, and optionally
`AIX_OIDC_WEB_APP_URL`. The callback verifies provider user information and
verified email status. Automatic provisioning is disabled by default. When the
web app URL is configured, the callback returns the token in a URL fragment,
which the SPA removes after placing it in session storage.

## Python Client

```python
from aix_client import AIxClient

with AIxClient("https://aix.example.com", token) as client:
    systems = client.call("list_systems_v1_systems_get")
```

Operation IDs and paths are generated from OpenAPI by
`scripts/generate_api_clients.py`.

## TypeScript Client

```ts
import { AIxClient } from '@aix-open/client'

const client = new AIxClient('https://aix.example.com', token)
const systems = await client.call('list_systems_v1_systems_get')
```

The package source is in `clients/typescript`.

## Evidence

Evidence can reference an external URI with a caller-supplied SHA-256 digest or
be uploaded as multipart data. Uploaded content is streamed through a bounded
temporary file, hashed by the server, and stored under a tenant-prefixed object
key. Downloads require tenant authorization.

## Reports And Export

`POST /v1/jobs` creates an idempotent report job for a finalized assessment.
Workers generate Markdown, JSON, CSV, or HTML. `POST /v1/privacy/exports`
creates an asynchronous organization export that excludes password hashes,
credential hashes, and encrypted webhook secrets.

The measurement CLI also imports YAML/JSON assessments and exports JSON/CSV:

```bash
aix validate assessment.yaml
aix export assessment.yaml --format json --out assessment.json
```

## Webhooks

Create endpoints with `POST /v1/webhooks`. The signing secret is returned once.
Deliveries include:

```text
X-AIx-Event-ID
X-AIx-Event-Type
X-AIx-Timestamp
X-AIx-Signature: sha256=<hex digest>
```

Verify the HMAC-SHA256 over `<timestamp>.<raw request body>`, reject stale
timestamps, and deduplicate by event ID. Production endpoints must use HTTPS and
must not resolve to private, loopback, link-local, multicast, or reserved
addresses. Destination safety is rechecked for every delivery.

## Privacy And Retention

Owners and admins can request exports, schedule delayed organization deletion,
and cancel pending deletion. The worker removes expired evidence according to
retention metadata. Production object storage should also use versioning and
lifecycle controls consistent with the organization's retention policy.
