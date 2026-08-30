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
- temporary files are created with restrictive permissions and removed by `trap`;
- Docker login is logged out before the job ends;
- test containers are always removed;
- local release test images are removed by exact tag/image ID;
- no persistent build cache is uploaded;
- cleanup steps use `if: always()` where necessary.

No self-hosted build workspace is used, so checkout, `node_modules`, BuildKit state and temporary containers disappear with the GitHub-hosted VM.

## 3. Private GHCR package

Canonical package:

```text
ghcr.io/zavx0z/proizvodstvo1-react-portal
```

Deployment always uses a full digest. Tags exist only for traceability and retention.

Retention target:

- keep the 5 most recent successfully deployed versions;
- always keep versions younger than 48 hours as a race-safety grace window;
- failed/orphan candidate versions older than 48 hours are eligible for deletion;
- never delete a digest referenced by current VPS state, rollback state or safety state;
- delete only versions of the exact package above;
- cap cleanup to 50 package-version deletions per run.

A cleanup workflow must run after successful publish and on a daily schedule.

If the package inventory exceeds the expected bound and cleanup cannot safely reduce it, report `CLEANUP_BLOCKED` and block the next release. Do not fall back to broad deletion.

## 4. VPS image retention

The React staging host keeps a bounded three-image ring:

```text
current
rollback
safety
```

After a successful deployment:

1. new image becomes `current`;
2. old `current` becomes `rollback`;
3. old `rollback` becomes `safety`;
4. the previous fourth digest becomes deletion candidate;
5. delete it only after proving it belongs to the exact React staging repository and is not referenced by any running container or one of the three retained states.

Never use:

```text
docker system prune
docker image prune -a
docker volume prune
docker compose down
```

Do not remove unrelated images, volumes, networks, caches or containers.

## 5. VPS temporary state

All release temporary files live under a dedicated root-owned release state directory.

Rules:

- use `mktemp` inside that directory;
- install `trap` cleanup before mutation;
- no symlink traversal;
- stale temp cleanup is limited to files created by this release system, with expected owner/prefix, older than 24 hours;
- if ownership/path safety cannot be proven, do not delete and return `CLEANUP_BLOCKED`.

Persistent state contains only the bounded current/rollback/safety digests plus minimal release status.

## 6. Logs

React staging container logs must use bounded Docker log rotation. Target contract:

```text
max-size: 10m
max-file: 5
```

Existing staging Nginx and central ingress logging are outside ordinary application publish. Their retention must be checked read-only before automation is enabled; changes require a separate infrastructure task.

## 7. Disk guard

Before pulling or importing a new staging image, check free space.

If the configured free-space threshold is not met:

```text
DISK_GUARD_BLOCKED
```

No deployment starts and no global prune is attempted.

## 8. Cleanup evidence

Every successful release report must include:

```text
GHCR versions before/after
GHCR digests retained
affected GHCR version IDs
VPS current/rollback/safety digests
exact VPS image removed, if any
temporary-state cleanup result
disk free before/after
cleanup status
```

Secrets and credentials are never printed.

A release is not considered complete until cleanup status is `OK`.
