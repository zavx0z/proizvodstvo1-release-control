# Current release-control state

Snapshot: 2026-08-30. Always re-check GitHub and live infrastructure before mutation.

## Public release authority

```text
repository: zavx0z/proizvodstvo1-release-control
visibility: public
default branch: main
protected main before this maintenance PR:
055c67b563140794c9efaeeff4aeb97d1aac22f2
```

GitHub branch protection is independently verified:

```text
protected=true
enforcement=everyone
PR required=true
required approvals=0
strict checks=true
required checks:
- Release manifest guard
- Release-control code self-test
force push=false
deletion=false
admin bypass=false
conversation resolution=true
linear history=true
```

Codex Issue #13 is completed and closed. All temporary bootstrap/probe/fix branches were removed; before this maintenance branch was created, public repo contained only `main`.

## Private source baseline

```text
zavx0z/proizvodstvo1/main:
64c09e30a097d811eed1e257faf79171766d3fa9

zavx0z/proizvodstvo1/ai-dev:
657b77d5839385775b0c1a43d2621a0ce9c3a628
```

Private source-side PR #6 remains open/draft and not merged. It contains the application-owned release Dockerfile and Dockerfile-specific ignore file required by the GHCR publisher.

A real GHCR build cannot pass source preflight until those release files are separately accepted into `ai-dev`. This is not a merge into private `main` and not production cutover.

## Live staging baseline

Last externally confirmed live baseline remains:

```text
https://staging.proizvodstvo1.ru

source SHA:
657b77d5839385775b0c1a43d2621a0ce9c3a628

current image:
10.66.0.10:5000/platform/proizvodstvo1-react-portal@sha256:8f701237413da3fe1c663e5b0c14e67b52e6a2c3bb82bad92383880f00b82b1c
```

Production №1, Artel, central ingress, staging Nginx, DNS and TLS remain outside release-control bootstrap and have not been changed by it.

## Current maintenance PR

```text
PR #5
branch: maintenance/publish-pipeline-v1
base: protected public main
```

The PR changes control code only and does **not** change `release/staging.json`, so merging it alone cannot trigger an application build or deployment.

It contains:

- exact manifest/private-source preflight;
- immutable `git archive` source freeze;
- separate test and build snapshots from the same archive;
- GitHub-hosted application gates;
- build-only GHCR bootstrap mode with no VPS deployment;
- private-package visibility check;
- release image revision/health check;
- split credential jobs: VPS preflight / source build / VPS deploy / GHCR finalize;
- restricted root-owned transactional VPS wrapper;
- protected control-side full staging smoke;
- bounded GHCR cleanup;
- bounded VPS current/rollback/safety ring;
- no-op-safe repeat release path;
- security/release/cleanup documentation.

## Security review findings already addressed in PR #5

Manual review caught and corrected these issues before merge:

1. Source-controlled host smoke must not run in a job holding the VPS private key. Full host smoke now lives only in protected public release-control workflow code.
2. Application tests must not be able to mutate the later Docker build context. Tests and build now use different directories extracted from one frozen source archive.
3. Private source and VPS private key must not coexist in the same job. The workflow is split into separate jobs.
4. Releasing the already-current digest must not rotate duplicate rollback/safety entries. The VPS wrapper has an explicit no-op transaction.
5. Root-owned staging image env is required and checked against the live container before state-changing actions.
6. Temporary root state uses atomic files and EXIT/INT/TERM cleanup instead of function-local RETURN traps.

## External setup is still absent

No external installation is authorized yet. The following still require a separate Codex task after PR #5 is reviewed and separately authorized for merge:

- `P1_SOURCE_DEPLOY_KEY` read-only deploy key;
- restricted VPS SSH account/key/forced command;
- root-owned VPS wrapper/config installation;
- VPS pull-only GHCR credential;
- release-control secrets/variables;
- GHCR package/bootstrap access verification;
- staging portal log-rotation and disk baseline proof.

Enabling variables remain absent:

```text
P1_STAGING_BUILD_ONLY_ENABLED
P1_STAGING_PUBLISH_ENABLED
P1_STAGING_MAINTENANCE_ENABLED
```

Therefore there is no route from this maintenance PR to live deployment.

## Planned bootstrap sequence after PR #5 acceptance

1. After PR #5 is accepted, create a new exact external installation Issue; do not reuse Issue #15.
2. Install credentials/wrapper with all enabling variables false.
3. Run wrapper self-test and VPS `state` only; no live deploy.
4. Temporarily enable only `P1_STAGING_BUILD_ONLY_ENABLED` and run build-only to create/verify the private GHCR package without VPS deployment.
5. Configure and prove VPS pull-only access to that one package.
6. Disable build-only again and review cleanup evidence.
7. Obtain separate Vladimir authorization before merging source-side PR #6 into `ai-dev` if still required.
8. Obtain separate Vladimir authorization before the first manifest sequence that performs the controlled functionally-no-op live migration.

## Cleanup invariant

No release step may use broad Docker cleanup. GHCR and VPS cleanup are exact-package/exact-image only. Any unclassifiable state or failed safe deletion returns `CLEANUP_BLOCKED` and prevents the next deployment.
