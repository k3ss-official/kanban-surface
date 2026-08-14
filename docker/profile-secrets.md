# Profile secret templates

Keep templates outside the repository. Create `ksm.env.tpl` plus one file named
`<profile>.env.tpl` for every entry in `profiles/manifest.json`. Each contains only the
variables that runtime needs, with 1Password template expressions as values.

KSM receives only orchestration/messaging credentials. All profiles normally need their own
model-provider credential. `knowledge-custodian` is the only profile that receives the Open
Notebook writer capability token. The orchestrator, approved research/writer readers, the provenance
reviewer, and `audit-controller` receive the reader capability token. No profile receives the
Open Notebook instance password or encryption key. Infrastructure profiles receive only narrow
capability-gateway credentials, never a deployment-admin or unrestricted vault token.

Create a second secure template directory containing exactly these one-value templates:

- `encryption_key.tpl`
- `upstream_password.tpl`
- `reader_token.tpl`
- `writer_token.tpl`

Each file contains only its corresponding `op://...` reference. Use independently generated,
URL-safe reader and writer tokens. Set `KSM_OPEN_NOTEBOOK_SECRET_TEMPLATES` to that directory and
`OPEN_NOTEBOOK_SECRETS_DIR` to an ephemeral runtime directory. The renderer injects the correct
capability token into each authorized profile env without exposing the upstream password.

The renderer writes mode-0600 files into both runtime directories. Use ephemeral host paths
such as `/private/tmp/...` on macOS or a protected `/run/user/<uid>/...` path on Linux, render
again after reboot, and never commit the output. The 1Password service-account token remains
in the host process environment for `op inject`; it is not copied into any rendered file.
