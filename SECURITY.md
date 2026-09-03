# Security policy

## Reporting a vulnerability

Report suspected vulnerabilities through GitHub's private security-advisory flow:

https://github.com/anwhelan01/kanban-surface/security/advisories/new

Do not open a public issue for authentication bypasses, token exposure, permission-boundary failures, command execution, secret-scope failures, or deployment details that would help exploitation.

Include:

- affected commit or release;
- reproduction steps using synthetic data;
- expected and observed permission boundary;
- impact;
- any safe mitigation already tested.

Do not include live credentials, customer data, private hostnames, 1Password renders, or production logs. Redact tokens completely rather than partially.

## Security model

Kanban Surface enforces application-level authority through scoped gateway tokens, explicit target-board rules, profile-isolated home directories, read-only rendered secret mounts, and independent audit routing. A shared container is not a kernel isolation boundary. Operators requiring hostile-tenant isolation must use separate operating-system or virtualisation boundaries.

The MCP adapter is optional and off by default. This repository does not ship a live `KS_TOKEN`. If you enable the shim, bind the gateway on loopback (`127.0.0.1`), never `0.0.0.0` on the host.

## Supported versions

Until tagged releases begin, only the current `main` branch receives security fixes.

## Deployment safety

- Bind the UI and APIs to loopback unless an authenticated reverse proxy protects them.
- Never mount the Docker socket.
- Never put the 1Password service-account token inside the container.
- Never commit `config.json`, rendered profile secrets, or real collab-mem content.
- Do not install the reference profile team onto a personal `~/.hermes` as part of reading this snapshot.
- Run negative permission tests as well as positive canaries.
- Use a disposable ledger and target for `tests/smoke.sh` before production.
