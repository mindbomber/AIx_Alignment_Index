# Compatibility Policy

AIx uses semantic versioning for the Python package and versioned HTTP paths.

- Additive fields and endpoints may ship in a minor release.
- Removing or renaming fields, changing meanings, or tightening accepted values
  requires a new major API version or a documented deprecation period.
- Clients must ignore unknown response fields.
- Database migrations are forward-only in production. A release documents the
  oldest application version compatible with its migrated schema.
- Published rubric versions and finalized assessments are immutable. Corrections
  create a new rubric or assessment version.
- The checked-in OpenAPI contract and generated clients must match in CI.

Security fixes may accelerate removal of unsafe behavior. Such exceptions must
be called out in release notes with migration guidance.
