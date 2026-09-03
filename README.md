# Kanban Surface

**A thin stations-and-receipts layer on [Hermes Agent](https://github.com/NousResearch/hermes-agent) native Kanban.**

This repository is the `anwhelan01` snapshot of that layer. It composes Hermes primitives rather than replacing them.

- **Durable truth is the Git-backed work ledger** (operators typically call this **collab-mem**). Kanban is the live execution projection.
- **Nine stations** route work. Board movement is dispatch.
- **Receipts are native Hermes Kanban lifecycle** on the current persistent-profile team. The old `AGENT …` prose grammar is legacy only.
- **This checkout is not a live deploy.** A stranger can clone it, read this file, and run the documented offline tests. Nothing here writes your collab-mem, installs a team onto `~/.hermes`, or turns MCP on.

> **Status:** offline suites and Compose validation are the proof this snapshot offers. Live Hermes, a production board, Open Notebook, and host installers are operator-owned later steps — not part of a clean checkout.

## What this product is

Multi-agent systems rarely fail because they cannot generate text. They fail because ownership is fuzzy, authority exists only in prompts, state disappears into chats, and nobody can prove what happened.

Kanban Surface makes those edges explicit:

- **Boards are stations.** Moving a card changes the accountable profile and dispatches work.
- **Git-backed collab-mem is durable truth.** A Markdown ledger keeps project facts, priorities, and history reviewable. This repository ships only a synthetic example ledger.
- **Every run leaves a receipt.** Current profiles use native Hermes Kanban lifecycle tools. Historical cards may still carry the old prose tokens; the parser keeps them readable.
- **Authority is enforced in code.** Tokens map to stable actors, permitted verbs, and allowed target boards.
- **External mutations are independently checked.** Work that changes another system routes through audit before completion.

This snapshot does **not** ship live hostnames, IPs, tokens, 1Password renders, or a `config.json` with secrets. Copy `config.example.json` locally if you need a template.

## Nine stations

```text
Git-backed collab-mem (work ledger)
           │
           ▼
      sys-intake ─┬─► work-research ─► work-knowledge ─┐
                  ├─► work-engineering ────────────────┤
                  ├─► work-infra ──────────────────────┤
                  └─► work-writer ─────────────────────┤
                               │                       │
                               ├─► sys-input ↩         │
                               └─► sys-audit ──────────┤
                                                       ▼
                                                   sys-done
                                                       │
                                                       ▼
                                             receipt committed to Git
```

| Station | Authority |
|---|---|
| `sys-intake` | Triage and route; never performs domain work |
| `work-research` | Gather current signals and primary sources |
| `work-knowledge` | Verify evidence and control approved knowledge writes |
| `work-engineering` | Build code, integrations, automation, and tests |
| `work-infra` | Operate hosts, networks, DNS, security, and deployments |
| `work-writer` | Produce editorial work from verified material |
| `sys-input` | Ask one bounded human decision |
| `sys-audit` | Independently verify external mutations; verdict only |
| `sys-done` | Write terminal receipts back to the ledger |

The full contract is in [`docs/spec.md`](docs/spec.md).

## Reference team versus the M4 Hermes floor

`profiles/manifest.json` defines an **opinionated 16-profile reference team**: the default orchestrator plus 15 named specialists.

```text
default
├── research-lead
│   ├── research-signal
│   └── research-source
├── knowledge-custodian
├── knowledge-provenance
├── engineering-lead
│   ├── engineering-builder
│   └── engineering-review
├── infra-guardian
│   ├── infra-sysops
│   └── infra-netops
├── writer-director
│   ├── writer-longform
│   └── writer-social
└── audit-controller
```

This reference team is **not** the M4 Hermes floor (`Rae`, `scout`, `maker`, `gatekeeper`, `webdevsocials`). This snapshot does not create those bots and does not install any team onto anyone's `~/.hermes`.

Read the SOULs, adapt them if you operate your own host, and keep builder, knowledge authority, and independent reviewer separate. Do not treat `profiles/apply_team.py` or `install/install_ksm.sh` as something a stranger should run against a personal Hermes home.

The example model policy uses three separately bounded provider domains:

```text
OpenCode Go / glm-5.2
       ▼
OpenCode Zen / kimi-k2.7-code
       ▼
OpenAI Codex / gpt-5.6-sol
       ▼
fail closed
```

Change `profiles/manifest.json` before any operator install if you use different providers. Nous Portal is used for managed tools, not model inference, in this reference policy.

## Receipts

Current persistent profiles use **native Hermes Kanban lifecycle tools**. They do not emit prose station receipts.

`sync/receipts.py` still understands the **legacy comment grammar** so historical cards and the deterministic watcher remain parseable:

```text
AGENT CLAIMED       AGENT DONE          AGENT BLOCKED
AGENT HUMAN HOLD    AGENT UNBLOCKED     AGENT HUMAN ANSWERED
AGENT RESUMED       AGENT VERIFIED      AGENT REJECTED
AGENT FAILED
```

That list is history and compatibility, not the current write path. `tests/test_receipts.py` guards both: the parser still reads the old tokens, and the shipped SOULs must not invent or emit them.

When a domain completion still carries the legacy `mutated_external_state: true|false` declaration, `true` routes toward `sys-audit` and `false` may route to `sys-done`.

## MCP (optional, off by default)

`mcp/ks_mcp.py` is an **optional outsider interface**. It is **off by default**. This snapshot does not generate a live `KS_TOKEN`, does not bind `0.0.0.0`, and does not enable systemd.

If an operator later turns it on, the shim exposes five tools — `ks_list`, `ks_create`, `ks_move`, `ks_comment`, `ks_archive` — and holds no authority of its own. Identity and scope come from a gateway token you supply in the local environment. `ks_create` always lands on `sys-intake`. See [`mcp/README.md`](mcp/README.md).

## This is not an installable Python package

`pyproject.toml` configures Black and Ruff only. There is no `[project]` table and nothing is published to PyPI. A clean checkout installs pinned dependencies from the requirements files:

```bash
python3 -m pip install -r requirements-dev.txt   # tests + lint
# or: python3 -m pip install -r requirements.txt  # runtime extras only
```

The core board, Git sync, permission gateway, watcher, UI, local demo, and `mcp/ks_mcp.py` use the Python standard library. `requirements.txt` covers PyYAML, HTTPX, and the MCP SDK for the Open Notebook adapter and profile installer.

## Quick start (offline)

### 1. Clone this repository

```bash
git clone https://github.com/anwhelan01/kanban-surface.git
cd kanban-surface
python3 -m pip install -r requirements-dev.txt
```

### 2. Run the documented offline proof

```bash
./tests/run_all.sh
docker compose config --quiet
```

`./tests/run_all.sh` covers the parser, legacy receipt grammar, profiles, config, MCP stdio shim, workers, Open Notebook adapter, and a real temporary Git round trip. It does **not** need live Hermes, a live board, or network. `tests/test_live_team.py` is a separate, opt-in check against an already-installed Hermes home; it is not in the default suite.

### 3. Explore the local demo (optional)

```bash
python3 dev/demo.py --repo examples/ledger
```

Use `demo-owner`, `demo-orchestrator`, or `demo-contributor` as the UI token. The contributor token is deliberately denied access to restricted stations. The demo is synthetic.

## Ledger format

The parser accepts three intentionally small Markdown structures: MASTER rows, daily rows, and ordered items under a project's `## Next` heading. See [`docs/ledger-format.md`](docs/ledger-format.md) and [`examples/ledger`](examples/ledger).

The example ledger is synthetic. Keep real collab-mem content in your private ledger repository. This snapshot does not clone, write, or deploy that repository.

## Operator deployment (not this snapshot)

Compose files, the native installer, 1Password secret rendering, and systemd units exist in-tree for operators who already own a host. They are **out of scope** for a stranger checkout of this PR:

- Do not enable systemd from this snapshot.
- Do not bind the host UI or APIs to `0.0.0.0`. Loopback (`127.0.0.1`) is the documented host bind; put TLS in front if you need remote access.
- Do not write a live `config.json` into git.
- Do not mount the Docker socket.
- Do not put a 1Password service-account token in Compose, an image, or a tracked file.
- Do not install the reference team onto `~/.hermes`.
- Do not treat a green CI run as a VPS cutover.

If you later operate a dedicated host, start from `config.example.json` / `config.docker.example.json`, validate with `python3 sync/ksconfig.py config.json`, and keep secrets off the repository. `tests/smoke.sh` is the live sequence; it is not the default suite.

## Repository map

```text
compose.yaml       isolated multi-service topology (operator-owned)
docker/            bootstrap, safe Hermes defaults, secret rendering
profiles/          reference SOULs, 16-profile manifest, team installer
sync/              board backend, Markdown parser, Git sync, receipts
gateway/           permission gateway, audit log, static UI
triggers/          deterministic reconcile, notifications, loop breaks
mcp/               optional Kanban and Open Notebook MCP adapters (off)
ui/                drag-to-dispatch board surface
tests/             offline default suite; live-team check is opt-in
docs/              architecture contract and ledger schema
examples/ledger/   safe, synthetic demonstration ledger
```

## Security, provenance, and licensing

- Report vulnerabilities through [GitHub Security Advisories](https://github.com/anwhelan01/kanban-surface/security/advisories/new), not a public issue.
- Never commit credentials, live hostnames, customer data, 1Password renders, or real collab-mem content.
- This repository's original code is MIT licensed; see [`LICENSE`](LICENSE).
- Hermes Agent's Kanban implementation is distributed under the upstream Hermes Agent MIT licence. The generic Kanban method is not copied product code.
- External projects, packages, services, and images retain their own licences; see [`THIRD_PARTY.md`](THIRD_PARTY.md).
- Kanban Surface is an independent project and is not an official Nous Research product.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md), preserve the invariants, include tests for changed behaviour, and keep examples synthetic. Conventional Commits are preferred.

## What “green” means

GitHub Actions (Python 3.11, Black, Ruff, `./tests/run_all.sh`, `docker compose config --quiet`) runs the offline suites on pull requests and pushes to `main`. The suite uses a real temporary Git repository and bare remote to prove the ledger → intake → dispatch → receipt → Git loop without touching a live ledger or a live Hermes install.

A green CI run proves this snapshot's deterministic paths. It does **not** prove provider credentials, a remote proxy, live Open Notebook, M4 `~/.hermes/kanban.db`, or a production deployment.
