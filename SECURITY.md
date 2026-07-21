# Security policy

## Supported versions

Security fixes are applied to the current `0.2.x` release line and to `main`.
Earlier untagged demonstrator states are not supported release lines.

## Reporting a vulnerability

Please report vulnerabilities privately through
[GitHub Security Advisories](https://github.com/chris-page-gov/okf-ons/security/advisories/new).
Do not include credentials, unpublished exploit details or sensitive data in a
public issue.

Include the affected release or commit, the component and source surface, a
minimal reproduction, likely impact, and any suggested mitigation. Reports are
acknowledged and assessed on a best-effort basis; this experimental project does
not make a formal response-time commitment.

## Security boundary

The published bundle and local MCP broker are metadata-only and non-executing.
They must not contain observation values, secrets or credentials. Selection
plans do not confer authorisation, and any downstream live system must recheck
source state, policy, audience, purpose and expiry.

Release checksums detect changes only when the expected checksum is obtained
through a trusted channel. They are not an authenticated signature. The
machine-readable governance release states this boundary explicitly.
