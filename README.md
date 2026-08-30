# proizvodstvo1-release-control

Public release authority for the React staging portal of Производство №1.

This repository intentionally contains only safe release metadata and trusted GitHub Actions. It must never contain application source, Institute data, client data, Artel/Production configuration, private keys, passwords, Docker auth, tokens or other secrets.

## Trust model

- private source: `zavx0z/proizvodstvo1`;
- staging source line: `refs/heads/ai-dev`;
- release authority: protected `main` in this repository;
- canonical request: `release/staging.json`;
- deployment target: only `proizvodstvo1-react-staging.portal`;
- Production №1, Artel, central ingress, staging Nginx, DNS and TLS are outside the ordinary publish operation.

Normal staging updates are manifest-only Pull Requests. Maintenance of this control repository uses owner-only `maintenance/*` branches and must never be mixed with a release manifest change.

See `docs/RELEASE_CONTRACT.md` and `docs/RETENTION_AND_CLEANUP.md` before any change.

Bootstrap source: `zavx0z/proizvodstvo1#6`.
