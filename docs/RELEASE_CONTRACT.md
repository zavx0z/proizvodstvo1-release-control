# React staging release contract

Date fixed: 2026-08-30  
Architecture owner: Vladimir

## 1. Authority

The only automated staging release authority is:

```text
protected public main
+ release/staging.json
```

in `zavx0z/proizvodstvo1-release-control`.

The private branch `zavx0z/proizvodstvo1:ai-dev` is the accepted staging source line but, on GitHub Free, is not itself the technical deployment authority.

## 2. Manifest schema

Canonical file:

```text
release/staging.json
```

Exact fields:

```json
{
  "schema": 1,
  "environment": "staging",
  "source_repository": "zavx0z/proizvodstvo1",
  "source_ref": "refs/heads/ai-dev",
  "source_sha": "<40 lowercase hex>",
  "sequence": 1,
  "requested_at": "<RFC3339 UTC ending in Z>",
  "summary": "<1..160 printable characters, one line>"
}
```

No additional fields are accepted.

`sequence` is monotonic and increments by exactly one for each release request. A no-op release may keep the same functional application while increasing `sequence`; this is used for controlled pipeline/rollback verification.

## 3. Release Pull Request

A normal release PR:

- originates from this repository;
- branch name is `release/staging-seq-<N>`;
- changes exactly `release/staging.json`;
- sets `<N>` equal to manifest `sequence`;
- increments the base manifest sequence by exactly one;
- does not change workflow, docs or policy files.

The trusted-base `Release manifest guard` validates this without using secrets.

## 4. Maintenance Pull Request

A maintenance PR:

- branch starts with `maintenance/`;
- originates from this repository;
- author is `zavx0z`;
- never changes `release/staging.json` in the same PR;
- may change only control paths explicitly allowed by the existing base guard.

`Release manifest guard` executes from the protected base. `Release-control code self-test` executes the proposed maintenance code. Both are required by branch protection.

## 5. Publish trigger

Canonical workflow:

```text
.github/workflows/publish-staging.yml
```

It runs only on a `push` to protected `main` when `release/staging.json` changes. Maintenance merges do not trigger application publication.

The workflow uses GitHub-hosted ephemeral runners only. It is additionally blocked unless the separately configured repository variable is exactly:

```text
P1_STAGING_PUBLISH_ENABLED=true
```

This variable is an operational gate, not a replacement for branch protection.

## 6. Private source proof

The publisher checks out only:

```text
zavx0z/proizvodstvo1
branch: ai-dev
```

through a dedicated read-only deploy key.

It then proves:

```text
checked-out ai-dev HEAD == release/staging.json:source_sha
```

If they differ, publication stops before application checks, image build or deployment.

Required source-side release files include:

```text
app/ai/Dockerfile.release
app/ai/ops/staging-smoke.sh
```

Therefore source-side release-contract PR #6 must be accepted into `ai-dev` before the first GHCR publication can succeed. This does not authorize `proizvodstvo1/main` or production cutover.

## 7. Application gates

The GitHub-hosted publisher repeats application checks with the pinned Bun 1.4.0 image:

```text
oven/bun:1.4.0-debian@sha256:0e74e9bd11cf47eb67ac4d8698ed1b10d378fa4a5f4a5f1146556087649b607f
```

At minimum:

- frozen root install;
- toolchain verify;
- root TypeScript check;
- Institute tests;
- legacy portal build compatibility;
- React install/tests/typecheck/production build.

No Artel, SSO, Email, WebRTC or general platform release suite is part of this application publish.

## 8. Image build and GHCR

The only target package is:

```text
ghcr.io/zavx0z/proizvodstvo1-react-portal
```

The GitHub-hosted job uses only its job-scoped `GITHUB_TOKEN` with `packages: write`; no long-lived GHCR push PAT is stored in the public repository.

Candidate traceability tags:

```text
seq-<sequence>
sha-<source_sha>
```

After successful full smoke and VPS commit, the same manifest also receives:

```text
deployed-seq-<sequence>
```

Deployment itself always uses:

```text
ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:<digest>
```

Attestations are disabled for staging v1 to avoid untagged manifest accumulation; source SHA, release sequence, OCI revision label, image digest and GitHub workflow evidence form the staging provenance chain.

## 9. Transactional VPS deployment

The public workflow never has an arbitrary VPS shell. A dedicated SSH key is restricted server-side to the reviewed root-owned wrapper in:

```text
ops/p1-react-staging-deploy.sh
```

The wrapper owns only Compose project:

```text
proizvodstvo1-react-staging
```

and service:

```text
portal
```

while also proving the staging Nginx container identity does not change.

Deployment has three phases:

```text
deploy IMAGE
  -> pull exact GHCR digest
  -> disk guard
  -> update portal only
  -> health
  -> PENDING_IMAGE

GitHub full staging smoke

commit IMAGE
  -> finalize current/rollback/safety ring
  -> exact bounded VPS image cleanup
```

If full smoke fails:

```text
rollback PREVIOUS_CURRENT
```

restores the previously committed image before the rollback ring is rotated.

A runner crash after `deploy` leaves explicit pending state and blocks the next release with `PENDING_RECOVERY_REQUIRED` rather than silently overwriting evidence.

## 10. Bounded cleanup

Cleanup is mandatory both before build and after a successful committed deployment.

GHCR policy is implemented by:

```text
scripts/ghcr_cleanup.py
.github/workflows/ghcr-cleanup.yml
```

The scheduled cleanup job runs only when:

```text
P1_STAGING_MAINTENANCE_ENABLED=true
```

It queries the restricted VPS `state` command and protects every GHCR digest referenced by live/current/rollback/safety/pending/blocked state.

The next release is blocked when cleanup returns:

```text
CLEANUP_BLOCKED
```

No global Docker prune command is permitted.

## 11. Credential boundaries

Expected narrow credentials and variables are documented in `docs/SECURITY.md` and installed only through a separate external task after this control-code PR is reviewed.

No secret, key, GHCR package permission or VPS configuration is created by merging the control-code PR itself.

## 12. Never part of ordinary staging publish

- `zavx0z/proizvodstvo1/main`;
- Production №1 containers/images;
- Artel;
- central ingress;
- staging Nginx recreation/restart;
- DNS;
- TLS;
- global Docker cleanup.

Production cutover is a separate Vladimir-authorized operation.
