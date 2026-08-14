#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import importlib.util
import json
import os
from pathlib import Path
import unittest


ROOT = Path(__file__).parent.parent
MANIFEST = json.loads((ROOT / "profiles" / "manifest.json").read_text())


def load_gateway():
    spec = importlib.util.spec_from_file_location(
        "open_notebook_gateway", ROOT / "gateway" / "open_notebook_gateway.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def mcp_tools(mode: str):
    old = {
        key: os.environ.get(key)
        for key in ("OPEN_NOTEBOOK_MODE", "OPEN_NOTEBOOK_ACCESS_TOKEN")
    }
    os.environ["OPEN_NOTEBOOK_MODE"] = mode
    os.environ["OPEN_NOTEBOOK_ACCESS_TOKEN"] = "test-only-token"
    try:
        spec = importlib.util.spec_from_file_location(
            f"open_notebook_mcp_{mode}", ROOT / "mcp" / "open_notebook_mcp.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        return {tool.name: tool for tool in asyncio.run(module.mcp.list_tools())}
    except ImportError as e:
        raise unittest.SkipTest(f"MCP runtime not available in this environment: {e}")
    finally:
        for key, value in old.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value


class TestOpenNotebookBoundary(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gateway = load_gateway()

    def test_manifest_has_one_writer_and_pinned_image(self):
        integration = MANIFEST["integrations"]["open_notebook"]
        self.assertEqual(integration["writer_profile"], "knowledge-custodian")
        self.assertIn("@sha256:", integration["image"])
        writers = [
            item["name"]
            for item in MANIFEST["profiles"]
            if item.get("open_notebook_access") == "write"
        ]
        self.assertEqual(writers, ["knowledge-custodian"])

    def test_reader_policy_is_read_only(self):
        allowed = self.gateway._allowed
        self.assertTrue(allowed("reader", "GET", "/api/notebooks"))
        self.assertTrue(allowed("reader", "GET", "/api/notes/note:1"))
        self.assertTrue(allowed("reader", "POST", "/api/search"))
        self.assertFalse(allowed("reader", "POST", "/api/notes"))
        self.assertFalse(allowed("reader", "PUT", "/api/notebooks/notebook:1"))
        self.assertFalse(allowed("reader", "DELETE", "/api/notes/note:1"))

    def test_writer_policy_is_narrow_and_non_destructive(self):
        allowed = self.gateway._allowed
        self.assertTrue(allowed("writer", "POST", "/api/notebooks"))
        self.assertTrue(allowed("writer", "POST", "/api/sources"))
        self.assertTrue(allowed("writer", "POST", "/api/notes"))
        self.assertTrue(allowed("writer", "PUT", "/api/notes/note:1"))
        self.assertFalse(allowed("writer", "DELETE", "/api/notes/note:1"))
        self.assertFalse(allowed("writer", "POST", "/api/credentials"))
        self.assertFalse(allowed("writer", "PUT", "/api/settings"))
        self.assertFalse(allowed("writer", "POST", "/api/models"))
        self.assertFalse(allowed("writer", "GET", "/api/../credentials"))

    def test_mcp_reader_exposes_no_mutations(self):
        tools = mcp_tools("read")
        self.assertIn("search_notebook", tools)
        self.assertIn("list_notebooks", tools)
        self.assertFalse(
            any(name.startswith(("create_", "update_", "delete_")) for name in tools)
        )
        search_properties = tools["search_notebook"].inputSchema["properties"]
        self.assertNotIn("notebook_id", search_properties)

    def test_mcp_writer_can_append_but_not_delete_or_administer(self):
        tools = mcp_tools("write")
        self.assertIn("create_note", tools)
        self.assertIn("update_note", tools)
        self.assertFalse(any(name.startswith("delete_") for name in tools))
        self.assertTrue(
            set(tools).isdisjoint({"update_settings", "create_model", "delete_model"})
        )
        self.assertNotIn("topics", tools["create_note"].inputSchema["properties"])
        self.assertNotIn("topics", tools["update_note"].inputSchema["properties"])

    def test_compose_uses_three_separate_notebook_networks(self):
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn("notebook_db:", compose)
        self.assertIn("notebook_api:", compose)
        self.assertIn("hermes_notebook:", compose)
        self.assertIn("127.0.0.1:${OPEN_NOTEBOOK_API_PORT:-5055}:5055", compose)
        self.assertNotIn("OPEN_NOTEBOOK_PASSWORD=", compose)


if __name__ == "__main__":
    unittest.main(verbosity=2)
