#!/usr/bin/env python3
"""Kanban Surface MCP server — the universal plug.

Wraps the KS permission gateway as MCP tools so any MCP-capable runtime — Hermes (/mcp),
Claude Code, Claude Desktop, Codex, Cursor — gets the shared board as native tools with one
config block. The shim holds NO authority of its own: identity and scope come entirely from
KS_TOKEN, and every call still passes the gateway's per-token rule table (spec §8).

Transport: stdio JSON-RPC 2.0 (MCP 2025-11-25). Stdlib only. Config via env:
  KS_GATEWAY_URL   e.g. https://ks.example.com
  KS_TOKEN         this runtime's bearer token
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

GATEWAY = os.environ.get("KS_GATEWAY_URL", "http://127.0.0.1:8742").rstrip("/")
TOKEN = os.environ.get("KS_TOKEN", "")
PROTOCOL = "2025-11-25"
BOARDS = [
    "sys-intake",
    "work-research",
    "work-knowledge",
    "work-engineering",
    "work-infra",
    "work-writer",
    "sys-input",
    "sys-audit",
    "sys-done",
]

TOOLS = [
    {
        "name": "ks_list",
        "description": "List all cards on the shared Kanban Surface board with their board "
        "(assignee), status, cm_ref, and title. Read-only.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "ks_create",
        "description": "Create a card on the shared board. It lands on the intake board for "
        "triage — you cannot inject directly onto a work board. Include a "
        "'cm_ref: <id>' line in the body if this ties to a work-ledger item.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "Short outcome-shaped title.",
                },
                "body": {
                    "type": "string",
                    "description": "Scope in <=5 lines; optional cm_ref.",
                },
            },
            "required": ["title"],
        },
    },
    {
        "name": "ks_move",
        "description": "Move a card to a board — THE dispatch primitive. Moving a card onto a "
        "board runs that board's worker. You may only move to boards your token "
        "allows; refusals are returned verbatim.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "task_id": {"type": "string"},
                "board": {"type": "string", "enum": BOARDS},
            },
            "required": ["task_id", "board"],
        },
    },
    {
        "name": "ks_comment",
        "description": "Append a comment to a card (use the receipt grammar where it applies).",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}, "text": {"type": "string"}},
            "required": ["task_id", "text"],
        },
    },
    {
        "name": "ks_archive",
        "description": "Archive a card. Most tokens are not permitted this; refusal is returned.",
        "inputSchema": {
            "type": "object",
            "properties": {"task_id": {"type": "string"}},
            "required": ["task_id"],
        },
    },
]
TOOLS_BY_NAME = {t["name"]: t for t in TOOLS}


def _http(method: str, path: str, body: dict | None = None) -> tuple[int, object]:
    req = urllib.request.Request(
        GATEWAY + path,
        data=json.dumps(body).encode() if body is not None else None,
        method=method,
    )
    req.add_header("Authorization", f"Bearer {TOKEN}")
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except (json.JSONDecodeError, OSError):
            return e.code, {"error": f"HTTP {e.code}"}
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        return 0, {"error": f"gateway unreachable: {e}"}


def call_tool(name: str, args: dict) -> tuple[str, bool]:
    """Returns (text, is_error). Refusals and bad input are reported as tool errors — the
    model can read and act on them — never as exceptions that would kill the server."""
    spec = TOOLS_BY_NAME.get(name)
    if not spec:
        return f"unknown tool: {name}", True
    missing = [k for k in spec["inputSchema"].get("required", []) if not args.get(k)]
    if missing:
        return f"missing required argument(s): {', '.join(missing)}", True

    if name == "ks_list":
        code, payload = _http("GET", "/tasks")
    elif name == "ks_create":
        code, payload = _http(
            "POST", "/tasks", {"title": args["title"], "body": args.get("body", "")}
        )
    elif name == "ks_move":
        code, payload = _http(
            "POST", f"/tasks/{args['task_id']}/move", {"board": args["board"]}
        )
    elif name == "ks_comment":
        code, payload = _http(
            "POST", f"/tasks/{args['task_id']}/comment", {"text": args["text"]}
        )
    else:  # ks_archive
        code, payload = _http("POST", f"/tasks/{args['task_id']}/archive", {})

    return json.dumps(payload, indent=2), not (200 <= code < 300)


def handle(msg: dict) -> dict | None:
    method = msg.get("method")
    mid = msg.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": (msg.get("params") or {}).get(
                    "protocolVersion", PROTOCOL
                ),
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {
                    "name": "kanban-surface",
                    "version": "1.0.0",
                    "description": "Shared Kanban Surface board via the KS gateway",
                },
                "instructions": "Cards are work-ledger items. Moving a card to a board runs "
                "that board's worker. Your authority is fixed by your token.",
            },
        }
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": TOOLS}}
    if method == "tools/call":
        params = msg.get("params") or {}
        args = params.get("arguments")
        text, is_error = call_tool(
            params.get("name", ""), args if isinstance(args, dict) else {}
        )
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "content": [{"type": "text", "text": text}],
                "isError": is_error,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "notifications/initialized" or mid is None:
        return None  # notifications are never answered
    return {
        "jsonrpc": "2.0",
        "id": mid,
        "error": {"code": -32601, "message": f"method not found: {method}"},
    }


def main() -> int:
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(msg, dict):
            continue
        try:
            resp = handle(msg)
        except Exception as e:  # a malformed call must never take the server down
            resp = {
                "jsonrpc": "2.0",
                "id": msg.get("id"),
                "error": {"code": -32603, "message": f"internal error: {e}"},
            }
            if msg.get("id") is None:
                resp = None
        if resp is not None:
            sys.stdout.write(json.dumps(resp) + "\n")
            sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
