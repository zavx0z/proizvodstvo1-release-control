# Release-control current state

Purpose: one-time protection probe. This file exists only to make the trusted-base `Release manifest guard` execute before branch protection is enabled.

Current public main after bootstrap:

```text
21344efa0b3223ec3964dc2273a42e8a163b0834
```

No GHCR package, secrets, Deploy Keys, publish workflow or VPS deployment access are configured yet.

This probe PR must be closed without merge after the guard reports success.
