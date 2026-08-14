#!/usr/bin/env python3
"""Drive ks_mcp.py over real stdio against a throwaway gateway, exercising the full
JSON-RPC handshake + each tool + a permission refusal. Run anywhere:

    python3 ks/tests/test_mcp.py
"""

import json
import os
import pathlib
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

KS = pathlib.Path(__file__).parent.parent
PORT = 8749


# Minimal fake gateway: allows list/create/comment, refuses move-to-audit (like a grok token).
class Fake(BaseHTTPRequestHandler):
    def _send(self, code, payload):
        b = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.headers.get("Authorization") != "Bearer test":
            return self._send(401, {"error": "bad token"})
        self._send(
            200,
            [
                {
                    "id": "t_1",
                    "assignee": "sys-intake",
                    "status": "ready",
                    "title": "demo",
                    "body": "cm_ref: M20",
                }
            ],
        )

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length) or b"{}")
        if self.path.endswith("/move") and body.get("board") == "sys-audit":
            return self._send(403, {"error": "contributor may not move to sys-audit"})
        self._send(200, {"ok": True, "echo": body})

    def log_message(self, *a):
        pass


def rpc(proc, obj):
    proc.stdin.write(json.dumps(obj) + "\n")
    proc.stdin.flush()
    if obj.get("id") is None:
        return None
    return json.loads(proc.stdout.readline())


def main() -> int:
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), Fake)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)

    env = {
        **os.environ,
        "KS_GATEWAY_URL": f"http://127.0.0.1:{PORT}",
        "KS_TOKEN": "test",
    }
    proc = subprocess.Popen(
        [sys.executable, str(KS / "mcp" / "ks_mcp.py")],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        text=True,
        env=env,
    )
    fails = []
    try:
        init = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {"protocolVersion": "2025-11-25"},
            },
        )
        assert init["result"]["protocolVersion"] == "2025-11-25", "protocol echo"
        assert init["result"]["serverInfo"]["name"] == "kanban-surface"
        print("PASS initialize")

        rpc(
            proc, {"jsonrpc": "2.0", "method": "notifications/initialized"}
        )  # no response

        tools = rpc(proc, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in tools["result"]["tools"]}
        assert names == {
            "ks_list",
            "ks_create",
            "ks_move",
            "ks_comment",
            "ks_archive",
        }, names
        print("PASS tools/list:", sorted(names))

        r = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "ks_list", "arguments": {}},
            },
        )
        assert r["result"]["isError"] is False
        assert "cm_ref: M20" in r["result"]["content"][0]["text"]
        print("PASS ks_list")

        r = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 4,
                "method": "tools/call",
                "params": {
                    "name": "ks_create",
                    "arguments": {"title": "new work", "body": "cm_ref: M99"},
                },
            },
        )
        assert (
            r["result"]["isError"] is False
            and '"ok": true' in r["result"]["content"][0]["text"]
        )
        print("PASS ks_create")

        # The money test: a refused move surfaces as isError:true with the gateway's reason.
        r = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 5,
                "method": "tools/call",
                "params": {
                    "name": "ks_move",
                    "arguments": {"task_id": "t_1", "board": "sys-audit"},
                },
            },
        )
        assert r["result"]["isError"] is True, "refusal must be a tool error"
        assert "may not move to sys-audit" in r["result"]["content"][0]["text"]
        print(
            "PASS ks_move refusal surfaced:",
            r["result"]["content"][0]["text"].strip()[:60],
        )

        r = rpc(
            proc,
            {
                "jsonrpc": "2.0",
                "id": 6,
                "method": "tools/call",
                "params": {
                    "name": "ks_move",
                    "arguments": {"task_id": "t_1", "board": "work-engineering"},
                },
            },
        )
        assert r["result"]["isError"] is False
        print("PASS ks_move allowed")
    except AssertionError as e:
        fails.append(str(e))
    finally:
        proc.terminate()
        srv.shutdown()

    if fails:
        print("\nFAILURES:", *fails, sep="\n  ")
        return 1
    print("\nALL MCP TESTS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
