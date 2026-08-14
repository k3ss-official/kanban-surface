#!/usr/bin/env python3
"""Minimal role-aware MCP adapter for the KSM Open Notebook gateway."""

from __future__ import annotations

import os
from typing import Any

import httpx
from mcp.server.fastmcp import FastMCP


MODE = os.environ.get("OPEN_NOTEBOOK_MODE", "read").strip().lower()
if MODE not in {"read", "write"}:
    raise RuntimeError("OPEN_NOTEBOOK_MODE must be read or write")

BASE_URL = os.environ.get("OPEN_NOTEBOOK_GATEWAY_URL", "http://127.0.0.1:8765").rstrip(
    "/"
)
TOKEN = os.environ.get("OPEN_NOTEBOOK_ACCESS_TOKEN", "").strip()
if not TOKEN:
    raise RuntimeError("OPEN_NOTEBOOK_ACCESS_TOKEN is required")

mcp = FastMCP(f"open-notebook-{MODE}")


async def _request(
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    headers = {"Authorization": f"Bearer {TOKEN}"}
    async with httpx.AsyncClient(timeout=60.0, follow_redirects=False) as client:
        response = await client.request(
            method, f"{BASE_URL}{path}", params=params, json=payload, headers=headers
        )
    if response.is_error:
        detail = "request failed"
        try:
            detail = response.json().get("detail", detail)
        except (ValueError, AttributeError):
            pass
        raise RuntimeError(
            f"Open Notebook returned HTTP {response.status_code}: {detail}"
        )
    return response.json() if response.content else {"ok": True}


@mcp.tool()
async def list_notebooks(archived: bool | None = None) -> Any:
    """List Open Notebook notebooks without changing state."""
    params = {"order_by": "updated desc"}
    if archived is not None:
        params["archived"] = archived
    return await _request("GET", "/api/notebooks", params=params)


@mcp.tool()
async def get_notebook(notebook_id: str) -> Any:
    """Read one notebook by its exact identifier."""
    return await _request("GET", f"/api/notebooks/{notebook_id}")


@mcp.tool()
async def list_sources(notebook_id: str | None = None, limit: int = 20) -> Any:
    """List sources, optionally constrained to one notebook."""
    params: dict[str, Any] = {"limit": max(1, min(limit, 100)), "offset": 0}
    if notebook_id:
        params["notebook_id"] = notebook_id
    return await _request("GET", "/api/sources", params=params)


@mcp.tool()
async def get_source(source_id: str) -> Any:
    """Read one source by its exact identifier."""
    return await _request("GET", f"/api/sources/{source_id}")


@mcp.tool()
async def list_notes(notebook_id: str | None = None, limit: int = 20) -> Any:
    """List notes, optionally constrained to one notebook."""
    params: dict[str, Any] = {}
    if notebook_id:
        params["notebook_id"] = notebook_id
    notes = await _request("GET", "/api/notes", params=params)
    if not isinstance(notes, list):
        return notes
    return notes[: max(1, min(limit, 100))]


@mcp.tool()
async def get_note(note_id: str) -> Any:
    """Read one note by its exact identifier."""
    return await _request("GET", f"/api/notes/{note_id}")


@mcp.tool()
async def search_notebook(
    query: str, search_type: str = "text", limit: int = 10
) -> Any:
    """Search verified content across the Open Notebook instance."""
    payload: dict[str, Any] = {
        "query": query,
        "type": search_type,
        "limit": max(1, min(limit, 50)),
    }
    return await _request("POST", "/api/search", payload=payload)


if MODE == "write":

    @mcp.tool()
    async def create_notebook(name: str, description: str | None = None) -> Any:
        """Create a notebook after the knowledge admission gate has passed."""
        payload: dict[str, Any] = {"name": name}
        if description is not None:
            payload["description"] = description
        return await _request("POST", "/api/notebooks", payload=payload)

    @mcp.tool()
    async def update_notebook(
        notebook_id: str,
        name: str | None = None,
        description: str | None = None,
        archived: bool | None = None,
    ) -> Any:
        """Update notebook metadata; this adapter never exposes deletion."""
        payload = {
            key: value
            for key, value in {
                "name": name,
                "description": description,
                "archived": archived,
            }.items()
            if value is not None
        }
        return await _request("PUT", f"/api/notebooks/{notebook_id}", payload=payload)

    @mcp.tool()
    async def create_link_source(
        notebook_id: str, url: str, title: str | None = None, embed: bool = True
    ) -> Any:
        """Add one URL source to an approved notebook evidence package."""
        payload: dict[str, Any] = {
            "notebook_id": notebook_id,
            "type": "link",
            "url": url,
            "embed": embed,
        }
        if title is not None:
            payload["title"] = title
        return await _request("POST", "/api/sources", payload=payload)

    @mcp.tool()
    async def update_source(
        source_id: str, title: str | None = None, topics: list[str] | None = None
    ) -> Any:
        """Update approved source metadata; this adapter never exposes deletion."""
        payload = {
            key: value
            for key, value in {"title": title, "topics": topics}.items()
            if value is not None
        }
        return await _request("PUT", f"/api/sources/{source_id}", payload=payload)

    @mcp.tool()
    async def create_note(
        notebook_id: str,
        title: str,
        content: str,
    ) -> Any:
        """Commit an approved evidence note to Open Notebook."""
        payload: dict[str, Any] = {
            "notebook_id": notebook_id,
            "title": title,
            "content": content,
        }
        return await _request("POST", "/api/notes", payload=payload)

    @mcp.tool()
    async def update_note(
        note_id: str,
        title: str | None = None,
        content: str | None = None,
    ) -> Any:
        """Supersede or correct an approved note without deleting history."""
        payload = {
            key: value
            for key, value in {
                "title": title,
                "content": content,
            }.items()
            if value is not None
        }
        return await _request("PUT", f"/api/notes/{note_id}", payload=payload)


def main() -> None:
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
