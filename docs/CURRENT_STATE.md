# React staging: current release

GitHub Actions were disabled on 25.09.2026 in `proizvodstvo1`, this repository, `platform-ingress`, and `artel`. The manifest records the selected source but does not trigger publication. Protected public `main` still requires a Pull Request; no Actions status checks are required.

The current manually published React staging release is **sequence 30**:

```text
manifest: release/staging.json
release-control merge: e9470e31a6b9f2014c7b3fb0808a7bce6561fb2d (PR #41)
source repository/ref: zavx0z/proizvodstvo1 / refs/heads/ai-dev
source_sha: 56c5682f949b11405ea9d9d8f1716f6a6305b5d6
current image: ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:d1fa87c79bbc52a6418ec53ccb39c96a22ea3861a1a1e02beab32d3572af2dd3
rollback image: ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:d9763d84512da6a90bf53837200f9f15180e4ee77b2cd8fd969a327ae2297897
safety image: ghcr.io/zavx0z/proizvodstvo1-react-portal@sha256:e5210d753f2e8b1bad1eb44acaac521a9db4d272f63a516c1fc395b9b4783565
```

The exact `ai-dev` commit passed `bun run local:check`. The release image passed container smoke, 179 photo endpoint checks, and Chrome checks at 1440, 1024, 390, and 320 px. The image was pushed to the private GHCR package with `seq-30`, `sha-56c5682f949b11405ea9d9d8f1716f6a6305b5d6`, and `deployed-seq-30` tags pointing to the same digest. The restricted VPS wrapper deployed only the React staging portal. HTTP and live browser smoke passed before commit; the final ring reported `STATUS=ok`, no pending or blocked image, and `CLEANUP_STATUS=OK`.

Bounded GHCR cleanup removed only the obsolete staging sequence 24 version. Five successful release versions remain, including the current, rollback, and safety images. Temporary image archives were removed from the builder, relay, and VPS. `https://staging.proizvodstvo1.ru/health` returned `status=ok`, `seoIndexable=false`, and the sequence 30 source SHA.

The preceding Actions release was sequence 29 (`d32c0fff145390533672064717d6309702969d9c`, run `36070548481`). Publication now requires manual local verification and image upload followed by the existing restricted VPS deploy transaction. No recurring local publish job has been added. Production №1, Artel runtime, central ingress, staging Nginx, DNS, and TLS were not changed by sequence 30.
