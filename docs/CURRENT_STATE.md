# Current release-control state

Snapshot: 2026-08-30. Always re-check GitHub and live infrastructure before mutation.

## Public release authority

```text
repository: zavx0z/proizvodstvo1-release-control
visibility: public
default branch: main
main SHA before this maintenance PR:
055c67b563140794c9efaeeff4aeb97d1aac22f2
```

Branch protection is active and independently verified through the GitHub branch API:

```text
protected=true
enforcement=everyone
required checks:
- Release manifest guard
- Release-control code self-test
```

Codex Issue #13 reported and GitHub confirmed:

- PR required;
- approvals required: 0;
- strict/up-to-date status checks;
- force-push disabled;
- deletion disabled;
- administrator bypass disabled;
- conversation resolution enabled;
- linear history enabled;
- all temporary probe/bootstrap/fix branches removed.

## Private source baseline

```text
zavx0z/proizvodstvo1/main:
64c09e30a097d811eed1e257faf79171766d3fa9

zavx0z/proizvodstvo1/ai-dev:
657b77d5839385775b0c1a43d2621a0ce9c3a628
```

Private source-side PR #6 remains open/draft and is not merged. It contains the application-owned release Dockerfile, staging smoke and canonical source-side architecture for this release model.

The first GHCR publication cannot be enabled until the exact required release files are accepted into `ai-dev` through a separately authorized merge. This is not a merge into private `main` and not production cutover.

## Live staging baseline

Last externally confirmed live baseline remains:

```text
https://staging.proizvodstvo1.ru

source SHA:
657b77d5839385775b0c1a43d2621a0ce9c3a628

legacy isolated-registry image:
10.66.0.10:5000/platform/proizvodstvo1-react-portal@sha256:8f701237413da3fe1c663e5b0c14e67b52e6a2c3bb82bad92383880f00b82b1c
```

Production №1, Artel, central ingress, staging Nginx, DNS and TLS have not been changed by release-control bootstrap.

## Current maintenance PR purpose

Branch:

```text
maintenance/publish-pipeline-v1
```

This PR adds reviewed but inert control code for:

- manifest/private-source preflight;
- GitHub-hosted exact-source application gates;
- private GHCR image build by full digest;
- transactional restricted VPS deploy/commit/rollback;
- full external staging smoke before ring rotation;
- bounded GHCR cleanup;
- bounded VPS current/rollback/safety retention;
- security and operational contracts.

The publish workflow triggers only on a future `release/staging.json` change merged to protected `main`. Merging this maintenance PR alone does not build, push or deploy an application image.

The scheduled GHCR cleanup job is inert unless:

```text
P1_STAGING_MAINTENANCE_ENABLED=true
```

The publish workflow refuses to start unless:

```text
P1_STAGING_PUBLISH_ENABLED=true
```

No enabling variables or credentials are created by this PR.

## External setup still absent

The following do not exist yet and require a separate reviewed Codex task after this PR is accepted:

- read-only deploy key for private `proizvodstvo1` source;
- restricted VPS SSH key/account/forced command;
- VPS root-owned wrapper/config installation;
- private GHCR package permission verification;
- VPS pull-only GHCR credential;
- release-control repository secrets/variables;
- proof of staging portal log rotation and disk threshold;
- dry-run/no-live deployment acceptance.

## Cleanup invariant

No release step may use broad Docker cleanup. GHCR and VPS cleanup are exact-package/exact-image only. Any unclassifiable state or failed safe deletion returns `CLEANUP_BLOCKED` and prevents the next deployment.

## Next gates

1. Review this maintenance PR under protected public `main` and prove both required checks.
2. Obtain Vladimir authorization before merging the maintenance PR.
3. After merge, repurpose private Issue #15 into the exact external installation/credential task; do not create additional placeholder issues.
4. Install external boundary with publication variables left disabled.
5. Perform a dry-run that proves source checkout, tests, package permissions and VPS `state` without image push/deployment where possible.
6. Obtain separate Vladimir authorization to merge source-side PR #6 into `ai-dev` if still required.
7. Perform the first controlled functionally-no-op GHCR migration only after all previous evidence is green.
