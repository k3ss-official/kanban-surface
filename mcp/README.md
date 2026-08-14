# Kanban Surface MCP adapter

`mcp/ks_mcp.py` exposes the Kanban Surface gateway as native MCP tools. The adapter holds no authority: identity and permissions come from `KS_TOKEN`, and every call is checked by the gateway's per-token policy.

## Tools

| Tool | Operation | Required permission |
|---|---|---|
| `ks_list` | Read the board | read |
| `ks_create` | Create a card on intake | `create` |
| `ks_move` | Move a card and dispatch its station | allowed `move_to` target |
| `ks_comment` | Comment on a card | `comment` |
| `ks_archive` | Archive a card | `archive` |

A denied operation returns an MCP tool error containing the gateway's refusal reason.

## Requirements

Install the repository dependencies:

```bash
python3 -m pip install -r requirements.txt
```

Set two environment variables:

- `KS_GATEWAY_URL` — gateway URL, for example `http://127.0.0.1:8742` in local development.
- `KS_TOKEN` — bearer token for one stable gateway actor.

Never commit the token to client configuration tracked by Git.

## Hermes Agent

Add the server through Hermes configuration or the MCP dashboard:

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

With the gateway running, invoke the adapter through the shell:

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

The test drives the real stdio process through initialization, tool discovery, calls, and a permission refusal against a throwaway gateway.
