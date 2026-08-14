# Contributing

Kanban Surface is a security-sensitive execution surface. Small, evidenced changes beat broad rewrites.

## Before opening a pull request

```bash
python3 -m pip install -r requirements-dev.txt
black --check dev gateway mcp profiles sync tests triggers
ruff check .
./tests/run_all.sh
docker compose config --quiet
```

If behaviour changes, add or update a test that proves both the allowed path and the relevant refusal or failure path.

## Architecture rules

Preserve the invariants in `docs/spec.md`, especially:

- no card without a stable ledger reference;
- board movement is dispatch;
- one accountable owner per card;
- workers do not audit their own external mutations;
- terminal receipts are written through the done station;
- credentials and authority fail closed;
- reconciliation remains idempotent and loop-safe.

Changes to board names, receipt grammar, permission verbs, profile authority, ledger linkage, or secret scope require corresponding documentation and regression tests.

## Pull-request checklist

- [ ] Scope is bounded and the rationale is clear.
- [ ] No credentials, private hostnames, customer data, or real ledger content are present.
- [ ] Examples are synthetic.
- [ ] New dependencies are pinned and added to `THIRD_PARTY.md`.
- [ ] Tests cover success and refusal/failure behaviour.
- [ ] `./tests/run_all.sh` passes.
- [ ] `docker compose config --quiet` passes when Compose changes.
- [ ] Documentation matches the implemented path.
- [ ] Rollback or compatibility impact is stated.

## Style

- Python: type hints where meaningful, PEP 8, and deterministic tests.
- Shell: `set -euo pipefail`, quoted variables, idempotent operations.
- Configuration: validate JSON and YAML after editing.
- Commits: Conventional Commits are preferred.

## Security disclosures

Use the private process in `SECURITY.md`; do not file exploitable details as a public issue.
