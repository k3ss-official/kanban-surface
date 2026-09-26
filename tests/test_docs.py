#!/usr/bin/env python3
"""Guard stranger-facing honesty for the k3ss-official repo.

These checks stay offline. They do not install a team, mint a token, or touch
a live Hermes home.
"""

from __future__ import annotations

import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parent.parent
DEAD_ORG = "anwhelan01"
LIVE_REPO = "https://github.com/k3ss-official/kanban-surface"
PUBLIC_DOCS = (
    ROOT / "README.md",
    ROOT / "SECURITY.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "mcp" / "README.md",
)
STATIONS = (
    "sys-intake",
    "work-research",
    "work-knowledge",
    "work-engineering",
    "work-infra",
    "work-writer",
    "sys-input",
    "sys-audit",
    "sys-done",
)
M4_FLOOR = ("Rae", "scout", "maker", "gatekeeper", "webdevsocials")


class TestStrangerDocs(unittest.TestCase):
    def test_public_docs_point_at_k3ss_official_not_old_copy(self):
        for path in PUBLIC_DOCS:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn(DEAD_ORG, text, path.name)
            self.assertNotIn("anwhelan01/kanban-surface", text, path.name)
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        security = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
        contributing = (ROOT / "CONTRIBUTING.md").read_text(encoding="utf-8")
        self.assertIn(f"{LIVE_REPO}.git", readme)
        self.assertIn(f"{LIVE_REPO}/security/advisories/new", readme)
        self.assertIn(f"{LIVE_REPO}/security/advisories/new", security)
        self.assertIn(LIVE_REPO, contributing)

    def test_readme_states_collab_mem_stations_and_receipts(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("collab-mem", readme)
        self.assertIn("native Hermes Kanban lifecycle", readme)
        self.assertRegex(readme, r"legacy", re.IGNORECASE)
        for station in STATIONS:
            self.assertIn(f"`{station}`", readme, station)

    def test_readme_separates_reference_team_from_m4_floor(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("16-profile", readme)
        self.assertIn("~/.hermes", readme)
        self.assertIn("not", readme.lower())
        for name in M4_FLOOR:
            self.assertIn(name, readme)
        self.assertRegex(readme, r"Do not install[^\n]*~/\.hermes")

    def test_mcp_is_optional_and_off_by_default(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        mcp = (ROOT / "mcp" / "README.md").read_text(encoding="utf-8")
        for text in (readme, mcp):
            self.assertIn("off by default", text.lower())
            self.assertNotRegex(text, r"KS_TOKEN=[A-Za-z0-9_\-]{16,}")
        self.assertIn("Do not bind the host UI or APIs to `0.0.0.0`", readme)
        self.assertIn("Never bind the host gateway to `0.0.0.0`", mcp)

    def test_pyproject_is_tooling_only(self):
        pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
        self.assertNotRegex(pyproject, r"(?m)^\[project\]")
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("not an installable Python package", readme)

    def test_default_suite_stays_offline(self):
        runner = (ROOT / "tests" / "run_all.sh").read_text(encoding="utf-8")
        self.assertIn("tests/test_docs.py", runner)
        self.assertNotIn("tests/test_live_team.py", runner)
        self.assertIn("no Hermes", runner)

    def test_license_is_mit(self):
        license_text = (ROOT / "LICENSE").read_text(encoding="utf-8")
        self.assertTrue(license_text.startswith("MIT License"))
        self.assertNotIn(DEAD_ORG, license_text)


if __name__ == "__main__":
    unittest.main(verbosity=2)
