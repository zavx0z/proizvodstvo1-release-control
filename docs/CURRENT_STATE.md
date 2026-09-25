# Last React staging release and local-only transition

GitHub Actions were disabled on 25.09.2026 in `proizvodstvo1`, this release-control repository, `platform-ingress`, and `artel`. The old ChatGPT release/development rules and workflow files were removed. Protected public `main` still requires a Pull Request and retains linear history, administrator enforcement, conversation resolution, and bans force-push and branch deletion; its required GitHub Actions checks were removed because they cannot run. No new deployment mechanism is active.

The final completed GitHub Actions release was staging **sequence 29**:

```text
manifest: release/staging.json
source repository/ref: zavx0z/proizvodstvo1 / refs/heads/ai-dev
source_sha: d32c0fff145390533672064717d6309702969d9c
release-control main before local-only transition: eac3c848aec15c0dbf60c2e96a870360ae5f52e7
publish run: 36070548481 (success, four jobs)
current image: ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:d9763d84512da6a90bf53837200f9f15180e4ee77b2cd8fd969a327ae2297897
rollback image: ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:e5210d753f2e8b1bad1eb44acaac521a9db4d272f63a516c1fc395b9b4783565
safety image: ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:795bcfccb86693d48d3340c4dcf0c5b3bf6410180d1945c56f0aee1a8d202b07
```

At the transition, `https://staging.proizvodstvo1.ru/health` returned `status=ok` and the same `sourceSha`. This records the historical live image; newer `ai-dev` commits are locally verified source changes and have not been published through this repository. Production №1, Artel runtime, central ingress, staging Nginx, DNS/TLS, and VPS image state were not changed by the local-only transition.
