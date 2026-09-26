# Kanban Surface MCP adapter

`mcp/ks_mcp.py` is an **optional outsider interface**. It is **off by default**.

This snapshot does not generate a live `KS_TOKEN`, does not bind `0.0.0.0`, and does not enable systemd. Do not turn the shim on as part of a clean checkout.

When an operator later enables it, the adapter wraps the Kanban Surface gateway as native MCP tools. The adapter holds no authority: identity and permissions come from `KS_TOKEN`, and every call is checked by the gateway's per-token policy. `ks_create` always lands on `sys-intake`.

## Tools

| Tool | Operation | Required permission |
|---|---|---|
| `ks_list` | Read the board | read |
| `ks_create` | Create a card on intake | `create` |
| `ks_move` | Move a card and dispatch its station | allowed `move_to` target |
| `ks_comment` | Comment on a card | `comment` |
| `ks_archive` | Archive a card | `archive` |

A denied operation returns an MCP tool error containing the gateway's refusal reason.

## Requirements (only if you enable it)

The core shim is stdlib-only. The repository still is not a PyPI package:

```bash
python3 -m pip install -r requirements.txt
```

Set two environment variables in the **local process environment**, not in git:

- `KS_GATEWAY_URL` — gateway URL. Local default is `http://127.0.0.1:8742`.
- `KS_TOKEN` — bearer token for one stable gateway actor that you create yourself.

Never commit the token. Never bind the host gateway to `0.0.0.0`.

## Hermes Agent

Add the server through Hermes configuration or the MCP dashboard **only after** you have a loopback gateway and a token you generated yourself:

```yaml
mcp_servers:
  kanban-surface:
    command: python3
    args: ["/absolute/path/to/kanban-surface/mcp/ks_mcp.py"]
    env:
      KS_GATEWAY_URL: "http://127.0.0.1:8742"
      KS_TOKEN: "${KS_TOKEN}"
```

## Generic MCP client

Clients using the `mcpServers` JSON shape can use:

```json
{
  "mcpServers": {
    "kanban-surface": {
      "command": "python3",
      "args": ["/absolute/path/to/kanban-surface/mcp/ks_mcp.py"],
      "env": {
        "KS_GATEWAY_URL": "http://127.0.0.1:8742",
        "KS_TOKEN": "${KS_TOKEN}"
      }
    }
  }
}
```

Confirm how your client resolves environment-variable placeholders. If it does not, inject the token through the client's secret mechanism rather than writing it into a tracked file.

## Stdio smoke test

With a **local** gateway already running on loopback, invoke the adapter through the shell:

```bash
printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-11-25"}}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}' \
  '{"jsonrpc":"2.0","id":3,"method":"tools/call","params":{"name":"ks_list","arguments":{}}}' \
  | env KS_GATEWAY_URL=http://127.0.0.1:8742 KS_TOKEN="$KS_TOKEN" \
      python3 mcp/ks_mcp.py
```

## Automated verification

```bash
python3 tests/test_mcp.py
```

The test drives the real stdio process through initialization, tool discovery, calls, and a permission refusal against a throwaway **loopback** gateway. It does not need live Hermes.
