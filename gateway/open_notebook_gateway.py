#!/usr/bin/env python3
"""Role-scoped HTTP gateway for an Open Notebook instance.

Open Notebook has one instance password and its upstream MCP exposes full CRUD.
This gateway keeps that password away from Hermes profiles and exchanges two
independent capability tokens for a deliberately small read or append/update
surface. Delete, credential, model, settings, chat, and admin routes are never
proxied.
"""

from __future__ import annotations

import hmac
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import unquote, urlsplit

import httpx


MAX_BODY_BYTES = 10 * 1024 * 1024
READ_GET = (
    re.compile(r"^/api/notebooks(?:/[^/]+)?$"),
    re.compile(r"^/api/sources(?:/[^/]+)?$"),
    re.compile(r"^/api/notes(?:/[^/]+)?$"),
)
READ_POST = {"/api/search"}
WRITE_POST = {"/api/notebooks", "/api/sources", "/api/sources/json", "/api/notes"}
WRITE_PUT = (
    re.compile(r"^/api/notebooks/[^/]+$"),
    re.compile(r"^/api/sources/[^/]+$"),
    re.compile(r"^/api/notes/[^/]+$"),
)


def _secret(name: str) -> str:
    file_name = os.environ.get(f"{name}_FILE")
    if file_name:
        value = Path(file_name).read_text(encoding="utf-8").strip()
    else:
        value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"{name} is required")
    return value


class GatewayConfig:
    def __init__(self) -> None:
        self.upstream = os.environ.get(
            "OPEN_NOTEBOOK_UPSTREAM_URL", "http://127.0.0.1:5055"
        ).rstrip("/")
        self.upstream_password = _secret("OPEN_NOTEBOOK_UPSTREAM_PASSWORD")
        self.reader_token = _secret("OPEN_NOTEBOOK_READER_TOKEN")
        self.writer_token = _secret("OPEN_NOTEBOOK_WRITER_TOKEN")
        if hmac.compare_digest(self.reader_token, self.writer_token):
            raise RuntimeError("reader and writer tokens must be different")


CONFIG: GatewayConfig


def _role(authorization: str | None) -> str | None:
    if not authorization or not authorization.startswith("Bearer "):
        return None
    supplied = authorization[7:]
    if hmac.compare_digest(supplied, CONFIG.writer_token):
        return "writer"
    if hmac.compare_digest(supplied, CONFIG.reader_token):
        return "reader"
    return None


def _allowed(role: str, method: str, raw_path: str) -> bool:
    path = unquote(urlsplit(raw_path).path)
    if ".." in path.split("/"):
        return False
    if method == "GET" and any(pattern.fullmatch(path) for pattern in READ_GET):
        return True
    if method == "POST" and path in READ_POST:
        return True
    if role != "writer":
        return False
    if method == "POST" and path in WRITE_POST:
        return True
    return method == "PUT" and any(pattern.fullmatch(path) for pattern in WRITE_PUT)


class Handler(BaseHTTPRequestHandler):
    server_version = "KSMOpenNotebookGateway/1"

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _proxy(self) -> None:
        if self.command == "GET" and urlsplit(self.path).path == "/healthz":
            self._json(HTTPStatus.OK, {"ok": True})
            return
        role = _role(self.headers.get("Authorization"))
        if role is None:
            self._json(HTTPStatus.UNAUTHORIZED, {"detail": "invalid capability token"})
            return
        if not _allowed(role, self.command, self.path):
            self._audit(role, HTTPStatus.FORBIDDEN)
            self._json(
                HTTPStatus.FORBIDDEN, {"detail": "route denied by capability policy"}
            )
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"detail": "invalid content length"})
            return
        if length > MAX_BODY_BYTES:
            self._json(
                HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"detail": "request too large"}
            )
            return
        body = self.rfile.read(length) if length else None
        headers = {
            "Authorization": f"Bearer {CONFIG.upstream_password}",
            "Accept": "application/json",
        }
        content_type = self.headers.get("Content-Type")
        if content_type:
            headers["Content-Type"] = content_type
        try:
            response = httpx.request(
                self.command,
                f"{CONFIG.upstream}{self.path}",
                content=body,
                headers=headers,
                follow_redirects=False,
                timeout=60.0,
            )
        except httpx.HTTPError:
            self._audit(role, HTTPStatus.BAD_GATEWAY)
            self._json(HTTPStatus.BAD_GATEWAY, {"detail": "Open Notebook unavailable"})
            return
        self._audit(role, response.status_code)
        self.send_response(response.status_code)
        self.send_header(
            "Content-Type", response.headers.get("Content-Type", "application/json")
        )
        self.send_header("Content-Length", str(len(response.content)))
        self.end_headers()
        self.wfile.write(response.content)

    def _audit(self, role: str, status: int) -> None:
        print(
            json.dumps(
                {
                    "event": "open_notebook_gateway",
                    "role": role,
                    "method": self.command,
                    "path": urlsplit(self.path).path,
                    "status": int(status),
                },
                separators=(",", ":"),
            ),
            file=sys.stderr,
            flush=True,
        )

    do_GET = _proxy
    do_POST = _proxy
    do_PUT = _proxy
    do_DELETE = _proxy

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> int:
    global CONFIG
    CONFIG = GatewayConfig()
    host = os.environ.get("OPEN_NOTEBOOK_GATEWAY_HOST", "127.0.0.1")
    port = int(os.environ.get("OPEN_NOTEBOOK_GATEWAY_PORT", "8765"))
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Open Notebook capability gateway listening on {host}:{port}", flush=True)
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
