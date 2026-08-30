# Protection probe v2

Temporary metadata-only file used to execute the trusted-base `Release manifest guard` after the GitHub Contents base64 fix and before branch protection is enabled.

Expected base main:
`055c67b563140794c9efaeeff4aeb97d1aac22f2`

This file must not be merged. Close the probe PR after the guard is green, then delete the probe branch during the branch-protection setup task.
