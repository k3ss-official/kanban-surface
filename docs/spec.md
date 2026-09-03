# Kanban Surface architecture contract v2

## Invariants

1. The Git-backed work ledger (operators typically call this collab-mem) is
   durable truth; Kanban is the live execution projection.
2. Card location is dispatch. Board names are Hermes profile assignees.
3. One card, one accountable profile, one bounded run.
4. Every run leaves a structured receipt on the native Hermes Kanban lifecycle.
   The `AGENT …` prose grammar is a legacy comment parser. External mutations
   require independent audit.
5. Lifecycle profiles route and govern. Domain profiles own outcomes.
6. `work-knowledge` alone may write approved Open Notebook material.
7. `sys-done` alone writes terminal Kanban receipts to the work ledger.
8. A human answer is never fabricated by an agent; `sys-input` is the airlock.
9. Narrow authority is enforced with gateway rules and scoped credentials, not prose alone.
10. Sync never silently destroys a stranded receipt commit or automatically spends tokens
    unless a positive WIP limit explicitly admits work.

## Topology

```text
Human owner / authenticated clients
        │
        ▼
loopback KS gateway + UI ─── per-token verbs and target-board rules
        │
        ▼
Hermes Kanban database + single dispatcher
        │
        ├── lifecycle: sys-intake · sys-input · sys-audit · sys-done
        └── domains: work-research · work-knowledge · work-engineering
                     work-infra · work-writer
        │
        ▼
work-ledger / collab-mem checkout ⇄ Git remote
```

On a multi-project VPS, each installation is a distinct Compose project. Project-scoped
volumes and networks prevent accidental name/data collision. Only the KS surface port is
published, on `127.0.0.1`.

## Routing

- All external creates land inert on `sys-intake`.
- `sys-intake` selects exactly one domain or `sys-input`.
- Current persistent profiles complete and route through native Hermes Kanban
  lifecycle tools. They do not emit `AGENT …` prose receipts.
- `sync/receipts.py` still parses the historical comment grammar so old cards
  and the deterministic watcher remain readable. A legacy `AGENT DONE` that
  declares `mutated_external_state: true|false` still routes true → `sys-audit`
  and false → `sys-done`.
- Research intended for curated knowledge goes `work-research` → `work-knowledge`.
- A successful notebook write goes `work-knowledge` → `sys-audit` → `sys-done`.
- `sys-audit` rejection returns to the originating domain. After the configured
  rejection limit, the deterministic watcher moves the card to `sys-input`.
- A native failure, or a legacy `AGENT FAILED` comment, freezes the card and
  notifies the human; there is no blind retry loop.

## Persistent versus temporary agents

The nine stations are persistent Hermes profiles with separate state, sessions, SOULs,
configuration, and scoped `.env` files. Domain leads may delegate to one or two temporary
leaf agents when the objective warrants it. Leaves have no durable board identity or direct
authority to write canonical knowledge, deploy, publish, or close the card.

## Credential boundary

Profile secrets are rendered from 1Password on the host and mounted read-only. The service
account token itself never enters Hermes. The multiplexing gateway uses Hermes's profile
secret scope; an absent credential in the active profile fails closed rather than falling
through to another profile or the process environment.

The shared Hermes container is not a kernel security boundary between profiles. Therefore:

- `terminal.home_mode: profile` is mandatory.
- The default/orchestrator env must contain no privileged profile credential.
- Open Notebook write and infrastructure mutation should be narrow tools/gateways enabled
  only in the authorized profile configuration.
- Deployment-admin credentials remain outside Hermes entirely.
- Canary tests prove positive and negative credential resolution before production use.

## Git and recovery

Intake pushes any stranded receipt commit before fetching and never resets the checkout.
Done stages the whole linked ledger edit plus the board snapshot. If push fails, the local
commit is retained and retried; the card is not archived. If Kanban dies, the work ledger remains
usable and the crew falls back to markdown.

## Permission gateway

The gateway supports list/show/source, create, move, comment, and archive. Create always lands
on intake. Each bearer token maps to a stable actor plus explicit allowed verbs and target
boards. Every decision is appended to the audit log. The UI never receives the underlying
Hermes board credential.

## Acceptance

Offline acceptance:

- config and profile-manifest validation;
- receipt parser plus SOUL checks that current profiles stay on native lifecycle;
- real temporary git remote round trip;
- permission-refusal and idempotency tests;
- Docker Compose parse plus Hermes profile secret-scope canaries.

Live acceptance, against a test ledger branch:

1. Round trip: intake → domain → done → pushed receipt.
2. Blocked/resume via `sys-input` and an actual human answer.
3. Human hold notification through the real messaging client path.
4. External mutation → `sys-audit`, including one deliberate rejection.
5. A restricted token is refused and the refusal appears in the audit log.
6. Restart recovery with no duplicate intake, lost receipt, or excess worker.
7. Each profile reads its own canary and cannot resolve sibling canaries.

Local success does not authorize a VPS cutover or merge. Deployment, client-path checks, and
rollback evidence are separate acceptance gates.
