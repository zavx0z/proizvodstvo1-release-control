# Retention and cleanup policy

Cleanup is a release invariant, not an optional maintenance task.

The release system must remain bounded and must never use broad prune commands that can affect Production №1, Artel, ingress or unrelated images.

## 1. Public release-control repository

Keep only one current release request file:

```text
release/staging.json
```

History is provided by Git, not duplicated as per-release JSON files.

Repository policy:

- merged head branches are auto-deleted;
- squash merge only;
- GitHub Actions logs/artifacts retention: 7 days;
- no `actions/cache`;
- no uploaded binary artifacts;
- no GitHub Releases for staging images;
- no OCI/Docker archive committed or uploaded;
- no generated reports stored as repository files.

## 2. GitHub-hosted build workspace

The publish system uses GitHub-hosted ephemeral runners only.

Rules:

- all temporary SSH/key/config files live under `RUNNER_TEMP`;
- SSH files are mode 0600 and removed in `if: always()` cleanup;
- Docker login is logged out before the job ends;
- test containers use `--rm`;
- Buildx pushes directly and does not load a persistent local release image;
- no persistent build cache is uploaded;
- no workflow artifact contains application source or an OCI archive.

No self-hosted build workspace is used, so checkout, `node_modules`, BuildKit state and temporary containers disappear with the GitHub-hosted VM.

## 3. Private GHCR package

Canonical package:

```text
ghcr.io/zavx0z/proizvodstvo1-react-portal
```

Deployment always uses a full digest. Tags exist only for traceability and retention.

Candidate tags:

```text
seq-<N>
sha-<source-sha>
```

A successfully committed deployment additionally points:

```text
deployed-seq-<N>
```

to the same immutable manifest.

Retention target:

- keep the 5 most recent versions carrying a successful `deployed-seq-*` tag;
- always keep versions younger than 48 hours as a race-safety grace window;
- always keep every GHCR digest referenced by VPS live/current/rollback/safety/pending/blocked state;
- failed/orphan candidate versions older than 48 hours are eligible for deletion;
- successful deployed versions older than the newest retained five are eligible only when not referenced by VPS state;
- never delete a version with an unknown tag shape; report `CLEANUP_BLOCKED` instead;
- delete only versions of the exact package above;
- cap cleanup to 50 package-version deletions per run.

A cleanup workflow runs after successful publication and daily when `P1_STAGING_MAINTENANCE_ENABLED=true`.

If more than 50 eligible versions remain or any inventory entry cannot be classified safely, cleanup returns:

```text
CLEANUP_BLOCKED
```

and the next release is blocked. Do not fall back to broad deletion.

## 4. Staging provenance and attestations

Staging v1 deliberately publishes no separate BuildKit SBOM/provenance attestations because they can create additional untagged OCI manifests that complicate exact retention.

Staging provenance is instead bounded to:

```text
release sequence
source SHA
OCI revision label
immutable image digest
GitHub workflow result
deployed-seq tag
health/smoke evidence
```

Production attestation policy is a separate cutover decision.

## 5. VPS committed ring

The React staging host keeps a bounded committed three-image ring:

```text
current
rollback
safety
```

The wrapper also permits at most one temporary `pending` image during a transaction and at most one `blocked` image when an exact deletion could not be proven safe.

A normal successful transaction is:

```text
A=current, B=rollback, C=safety

deploy N
  -> live=N, pending=N
  -> committed ring remains A/B/C

full GitHub smoke

commit N
  -> current=N
  -> rollback=A
  -> safety=B
  -> C becomes exact deletion candidate
```

If full smoke fails before commit:

```text
rollback A
```

restores live=A and leaves the committed A/B/C ring intact. The failed pending image becomes the only exact deletion candidate.

This means the safety image is never discarded before full smoke succeeds.

## 6. VPS exact image cleanup

The outgoing image is removed only after proving:

- its reference matches the allowed Proizvodstvo1 React staging repositories;
- it is not current/rollback/safety/pending;
- its Docker image ID is not used by any running container.

If exact deletion fails or safety cannot be proven, the wrapper stores:

```text
BLOCKED_IMAGE=<exact immutable ref>
```

reports:

```text
CLEANUP_STATUS=CLEANUP_BLOCKED
```

and refuses the next deployment until that exact image can be removed safely.

Never use:

```text
docker system prune
docker image prune -a
docker volume prune
docker compose down
```

Do not remove unrelated images, volumes, networks, caches or containers.

## 7. VPS temporary state

All release temporary files live under a dedicated root-owned release state directory.

Rules:

- use `mktemp` inside that directory;
- temp names use the `.p1tmp.*` prefix;
- no symlink traversal;
- stale temp cleanup is limited to root-owned regular files with that exact prefix older than 24 hours;
- if ownership/path safety cannot be proven, do not delete and return an error.

Persistent state contains only:

```text
current
rollback
safety
pending
blocked image
latest 100 audit ledger lines
```

The ledger is truncated to the most recent 100 records after every write.

## 8. Logs

React staging container logs must use bounded Docker log rotation. Target contract:

```text
max-size: 10m
max-file: 5
```

Existing staging Nginx and central ingress logging are outside ordinary application publish. Their retention must be checked read-only before automation is enabled; changes require a separate infrastructure task.

## 9. Disk guard

Before pulling a new staging image, the root-owned wrapper checks free space against the fixed `MIN_FREE_KB` configured outside GitHub.

`MIN_FREE_KB` must be at least 1 GiB; the installation task should choose a larger operational threshold based on the real VPS disk baseline.

If the threshold is not met:

```text
DISK_GUARD_BLOCKED
```

No deployment starts and no global prune is attempted.

## 10. Cleanup evidence

Every successful release report must include, without secrets:

```text
GHCR versions before/after
GHCR digests retained
affected GHCR version IDs
VPS current/rollback/safety digests
VPS pending/blocked state
exact VPS image removed, if any
temporary-state cleanup result
disk free before deployment
GHCR cleanup status
VPS cleanup status
```

A release is not considered complete until both GHCR and VPS cleanup statuses are `OK`.
