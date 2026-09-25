# proizvodstvo1-release-control

This public repository records the last React staging release of Производство №1. GitHub Actions were disabled on 25.09.2026; the manifest in `release/staging.json` no longer triggers a build or deployment. The published staging portal remains online at its last committed image.

`docs/CURRENT_STATE.md` records the last release identity and the current pause. Existing `scripts/` and `ops/p1-react-staging-deploy.sh` are retained as technical source, not an active publication workflow. Source verification now runs locally in `zavx0z/proizvodstvo1` with `bun run local:check`. A separate local deployment process has not yet been established.
