# Release-control security boundary

The public release-control repository contains only public metadata and reviewed control code. Application source, client data and credentials remain private.

## Trust chain

```text
protected public main
  -> exact release/staging.json
  -> restricted VPS state preflight
  -> read-only private-source deploy key
  -> exact ai-dev HEAD == manifest source_sha
  -> immutable git-archive snapshot
  -> repeated application checks in isolated container
  -> untouched second build snapshot
  -> private GHCR package
  -> immutable image digest
  -> restricted forced-command VPS deployment
  -> protected control-side full smoke
  -> transactional commit or rollback
  -> exact bounded cleanup
```

## Public information

The following may be public:

- release sequence;
- source commit SHA;
- image digest;
- staging release timestamps;
- workflow/check status;
- non-secret cleanup evidence.

No application source content is copied into this repository.

## GitHub Actions secrets and variables

Secrets are environment-scoped, never repository-scoped. Both environments must
be restricted to protected branches only before any enabling variable is set.

Exact map:

```text
p1-source-build
  P1_SOURCE_DEPLOY_KEY
  deployment branches: protected branches only

p1-vps-deploy
  P1_VPS_DEPLOY_KEY
  P1_VPS_KNOWN_HOSTS
  deployment branches: protected branches only
```

No other job environment may receive these secrets. The environments and their
secrets are external installation state and are not created by this code patch.

Expected non-secret repository variables:

```text
P1_STAGING_BUILD_ONLY_ENABLED
P1_STAGING_PUBLISH_ENABLED
P1_STAGING_MAINTENANCE_ENABLED
P1_VPS_DEPLOY_HOST
P1_VPS_DEPLOY_USER
```

All enabling variables remain false or absent until the corresponding installation/acceptance stage is complete.

### Private source key

`P1_SOURCE_DEPLOY_KEY` is a read-only deploy key bound only to `zavx0z/proizvodstvo1`. It has no write permission and no access to other repositories.

The build job checks out only branch `ai-dev`, proves its exact HEAD equals `release/staging.json:source_sha`, and immediately creates a Git archive snapshot.

Two independent directories are extracted from the same frozen archive:

```text
p1-test-source
p1-build-source
```

Application tests may mutate only `p1-test-source`. The Docker release image is built only from the untouched `p1-build-source`, so test-side mutation cannot alter the image candidate.

The source tree rejects Git symlinks/submodules before extraction.

### VPS key

`P1_VPS_DEPLOY_KEY` authenticates only a dedicated staging deploy account. Its public key is restricted server-side to the fixed root-owned forced command documented in `ops/README.md`.

Possession of this key must not allow:

- interactive shell;
- arbitrary sudo;
- arbitrary Docker command;
- Production №1 mutation;
- Artel mutation;
- central ingress mutation;
- DNS/TLS mutation;
- arbitrary image repository.

### GHCR write access

No long-lived GHCR push PAT is stored in this repository. Candidate build and package maintenance use the job-scoped `GITHUB_TOKEN` with `packages: write`.

The workflow explicitly checks after push that the package visibility is `private` before any live deployment can proceed.

The VPS uses a different pull-only GHCR credential stored only on the VPS. The public workflow never receives the VPS GHCR pull credential.

## Secret separation by job

The publisher deliberately separates credentials across jobs.

### `vps-preflight`

Uses environment `p1-vps-deploy` and has access to the restricted VPS key only.
It has no private-source deploy key and no application source checkout.

### `build`

Uses environment `p1-source-build`, has the private-source deploy key and
job-scoped GHCR write token. It never receives the VPS private key. It produces
an immutable digest and candidate only.

### `deploy`

Uses environment `p1-vps-deploy` and checks out only protected public
release-control code. It has the restricted VPS key but no private application
source checkout and executes no private-source shell script on the host.

### `finalize`

Uses only protected public release-control code plus the job-scoped GHCR token. It receives committed VPS ring digests as job outputs and never receives the VPS key or private-source key.

This prevents one source-controlled application test or Docker build from running in the same job that holds the VPS deployment key.

## Trusted full staging smoke

The full post-deployment smoke is embedded in the protected public `publish-staging.yml`, not taken from `ai-dev`.

It verifies:

- `/health` 200, `status=ok`, `seoIndexable=false`;
- `/`, `/request`, `/institute` return 200;
- public HTML responses carry `X-Robots-Tag: noindex, nofollow`;
- no not-found fallback appears;
- `/robots.txt` permits crawling so noindex can be observed and also carries the noindex header;
- `/sitemap.xml` is 404 while staging is non-indexable.

The same protected smoke is repeated after rollback before a failed release terminates.

## Build-only GHCR bootstrap

`workflow_dispatch` supports only one manual mode:

```text
build-only
```

It requires:

```text
P1_STAGING_BUILD_ONLY_ENABLED=true
```

This mode may validate the private-source key, build the exact candidate, create/verify the private GHCR package and run image health checks, but it has no VPS deployment job. It is the intended first package-bootstrap path.

The dispatch caller must provide `source_sha` as exactly 40 lowercase hex. The
workflow proves it equals the current remote `refs/heads/ai-dev` HEAD. Build-only
does not read or derive any value from `release/staging.json`; it emits only:

```text
bootstrap-sha-<source_sha>
sha-<source_sha>
```

and leaves the deployed tag empty.

The candidate remains under the normal 48-hour cleanup grace window and does not receive a `deployed-seq-*` tag.

## Transactional deployment

A normal manifest push uses the root-owned wrapper transaction:

```text
deploy IMAGE
  -> PENDING_IMAGE
  -> portal health only

protected GitHub full smoke

commit IMAGE
  -> rotate current / rollback / safety
```

If full smoke fails:

```text
rollback PREVIOUS_CURRENT
```

restores the previous committed image without rotating the rollback ring.

A repeated publication of the already-current immutable digest is treated as a no-op transaction and does not duplicate or corrupt the rollback/safety ring.

Any ambiguous crash state leaves either an explicit pending state or a live/current mismatch and blocks the next release for manual recovery.

## Workflow hardening

- GitHub-hosted ephemeral runners only;
- no self-hosted release runner;
- third-party Actions are not required;
- every `actions/checkout` use is pinned by full commit SHA;
- publish on `push` to protected `main` only when `release/staging.json` changes;
- manual mode is build-only and cannot deploy;
- no Actions cache or uploaded binary artifacts;
- staging BuildKit SBOM/provenance side manifests disabled to keep retention deterministic;
- all resulting live deployment references use full `@sha256:<digest>`;
- temporary SSH files live only in `RUNNER_TEMP` and are deleted in `if: always()` cleanup;
- Docker authentication is removed in `if: always()` cleanup;
- deployment and final GHCR metadata operations are separated into different jobs.

## Branch protection

Public `main` is the release authority and is independently verified protected with:

- PR required;
- approvals required: 0;
- strict required status checks;
- exact checks `Release manifest guard` and `Release-control code self-test`;
- force push disabled;
- branch deletion disabled;
- administrator bypass disabled;
- conversation resolution enabled;
- linear history enabled.

If these properties change, publication must stop.

## Stop conditions

Publication is blocked when any of the following is true:

- source deploy key missing or broader than read-only access to the one private source repository;
- `ai-dev` HEAD differs from manifest `source_sha`;
- application checks fail;
- GHCR package visibility is not proven private;
- VPS pull permission is not limited to the expected package;
- VPS forced-command restriction is not proven;
- VPS ring drifts between preflight and deployment;
- VPS reports pending or blocked cleanup state;
- disk guard fails;
- GHCR or VPS cleanup returns `CLEANUP_BLOCKED`;
- immutable digest cannot be resolved;
- trusted full smoke fails and rollback cannot be proven healthy.
