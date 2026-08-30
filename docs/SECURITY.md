# Release-control security boundary

The public release-control repository contains only public metadata and reviewed control code. Application source, client data and credentials remain private.

## Trust chain

```text
protected public main
  -> exact release/staging.json
  -> GitHub-hosted runner
  -> read-only private-source deploy key
  -> exact ai-dev HEAD == manifest source_sha
  -> repeated application checks
  -> private GHCR package
  -> immutable image digest
  -> forced-command VPS key
  -> fixed root-owned deploy wrapper
  -> only proizvodstvo1-react-staging.portal
```

## Public information

The following may be public:

- release sequence;
- source commit SHA;
- image digest;
- staging release timestamps;
- workflow/check status;
- non-secret cleanup evidence.

No source content is copied into this repository.

## GitHub Actions secrets

The publish workflow is designed to require only narrowly scoped external credentials:

```text
P1_SOURCE_DEPLOY_KEY
P1_VPS_DEPLOY_KEY
P1_VPS_KNOWN_HOSTS
```

and non-secret repository variables:

```text
P1_STAGING_PUBLISH_ENABLED
P1_STAGING_MAINTENANCE_ENABLED
P1_VPS_DEPLOY_HOST
P1_VPS_DEPLOY_USER
```

The exact final names may be adjusted once during installation, but the privileges must not be broadened.

### Private source key

`P1_SOURCE_DEPLOY_KEY` is a read-only deploy key bound only to `zavx0z/proizvodstvo1`. It must have no write permission and no access to other repositories.

The workflow checks out only branch `ai-dev`, immediately compares its exact HEAD with `release/staging.json:source_sha`, and fails before build if they differ.

### VPS key

`P1_VPS_DEPLOY_KEY` authenticates only the dedicated staging deploy account. The public key is restricted server-side to the fixed root-owned forced command described in `ops/README.md`.

Possession of this key must not allow:

- an interactive shell;
- arbitrary sudo;
- arbitrary Docker commands;
- Production №1 mutation;
- Artel mutation;
- central ingress mutation;
- DNS/TLS mutation;
- arbitrary image repositories.

### GHCR write credential

No long-lived GHCR push token is stored in the repository. GitHub-hosted publication uses the job-scoped `GITHUB_TOKEN` with `packages: write` for the exact package associated with this repository.

The package must remain private. Package access is configured separately and verified before publication is enabled.

The VPS uses a different pull-only GHCR credential stored only on the VPS. The public workflow never receives the VPS GHCR credential.

## Workflow hardening

- third-party Actions are not required;
- `actions/checkout` is pinned by full commit SHA;
- publish runs only on `push` to protected `main` when `release/staging.json` changes;
- source build uses the exact checked-out private commit;
- all resulting deployment references use `@sha256:<digest>`;
- no Actions cache or uploaded binary artifacts;
- GitHub-hosted ephemeral runners only;
- SSH private-key files are created only under `RUNNER_TEMP` and removed in an `if: always()` step;
- Docker logout runs in `if: always()` cleanup;
- the deployment wrapper uses a pending/commit transaction so full smoke happens before rollback-ring rotation.

## Branch protection

Public `main` is the release authority and must remain protected with:

- PR required;
- strict required status checks;
- exact checks `Release manifest guard` and `Release-control code self-test`;
- force push disabled;
- branch deletion disabled;
- administrator bypass disabled;
- conversation resolution and linear history enabled where supported.

If these properties are not true, do not publish.

## Stop conditions

Publication is blocked when any of the following is true:

- source deploy key missing or too broad;
- `ai-dev` HEAD differs from the manifest source SHA;
- application checks fail;
- GHCR package visibility or access is not proven private/scoped;
- VPS forced-command restriction is not proven;
- VPS reports a pending recovery state;
- disk guard fails;
- GHCR or VPS cleanup returns `CLEANUP_BLOCKED`;
- immutable digest cannot be resolved;
- full staging smoke fails and rollback cannot be proven healthy.
