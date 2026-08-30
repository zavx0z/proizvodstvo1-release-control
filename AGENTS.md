# Canonical rules for proizvodstvo1-release-control

## Purpose

This public repository is the technical release authority for React staging metadata only.

It must never contain:

- source code from private `zavx0z/proizvodstvo1`;
- Institute datasets or internal research;
- client data;
- Artel or Production runtime/configuration;
- secrets, keys, tokens, passwords or Docker auth;
- binary build artifacts or OCI archives.

Public data is limited to safe metadata such as source SHA, image digest, release sequence, dates and technical release status.

## Source and deployment boundaries

- private source repository: `zavx0z/proizvodstvo1`;
- accepted staging source ref: `refs/heads/ai-dev`;
- canonical release request: `release/staging.json`;
- ordinary deployment target: `proizvodstvo1-react-staging.portal` only.

Ordinary staging publication must not change or restart:

- Production №1;
- Artel;
- central ingress;
- staging Nginx;
- DNS;
- TLS.

## Pull Request types

### Release PR

Branch:

```text
release/staging-seq-<N>
```

Rules:

- changes exactly one file: `release/staging.json`;
- `sequence` increments by exactly one;
- manifest keeps fixed repository/ref/environment fields;
- source SHA is a full lowercase 40-character commit SHA;
- no workflow, docs or policy change may be mixed into a release PR.

### Maintenance PR

Branch:

```text
maintenance/<slug>
```

Rules:

- must originate from this repository, not a fork;
- author must be repository owner `zavx0z`;
- may change only reviewed control/docs/workflow paths allowed by the base guard;
- must not change `release/staging.json` in the same PR.

### Bootstrap PR

Only the first repository bootstrap from initial main SHA `5e438561a453648c1f9fd1e142a5c1cf01145a3b` is allowed to add the initial control files before branch protection exists.

After bootstrap, protected public `main` plus the base-branch `Release manifest guard` is the trust boundary.

## Merge rules

- no direct commits to `main` after bootstrap;
- no force-push or deletion of protected `main`;
- required check: `Release manifest guard`;
- ordinary merge method: squash;
- release-control `main` is not application `main` and never changes Production №1 by itself.

## Cleanup is part of release correctness

Read `docs/RETENTION_AND_CLEANUP.md`.

A release is not complete until cleanup evidence is green. If cleanup is blocked or cannot prove safe deletion, the next release must stop rather than run a broad prune.

Forbidden cleanup commands include:

```text
docker system prune
docker image prune -a
docker volume prune
docker compose down
```

Only exact resources belonging to this React staging release system may be removed.

## Roles

- Vladimir owns architecture and dangerous decisions.
- ChatGPT owns GitHub development, PRs, CI review and release-manifest operations.
- Codex is used only for external GitHub Settings, secrets/keys, GHCR package access, VPS and other non-GitHub runtime operations.

Codex does not make architecture decisions or expand scope.
