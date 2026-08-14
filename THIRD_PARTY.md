# Third-party software

Kanban Surface is MIT-licensed. It does not vendor third-party source code, but some features depend on separately installed or separately pulled software.

## Python dependencies

Versions used by the test and integration suite are pinned in [`requirements.txt`](requirements.txt).

| Dependency | Purpose | License |
|---|---|---|
| [PyYAML](https://github.com/yaml/pyyaml) | Profile configuration rendering and validation | MIT |
| [HTTPX](https://github.com/encode/httpx) | Open Notebook capability gateway and MCP adapter HTTP client | BSD-3-Clause |
| [MCP Python SDK](https://github.com/modelcontextprotocol/python-sdk) | Open Notebook MCP server | MIT |

Development checks pinned in [`requirements-dev.txt`](requirements-dev.txt) use [Black](https://github.com/psf/black) and [Ruff](https://github.com/astral-sh/ruff), both MIT-licensed.

The core board abstraction, Git sync, permission gateway, watcher, UI, local demo, and `mcp/ks_mcp.py` use the Python standard library only. The Open Notebook adapter and profile installer use the packages above.

## Runtime integrations

| Software | How it is used | License |
|---|---|---|
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Host orchestration runtime and Kanban execution substrate | MIT |
| [Open Notebook](https://github.com/lfnovo/open-notebook) | Optional private evidence store, pulled as a pinned container image | MIT |
| [Last30days](https://github.com/mvanhorn/last30days-skill) | Optional pinned research skill for `research-signal` | MIT |
| [1Password CLI](https://developer.1password.com/docs/cli) | Optional host-side rendering of ephemeral profile secrets | Proprietary; subject to 1Password terms |
| [SurrealDB](https://github.com/surrealdb/surrealdb) | Open Notebook database, pulled as a pinned v2 container image | Business Source License 1.1; not an OSI open-source licence |

Container images and optional integrations are downloaded separately at deployment time; they are not redistributed in this repository. SurrealDB's licence is version-specific: the current upstream licence identifies SurrealDB 3.0, restricts use as a database service, and changes to Apache-2.0 on its stated change date. Review the licence shipped with the exact pinned image before redistribution, managed-service use, or commercial packaging.

## Upstream notices

Hermes Agent, Open Notebook, Last30days, and the MCP Python SDK were verified through their GitHub license metadata as MIT-licensed when this notice was written. Their copyright notices remain with their respective projects.
