# Kanban Surface

**A stations-and-receipts execution surface for [Hermes Agent](https://github.com/NousResearch/hermes-agent).**

Kanban Surface turns Hermes Agent's native Kanban into a legible multi-profile operating system: Git-backed work enters through intake, board movement dispatches bounded specialist profiles, and every run leaves a machine-readable receipt. It composes Hermes primitives rather than replacing them.

> **Status:** serious work in progress. Offline suites and Compose validation are green; live acceptance remains an explicit deployment step. The architecture is usable, opinionated, and still evolving.

## Why this exists

Multi-agent systems rarely fail because they cannot generate text. They fail because ownership is fuzzy, authority exists only in prompts, state disappears into chats, and nobody can prove what happened.

Kanban Surface makes those edges explicit:

- **Boards are stations.** Moving a card changes the accountable profile and dispatches work.
- **Git is durable truth.** A Markdown ledger keeps project facts, priorities, and history reviewable.
- **Every run leaves a receipt.** Claim, completion, block, verification, rejection, and failure transitions use a fixed grammar.
- **Authority is enforced.** Tokens map to stable actors, permitted verbs, and allowed target boards.
- **External mutations are independently checked.** Work that changes another system routes through audit before completion.
- **Credentials fail closed.** Profile secrets are rendered from 1Password on the host and mounted read-only.

## The operating model

```text
Git-backed Markdown ledger
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

## Invariants

1. No executable card exists without a stable ledger reference.
2. A board move is dispatch, not decoration.
3. One profile owns each card at a time.
4. A worker does not certify its own external mutation.
5. Only the done station writes terminal receipts to Git.
6. Permission is enforced by code and scoped credentials, not prose alone.
7. Missing profile credentials fail closed.
8. Human decisions cross a dedicated input airlock.
9. Reconciliation is deterministic and loop-safe.
10. Git remains recoverable when board state is damaged or lost.

The full contract is in [`docs/spec.md`](docs/spec.md).

## Profile team

The reference manifest defines **15 child profiles plus the default orchestrator: 16 profiles total**.

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

These SOULs, skills, model routes, and authority boundaries are an **opinionated reference team**, not universal defaults. Read them, adapt them to your organisation, and preserve the separation between builder, knowledge authority, and independent reviewer.

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

Change `profiles/manifest.json` before installation if you use different providers. Nous Portal is used for managed tools, not model inference, in this reference policy.

## Receipt contract

`sync/receipts.py` owns the fixed transition grammar:

```text
AGENT CLAIMED       AGENT DONE          AGENT BLOCKED
AGENT HUMAN HOLD    AGENT UNBLOCKED     AGENT HUMAN ANSWERED
AGENT RESUMED       AGENT VERIFIED      AGENT REJECTED
AGENT FAILED
```

Every domain completion declares `mutated_external_state: true|false`. A true value routes to `sys-audit`; a false value may route directly to `sys-done`.

## Credential boundary

```text
1Password on host
       │ op inject
       ▼
ephemeral 0600 files ── read-only mount ──► profile secret scope
                                                   │
                                      ┌────────────┼────────────┐
                                      ▼            ▼            ▼
                                  profile A    profile B    profile C
```

- The 1Password service-account token remains in the host process environment.
- It is never stored in Compose, the image, or a profile env file.
- Each profile receives only its rendered secret set.
- An absent credential fails closed instead of falling through to another profile.
- `terminal.home_mode: profile` is mandatory, but it is not a kernel security boundary.
- Narrow capability gateways enforce the boundaries a shared container cannot.

## Open Notebook integration

[Open Notebook](https://github.com/lfnovo/open-notebook) is treated as a private knowledge service behind a role-scoped gateway:

- Reader token: list, get, and search.
- Writer token: approved notebook, source, and note creation or update.
- Delete, admin, settings, chat, credential, and upstream secret routes are not proxied.
- `knowledge-custodian` is the sole writer profile.
- `knowledge-provenance` and `audit-controller` remain independent reviewers.

## Quick start

### 1. Clone and install Python dependencies

```bash
git clone https://github.com/k3ss-official/kanban-surface.git
cd kanban-surface
python3 -m pip install -r requirements.txt
```

### 2. Run the offline proof

```bash
./tests/run_all.sh
docker compose config --quiet
```

### 3. Explore the local demo

```bash
python3 dev/demo.py --repo examples/ledger
```

Use `demo-owner`, `demo-orchestrator`, or `demo-contributor` as the UI token. The contributor token is deliberately denied access to restricted stations.

## Docker deployment

Each deployment gets its own Compose project, private network, volumes, loopback ports, and profile-secret directory. The Compose file does not set `container_name`, mount the Docker socket, or bake credentials into an image.

```bash
cp config.docker.example.json config.json
# Replace placeholder tokens, chat ID, and work-ledger URL.
python3 sync/ksconfig.py config.json

export KSM_PROFILE_SECRET_TEMPLATES=/secure/path/profile-templates
export KSM_PROFILE_SECRETS_DIR=/private/tmp/hermes-ksm-profile-secrets
export KSM_OPEN_NOTEBOOK_SECRET_TEMPLATES=/secure/path/open-notebook-templates
export OPEN_NOTEBOOK_SECRETS_DIR=/private/tmp/hermes-ksm-open-notebook-secrets
./docker/render-profile-secrets.sh

export COMPOSE_PROJECT_NAME=hermes-ksm
export WORK_LEDGER_DIR="$PWD/examples/ledger"
export HERMES_UID="$(id -u)" HERMES_GID="$(id -g)"
docker compose config --quiet
docker compose pull
docker compose run --rm --no-deps bootstrap
docker compose up -d
curl -fsS http://127.0.0.1:8742/healthz
```

The UI and APIs bind to host loopback. Put remote access behind an authenticated reverse proxy or SSH tunnel. Run `tests/smoke.sh 1..5` against a deliberately selected test ledger and branch before any production cutover.

## Native deployment

The native installer targets a dedicated Linux host with user-scoped systemd:

```bash
cp config.example.json config.json
# Set repo_url and repo_dir to your Git-backed work ledger.
./install/install_ksm.sh
```

The installer clones the configured ledger when absent, validates configuration, creates clean Hermes profiles without cloning the default profile's secrets, installs the team, and enables the gateway, watcher, intake, and snapshot units.

## Ledger format

The parser accepts three intentionally small Markdown structures: MASTER rows, daily rows, and ordered items under a project's `## Next` heading. See [`docs/ledger-format.md`](docs/ledger-format.md) and [`examples/ledger`](examples/ledger).

## MCP access

`mcp/ks_mcp.py` exposes five native tools to MCP clients: `ks_list`, `ks_create`, `ks_move`, `ks_comment`, and `ks_archive`. Identity and scope still come from `KS_TOKEN`; the shim has no authority of its own. See [`mcp/README.md`](mcp/README.md).

## Repository map

```text
compose.yaml       isolated multi-service topology
docker/            bootstrap, safe Hermes defaults, secret rendering
profiles/          profile SOULs, reference manifest, team installer
sync/              board backend, Markdown parser, Git sync, receipts
gateway/           permission gateway, audit log, static UI
triggers/          deterministic reconcile, notifications, loop breaks
mcp/               Kanban and Open Notebook MCP adapters
ui/                drag-to-dispatch board surface
tests/             offline, real-Git, integration, container, smoke tests
docs/              architecture contract and ledger schema
examples/ledger/   safe, synthetic demonstration ledger
```

## Security, provenance, and licensing

- Report vulnerabilities through [GitHub Security Advisories](https://github.com/k3ss-official/kanban-surface/security/advisories/new), not a public issue.
- Never commit credentials, live hostnames, customer data, or real work-ledger content.
- This repository's original code is MIT licensed; see [`LICENSE`](LICENSE).
- Hermes Agent's Kanban implementation is distributed under the upstream Hermes Agent MIT licence. The generic Kanban method is not copied product code.
- External projects, packages, services, and images retain their own licences; see [`THIRD_PARTY.md`](THIRD_PARTY.md).
- Kanban Surface is an independent project and is not an official Nous Research product.

## Contributing

Read [`CONTRIBUTING.md`](CONTRIBUTING.md), preserve the invariants, include tests for changed behaviour, and keep examples synthetic. Conventional Commits are preferred.

## What “green” means

GitHub Actions runs all offline suites on pull requests and pushes to `main`. The suite uses a real temporary Git repository and bare remote to prove the ledger → intake → dispatch → receipt → Git loop without touching a live ledger.

A green CI run proves the repository's deterministic paths. It does **not** prove your provider credentials, remote proxy, live Open Notebook, or production deployment. That is what the explicit smoke sequence is for.
