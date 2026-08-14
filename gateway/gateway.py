#!/usr/bin/env python3
"""The permission gateway (spec §8) — the ONLY network-facing piece of KS.

Narrow verbs, a per-token rule table, and an audit line for every call carrying the
requester's identity. The board itself stays localhost-only; this is what nginx/TLS fronts.

  GET  /tasks                  list the board
  GET  /workers                truthful executing-worker count
  GET  /healthz                liveness (no auth — for the supervisor, exposes nothing)
  POST /tasks                  {title, body}   create (always lands on intake)
  POST /tasks/<id>/move        {board}         THE dispatch primitive
  POST /tasks/<id>/comment     {text}
  POST /tasks/<id>/archive
  GET  /                       the UI (static HTML; data still needs a token)
"""

from __future__ import annotations

import datetime
import json
import pathlib
import re
import sys
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "sync"))
import board as board_mod  # noqa: E402
import ksconfig  # noqa: E402
import workers  # noqa: E402

TASK_PATH = re.compile(r"^/tasks/([A-Za-z0-9_\-]{1,64})/(move|comment|archive)$")
TASK_GET = re.compile(r"^/tasks/([A-Za-z0-9_\-]{1,64})$")
TASK_SOURCE = re.compile(r"^/tasks/([A-Za-z0-9_\-]{1,64})/source$")
UI = pathlib.Path(__file__).parent.parent / "ui" / "index.html"
MAX_BODY = 64 * 1024
SOURCE_LINE = re.compile(r"^source:\s*(.+?)\s*$", re.MULTILINE)
ALLOWED_SOURCE = re.compile(
    r"^(?:MASTER\.md|daily/\d{4}-\d{2}-\d{2}\.md|projects/[A-Za-z0-9_.-]+\.md)$"
)


class Gateway:
    """Transport-free core: permission decisions + audit. Directly unit-testable."""

    def __init__(self, cfg: dict, brd: board_mod.Board):
        self.cfg = cfg
        self.board = brd
        self.gw = cfg["gateway"]
        self.boards = cfg.get("boards", [])

    def audit(self, agent: str, verb: str, detail: dict, allowed: bool) -> None:
        entry = {
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "agent": agent,
            "verb": verb,
            "allowed": allowed,
            **detail,
        }
        path = self.gw.get("audit_log")
        if not path:
            return
        p = pathlib.Path(path)
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a") as f:
            f.write(json.dumps(entry) + "\n")

    def identify(self, authorization: str | None) -> dict | None:
        if not authorization or not authorization.startswith("Bearer "):
            return None
        return self.gw["tokens"].get(authorization[7:].strip())

    # --- verbs: each returns (http_status, payload) ---

    def list_tasks(self, tok: dict):
        self.audit(tok["agent"], "list", {}, True)
        return 200, self.board.list_tasks()

    def list_workers(self, tok: dict):
        self.audit(tok["agent"], "workers", {}, True)
        return 200, workers.project(self.board.list_tasks())

    def show(self, tok: dict, task_id: str):
        """Card detail incl. its receipts. Read is open to every valid token — the whole
        point of the shared board is that everyone can see the same state."""
        self.audit(tok["agent"], "show", {"task": task_id}, True)
        return 200, self.board.show(task_id)

    def source(self, tok: dict, task_id: str):
        """Return the canonical work-ledger file linked by a card.

        This is deliberately card-scoped rather than a general file API: callers
        cannot choose a path, and only the three supported ledger source families are
        accepted. Source is fetched only when a human opens a card.
        """
        task = self.board.show(task_id)
        match = SOURCE_LINE.search(str(task.get("body") or ""))
        if not match or not ALLOWED_SOURCE.fullmatch(match.group(1)):
            self.audit(tok["agent"], "source", {"task": task_id}, False)
            return 404, {"error": "card has no readable work-ledger source"}
        relative = match.group(1)
        root = pathlib.Path(self.cfg["repo_dir"]).resolve()
        source = (root / relative).resolve()
        try:
            source.relative_to(root)
        except ValueError:
            self.audit(tok["agent"], "source", {"task": task_id}, False)
            return 404, {"error": "card source is outside the work ledger"}
        if not source.is_file():
            self.audit(tok["agent"], "source", {"task": task_id}, False)
            return 404, {"error": "work-ledger source is unavailable"}
        base = str(self.cfg.get("source_base_url") or "").rstrip("/")
        self.audit(tok["agent"], "source", {"task": task_id, "source": relative}, True)
        return 200, {
            "path": relative,
            "url": f"{base}/{relative}" if base else "",
            "markdown": source.read_text(encoding="utf-8"),
        }

    def create(self, tok: dict, body: dict):
        agent = tok["agent"]
        if not tok.get("create"):
            self.audit(agent, "create", {}, False)
            return 403, {"error": f"{agent} may not create"}
        title = (body.get("title") or "").strip()
        if not title:
            return 400, {"error": "title required"}
        # External creates always land on intake for triage — no direct-to-board injection.
        # Keying on the title would be wrong: two cards may legitimately share one, and the
        # collision would silently hand back someone else's card. Callers that need a retry
        # to be safe pass their own key; everyone else gets a fresh card per request.
        client_key = str(body.get("idempotency_key") or "").strip()[:64]
        task = self.board.create(
            title=title[:120],
            body=(body.get("body") or "") + f"\ncreated_by: {agent}",
            assignee="sys-intake",
            idempotency_key=(
                f"gw:{agent}:{client_key}" if client_key else f"gw:{uuid.uuid4().hex}"
            ),
        )
        self.audit(agent, "create", {"task": task.get("id"), "title": title[:80]}, True)
        return 201, task

    def move(self, tok: dict, task_id: str, body: dict):
        agent = tok["agent"]
        target = body.get("board", "")
        if self.boards and target not in self.boards:
            self.audit(agent, "move", {"task": task_id, "board": target}, False)
            return 400, {"error": f"unknown board: {target}"}
        if target not in tok.get("move_to", []):
            self.audit(agent, "move", {"task": task_id, "board": target}, False)
            return 403, {"error": f"{agent} may not move to {target}"}
        self.board.move_to_board(task_id, target, actor=agent)
        self.audit(agent, "move", {"task": task_id, "board": target}, True)
        return 200, {"ok": True, "task": task_id, "board": target}

    def comment(self, tok: dict, task_id: str, body: dict):
        agent = tok["agent"]
        if not tok.get("comment"):
            self.audit(agent, "comment", {"task": task_id}, False)
            return 403, {"error": f"{agent} may not comment"}
        text = (body.get("text") or "").strip()
        if not text:
            return 400, {"error": "text required"}
        self.board.comment(task_id, text, author=agent)
        self.audit(agent, "comment", {"task": task_id}, True)
        return 200, {"ok": True}

    def archive(self, tok: dict, task_id: str, body: dict):
        agent = tok["agent"]
        if not tok.get("archive"):
            self.audit(agent, "archive", {"task": task_id}, False)
            return 403, {"error": f"{agent} may not archive"}
        self.board.archive(task_id)
        self.audit(agent, "archive", {"task": task_id}, True)
        return 200, {"ok": True}


def make_handler(gateway: Gateway):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def _send(self, code: int, payload, content_type="application/json"):
            body = (
                payload if isinstance(payload, bytes) else json.dumps(payload).encode()
            )
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json_body(self):
            length = int(self.headers.get("Content-Length") or 0)
            if length > MAX_BODY:
                # Never leave an unread body on a keep-alive connection — it would be
                # parsed as the next request. Close instead of trying to drain it.
                self.close_connection = True
                return None
            raw = self.rfile.read(length) if length else b"{}"
            try:
                parsed = json.loads(raw or b"{}")
            except json.JSONDecodeError:
                return None
            return parsed if isinstance(parsed, dict) else None

        def do_GET(self):
            if self.path == "/healthz":
                return self._send(200, {"ok": True})
            if self.path == "/" and UI.exists():
                return self._send(200, UI.read_bytes(), "text/html; charset=utf-8")
            tok = gateway.identify(self.headers.get("Authorization"))
            if not tok:
                return self._send(401, {"error": "bad token"})
            if self.path == "/tasks":
                return self._send(*gateway.list_tasks(tok))
            if self.path == "/workers":
                return self._send(*gateway.list_workers(tok))
            m = TASK_SOURCE.match(self.path)
            if m:
                try:
                    return self._send(*gateway.source(tok, m.group(1)))
                except board_mod.BoardError as e:
                    return self._send(404, {"error": str(e)})
            m = TASK_GET.match(self.path)
            if m:
                try:
                    return self._send(*gateway.show(tok, m.group(1)))
                except board_mod.BoardError as e:
                    return self._send(404, {"error": str(e)})
            return self._send(404, {"error": "unknown path"})

        def do_POST(self):
            tok = gateway.identify(self.headers.get("Authorization"))
            if not tok:
                return self._send(401, {"error": "bad token"})
            body = self._json_body()
            if body is None:
                return self._send(400, {"error": "invalid or oversized JSON body"})

            if self.path == "/tasks":
                return self._send(*gateway.create(tok, body))
            m = TASK_PATH.match(self.path)
            if not m:
                return self._send(404, {"error": "unknown path"})
            task_id, verb = m.groups()
            try:
                handler = {
                    "move": gateway.move,
                    "comment": gateway.comment,
                    "archive": gateway.archive,
                }[verb]
                return self._send(*handler(tok, task_id, body))
            except board_mod.BoardError as e:
                return self._send(502, {"error": f"board error: {e}"})

        def log_message(self, *args):
            pass  # the audit JSONL is the log

    return Handler


def main() -> int:
    cfg = ksconfig.load()
    gw = Gateway(cfg, board_mod.get_board(cfg))
    bind, port = cfg["gateway"]["bind"], cfg["gateway"]["port"]
    srv = ThreadingHTTPServer((bind, port), make_handler(gw))
    print(
        f"ks gateway on {bind}:{port} — {len(cfg['gateway']['tokens'])} tokens",
        flush=True,
    )
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())
