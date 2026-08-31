# Restricted React staging VPS boundary

This directory contains reviewed source for the one external host-side command used by the public release-control workflow.

The repository file is never executed directly from a mutable checkout on the
VPS. The accepted staging model installs an exact reviewed owner-only copy:

```text
/home/zavx0z/.p1-react-staging/bin/p1-react-staging-deploy
```

and records its SHA-256 in the installation report.

## Forced SSH command

One unique key in the existing trusted `zavx0z` account has no interactive
shell, PTY, forwarding or user rc. Its authorized-key options are equivalent to:

```text
restrict,command="/home/zavx0z/.p1-react-staging/bin/p1-react-staging-deploy"
```

The wrapper itself reads `SSH_ORIGINAL_COMMAND` and accepts only:

```text
state
deploy ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:<64 lowercase hex>
commit ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:<64 lowercase hex>
rollback <current committed Proizvodstvo1 React staging image>
```

No path, Compose project, service name or arbitrary command is accepted from SSH.

## Owner-scoped configuration

Install `/home/zavx0z/.p1-react-staging/config/deploy.env` owner-only mode 0600.
The whole `.p1-react-staging` tree and its `bin`, `config`, and `state`
directories are mode 0700; wrapper mode is 0500.

Required values:

```text
STAGING_COMPOSE_FILE=/home/zavx0z/proizvodstvo1-react-staging.compose.yaml
STAGING_OVERRIDE_FILE=/home/zavx0z/proizvodstvo1-react-staging.override.yaml
STAGING_RUNTIME_ENV=/home/zavx0z/proizvodstvo1-react-staging.env
STAGING_IMAGE_ENV=/home/zavx0z/.p1-react-staging/config/staging-image.env
STATE_DIR=/home/zavx0z/.p1-react-staging/state
DOCKER_CONFIG_DIR=/home/zavx0z/.p1-react-staging/config/docker
PORTAL_SERVICE=portal
NGINX_SERVICE=project-nginx
MIN_FREE_KB=1048576
EXTERNAL_HEALTH_URL=https://staging.proizvodstvo1.ru/health
```

`DOCKER_CONFIG_DIR/config.json` contains a pull-only GHCR credential for only the private `proizvodstvo1-react-portal` package. Credential material is not committed or printed.

The wrapper enforces that this file is regular, non-symlink, owned by the current
UID and has no group/other permissions (`mode & 0077 == 0`). Its parent is
owner-only and not group/other writable.

`STAGING_IMAGE_ENV` is an owner-only mode-0600 one-line file:

```text
PROIZVODSTVO1_REACT_STAGING_IMAGE=<immutable image ref>
```

The target and canonical parent must be real current-user-owned paths without
group/other write permission. Updates use `.p1tmp.image-env.*` in that same
parent followed by atomic `mv`; symlink targets and parents are rejected.

Before automation is enabled, Codex must prove the existing fixed staging Compose file reads that variable for only the `portal` service. If it does not, STOP; do not rewrite platform infrastructure as part of credential installation.

## Transaction model

The wrapper deliberately separates deployment into three phases:

1. `deploy IMAGE` records `PENDING_IMAGE` durably, then pulls and starts IMAGE
   and verifies container health and `/health`. It does not rotate or delete the
   committed rollback ring.
2. GitHub performs the full external staging smoke.
3. `commit IMAGE` finalizes the ring only after smoke succeeds. If smoke fails, `rollback PREVIOUS_CURRENT` restores the previous committed image and discards the failed pending candidate.

A runner crash after `deploy` leaves an explicit pending state. A later deployment is blocked with `PENDING_RECOVERY_REQUIRED` instead of silently overwriting evidence.

For normal deploy, `PENDING_IMAGE` is saved before the exact image pull. If pull
fails, pending is durably transitioned to exact `BLOCKED_IMAGE` before deletion;
cleanup success clears blocked state in a second save, while cleanup failure
returns `CLEANUP_BLOCKED`.

Failed apply clears pending state and deletes the candidate only after proving
the previous image-env, live image, internal/external health and unchanged
staging Nginx ID. Otherwise pending and candidate evidence remain for manual
recovery. Both bounded image-env/live crash-window pairs are recognized; a
missing portal container fails closed.

## Bounded VPS retention

Committed state is only:

```text
current
rollback
safety
```

plus at most one pending or blocked-cleanup image. The outgoing fourth committed image is removed only by exact allowed image reference after proving its Docker image ID is not used by a running container.

The new committed ring and outgoing `BLOCKED_IMAGE` are saved before that delete
attempt. Successful deletion clears blocked state in a second durable save.

If exact deletion cannot be proven safe, the wrapper stores `BLOCKED_IMAGE` and reports `CLEANUP_BLOCKED`; the next deployment is refused until that exact candidate can be safely removed.

Global cleanup is forbidden:

```text
docker system prune
docker image prune -a
docker volume prune
docker compose down
```

The audit ledger is truncated to the latest 100 records.

## Installation acceptance

Before enabling publication, Codex must return:

- installed wrapper path and SHA-256;
- owner/mode of wrapper and configuration;
- exact forced-command restriction (without key material);
- exact Compose project and service inventory;
- proof that Production №1, Artel and central ingress are unreachable through this wrapper;
- read-only proof of Docker log rotation for the staging portal;
- disk free baseline;
- `state` output with no secrets;
- wrapper `--self-test` result;
- no live deployment.
