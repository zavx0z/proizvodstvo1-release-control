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

`sequence` increments by exactly one for each release request. A functionally no-op release may keep the same source SHA while increasing `sequence`; this is used for controlled release-path and rollback verification.

## 3. Release Pull Request

A normal release PR:

- originates from this repository;
- branch name is `release/staging-seq-<N>`;
- changes exactly `release/staging.json`;
- sets `<N>` equal to manifest `sequence`;
- increments base sequence by exactly one;
- does not change workflow, docs or policy files.

The trusted-base `Release manifest guard` validates this without secrets.

## 4. Maintenance Pull Request

A maintenance PR:

- branch starts with `maintenance/`;
- originates from this repository;
- author is `zavx0z`;
- never changes `release/staging.json` in the same PR;
- may change only control paths explicitly allowed by the existing base guard.

The base `Release manifest guard` evaluates the PR through `pull_request_target`. The proposed control code is separately exercised by `Release-control code self-test`. Both are required by protected public `main`.

## 5. Publish modes

Canonical workflow:

```text
.github/workflows/publish-staging.yml
```

There are only two modes.

### Normal publication

A normal publication starts only on `push` to protected `main` when `release/staging.json` changes and additionally requires:

```text
P1_STAGING_PUBLISH_ENABLED=true
```

### GHCR build-only bootstrap

Manual `workflow_dispatch` supports only:

```text
mode=build-only
```

and requires:

```text
P1_STAGING_BUILD_ONLY_ENABLED=true
```

Build-only validates source access, repeats application gates, builds the exact image, creates/verifies the private GHCR package and tests the image. It has no VPS deployment job and cannot mutate live staging.

The dispatch also requires:

```text
source_sha=<exact 40 lowercase hex current refs/heads/ai-dev SHA>
```

The preflight reads the current remote `ai-dev` HEAD and requires both the
checked-out HEAD and explicit `source_sha` to equal it. Build-only does not read
`release/staging.json`, does not use its sequence or source SHA, and produces an
empty deployed tag. Deploy and finalize jobs remain skipped.

## 6. Private source proof and immutable snapshots

The build job checks out only:

```text
zavx0z/proizvodstvo1
branch: ai-dev
```

through a dedicated read-only deploy key. Normal publication proves:

```text
checked-out ai-dev HEAD == release/staging.json:source_sha
```

Build-only instead proves:

```text
checked-out ai-dev HEAD
== current remote refs/heads/ai-dev HEAD
== explicit workflow_dispatch source_sha
```

If they differ, publication stops before image build or deployment.

Required source release files are:

```text
app/ai/Dockerfile.release
app/ai/Dockerfile.release.dockerignore
```

Therefore source-side PR #6 must be separately accepted into `ai-dev` before the first GHCR build can succeed. This is not a merge into private `main` and not production cutover.

The workflow rejects Git symlinks/submodules, freezes the accepted source SHA into one `git archive`, then extracts two independent snapshots:

```text
p1-test-source
p1-build-source
```

Application checks run only against the test snapshot. The release image is built only from the untouched build snapshot created from the same frozen archive after the tests. Test mutation therefore cannot alter the build context.

## 7. Application gates

Checks run with pinned Bun:

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

No Artel, SSO, Email, WebRTC or platform-wide release suite is part of ordinary application publish.

## 8. Image build and GHCR

Only this package is allowed:

```text
ghcr.io/zavx0z/proizvodstvo1-react-portal
```

The GitHub-hosted build job uses its job-scoped `GITHUB_TOKEN` with `packages: write`; no long-lived GHCR push PAT is stored in the public repository.

Candidate traceability tags:

```text
seq-<sequence>
sha-<source_sha>
```

Build-only has no release sequence and uses exactly:

```text
bootstrap-sha-<source_sha>
sha-<source_sha>
```

It never creates a `deployed-seq-*` tag.

Before any deployment, the workflow verifies through GitHub Packages API that the package visibility is exactly `private`.

After a successful committed deployment, the finalize job adds:

```text
deployed-seq-<sequence>
```

to the same immutable digest and verifies the tag did not change that digest.

Deployment itself always uses:

```text
ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:<digest>
```

Staging v1 disables BuildKit SBOM/provenance side manifests to avoid untagged OCI accumulation. Staging provenance remains bounded to sequence, source SHA, OCI revision label, image digest and GitHub workflow evidence.

## 9. Secret isolation by job

The normal pipeline is split so application source and VPS deployment credentials never coexist in the same job:

```text
vps-preflight
  -> restricted VPS key, public control code only

build
  -> private-source read-only key + job-scoped GHCR token
  -> no VPS private key

deploy
  -> restricted VPS key, protected public control code only
  -> no private source checkout

finalize
  -> job-scoped GHCR token + protected public control code
  -> no VPS key and no private source key
```

## 10. Transactional VPS deployment

The public workflow never has an arbitrary VPS shell. A dedicated SSH key is restricted to the reviewed root-owned wrapper:

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

while proving the configured staging Nginx container does not change.

The committed ring is not rotated until the protected full smoke succeeds:

```text
deploy IMAGE
  -> pull exact digest
  -> disk guard
  -> update portal only
  -> health
  -> record pending

trusted public-control full smoke

commit IMAGE
  -> rotate current / rollback / safety
  -> exact bounded VPS image cleanup
```

If full smoke fails:

```text
rollback PREVIOUS_CURRENT
```

restores the previously committed image and preserves the pre-release rollback/safety ring.

A repeated release of the already-current immutable digest is handled as a no-op transaction and does not duplicate the rollback ring.

A crash or ambiguous live/state mismatch blocks later release attempts for explicit recovery.

## 11. Trusted full smoke

Host-level full smoke belongs to protected release-control code, not private `ai-dev` shell scripts.

It verifies:

- `/health` = 200, status `ok`, `seoIndexable=false`;
- `/`, `/request`, `/institute` = 200;
- `X-Robots-Tag: noindex, nofollow` on staging pages;
- no not-found fallback;
- `/robots.txt` = 200, contains `User-agent: *` and `Allow: /`, does not contain `Disallow: /`, and exposes the noindex header;
- `/sitemap.xml` = 404.

The same trusted smoke runs after rollback before a failed deployment exits.

## 12. Bounded cleanup

Cleanup is mandatory before normal source build and after a successful committed deployment.

GHCR policy is implemented by:

```text
scripts/ghcr_cleanup.py
.github/workflows/ghcr-cleanup.yml
```

The scheduled cleanup job is inert unless:

```text
P1_STAGING_MAINTENANCE_ENABLED=true
```

It protects every GHCR digest referenced by VPS live/current/rollback/safety/pending/blocked state.

The next release is blocked when cleanup returns:

```text
CLEANUP_BLOCKED
```

No broad Docker prune or Compose down is ever permitted.

## 13. External installation remains separate

Credentials, package permissions and root-owned VPS installation are created only through a separate external Codex task after this control-code PR is reviewed and separately authorized for merge.

Merging this maintenance PR alone creates no secrets, keys, GHCR package or VPS changes and does not trigger publication because `release/staging.json` is unchanged.

## 14. Never part of ordinary staging publish

- `zavx0z/proizvodstvo1/main`;
- Production №1 containers/images;
- Artel;
- central ingress;
- staging Nginx recreation/restart;
- DNS;
- TLS;
- global Docker cleanup.

Production cutover is a separate Vladimir-authorized operation.
