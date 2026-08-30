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

`sequence` is monotonic and increments by exactly one for each release request. A no-op release may keep the same `source_sha` while increasing `sequence`; this is used for controlled pipeline/rollback verification.

## 3. Release Pull Request

A normal release PR:

- originates from this repository;
- branch name is `release/staging-seq-<N>`;
- changes exactly `release/staging.json`;
- sets `<N>` equal to manifest `sequence`;
- increments the base manifest sequence by exactly one;
- does not change workflow, docs or policy files.

The base-branch guard validates this without using secrets.

## 4. Maintenance Pull Request

A maintenance PR:

- branch starts with `maintenance/`;
- originates from this repository;
- author is `zavx0z`;
- never changes `release/staging.json` in the same PR;
- may change only the control paths explicitly allowed by the existing base guard.

This ensures a PR cannot modify the guard and release manifest together.

## 5. Publish pipeline — next stage

The publish workflow is intentionally not part of the bootstrap PR. It is added only after:

1. bootstrap guard is merged;
2. public `main` is protected;
3. required check `Release manifest guard` is enforced;
4. private-source and GHCR/VPS credentials are installed separately.

The future publish workflow must run on GitHub-hosted runners only and only for `push` to protected `main` when `release/staging.json` changes.

It must:

1. read the manifest from `main`;
2. fetch private source through a dedicated read-only credential;
3. prove `source_sha` is the current `refs/heads/ai-dev` head;
4. repeat application gates;
5. build the release image from exact source SHA;
6. publish only private `ghcr.io/zavx0z/proizvodstvo1-react-portal`;
7. resolve and use a full immutable digest;
8. update only `proizvodstvo1-react-staging.portal` through a restricted external command;
9. run health/smoke;
10. rollback on failure;
11. run bounded cleanup and fail the release if cleanup cannot be proven safe.

## 6. Never part of ordinary staging publish

- `zavx0z/proizvodstvo1/main`;
- Production №1 containers/images;
- Artel;
- central ingress;
- staging Nginx;
- DNS;
- TLS;
- global Docker cleanup.

Production cutover is a separate Vladimir-authorized operation.
