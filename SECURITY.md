# Security policy

## Reporting a vulnerability

Report suspected vulnerabilities through GitHub's private security-advisory flow:

https://github.com/k3ss-official/kanban-surface/security/advisories/new

Do not open a public issue for authentication bypasses, token exposure, permission-boundary failures, command execution, secret-scope failures, or deployment details that would help exploitation.

Include:

- affected commit or release;
- reproduction steps using synthetic data;
- expected and observed permission boundary;
- impact;
- any safe mitigation already tested.

Do not include live credentials, customer data, private hostnames, or production logs. Redact tokens completely rather than partially.

## Security model

Kanban Surface enforces application-level authority through scoped gateway tokens, explicit target-board rules, profile-isolated home directories, read-only rendered secret mounts, and independent audit routing. A shared container is not a kernel isolation boundary. Operators requiring hostile-tenant isolation must use separate operating-system or virtualisation boundaries.

## Supported versions

Until tagged releases begin, only the current `main` branch receives security fixes.

## Deployment safety

- Bind the UI and APIs to loopback unless an authenticated reverse proxy protects them.
- Never mount the Docker socket.
- Never put the 1Password service-account token inside the container.
- Run negative permission tests as well as positive canaries.
- Use a disposable ledger and target for `tests/smoke.sh` before production.
