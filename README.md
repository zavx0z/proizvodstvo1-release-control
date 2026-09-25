# proizvodstvo1-release-control

This public repository records React staging release manifests for Производство №1. GitHub Actions were disabled on 25.09.2026; a manifest change does not trigger a build or deployment.

`docs/CURRENT_STATE.md` records the current manually published release, its source commit, image digest, rollback state, and verification. Source checks run locally in `zavx0z/proizvodstvo1` with `bun run local:check`. The existing restricted VPS wrapper remains the staging deployment mechanism; there is no automated publish job.
