#!/usr/bin/env python3
"""Guard the legacy receipt parser and the native persistent-profile contract.

The custom surface still parses historical ``AGENT ...`` comments, but the current
profile team uses native Hermes Kanban terminal calls rather than prose station receipts.

    python3 tests/test_receipts.py
"""

from __future__ import annotations

import pathlib
import json
import re
import sys
import unittest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "sync"))
import receipts as R  # noqa: E402

SOULS = sorted((ROOT / "profiles").glob("*/SOUL.md"))
SOULS = [s for s in SOULS if s.parent.name != "ksm"]
# Any all-caps AGENT/KSM phrase in a SOUL is claiming to be part of the grammar.
TOKEN_RE = re.compile(r"\b(?:AGENT|KSM)(?: [A-Z][A-Z-]*)+")


class TestGrammar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads((ROOT / "profiles" / "manifest.json").read_text())
        cls.profiles = {item["name"]: item for item in cls.manifest["profiles"]}

    def test_souls_exist(self):
        self.assertEqual(
            len(SOULS), 15, f"expected 15 specialist SOULs, found {len(SOULS)}"
        )
        self.assertEqual({s.parent.name for s in SOULS}, set(self.profiles))

    def test_souls_invent_no_unknown_tokens(self):
        known = set(R.ALL) | set(R.SYSTEM)
        for soul in SOULS:
            for found in TOKEN_RE.findall(soul.read_text()):
                # Longest known token that this phrase starts with, if any.
                if not any(found.startswith(k) for k in known):
                    self.fail(
                        f"{soul.parent.name} uses unknown receipt token "
                        f"'{found}' — add it to sync/receipts.py or fix the SOUL"
                    )

    def test_persistent_profiles_do_not_emit_legacy_receipts(self):
        for soul in SOULS:
            self.assertFalse(
                TOKEN_RE.search(soul.read_text()),
                f"{soul.parent.name} must use native Kanban lifecycle tools",
            )

    def test_every_profile_uses_native_kanban_and_forbids_delegation(self):
        for name, profile in self.profiles.items():
            self.assertIn("kanban", profile["toolsets"], name)
            self.assertNotIn("delegation", profile["toolsets"], name)
            self.assertNotIn("coding", profile["toolsets"], name)
            soul = (ROOT / "profiles" / name / "SOUL.md").read_text()
            self.assertIn("delegate_task", soul, name)

    def test_hierarchy_uses_persistent_named_profiles(self):
        roster = {"default", *self.profiles}
        for name, profile in self.profiles.items():
            self.assertIn(profile["parent"], roster, name)
        self.assertEqual(self.profiles["research-signal"]["parent"], "research-lead")
        self.assertEqual(
            self.profiles["engineering-review"]["parent"], "engineering-lead"
        )

    def test_external_mutation_audit_is_independent(self):
        audit = (ROOT / "profiles" / "audit-controller" / "SOUL.md").read_text()
        self.assertIn("Never repair", audit)
        for name in ("engineering-lead", "infra-guardian", "knowledge-custodian"):
            soul = (ROOT / "profiles" / name / "SOUL.md").read_text()
            self.assertIn("audit-controller", soul, name)

    def test_knowledge_write_authority_is_separated(self):
        custodian = (ROOT / "profiles" / "knowledge-custodian" / "SOUL.md").read_text()
        provenance = (
            ROOT / "profiles" / "knowledge-provenance" / "SOUL.md"
        ).read_text()
        self.assertIn("ONLY Hermes profile", custodian)
        self.assertIn("Never write Open Notebook", provenance)


class TestParsing(unittest.TestCase):
    def test_find_matches_only_leading_tokens(self):
        self.assertEqual(R.find("AGENT DONE — all good"), R.DONE)
        self.assertEqual(R.find("  AGENT BLOCKED what port?"), R.BLOCKED)
        self.assertIsNone(R.find("discussing AGENT DONE in passing"))
        self.assertIsNone(R.find(""))

    def test_human_hold_is_not_confused_with_human_answered(self):
        self.assertEqual(R.find(f"{R.HUMAN_HOLD} need human owner"), R.HUMAN_HOLD)
        self.assertEqual(R.find(f"{R.HUMAN_ANSWERED} yes go"), R.HUMAN_ANSWERED)

    def test_count_and_present(self):
        comments = [f"{R.REJECTED} a", "chatter", f"{R.REJECTED} b", R.KSM_FROZEN]
        self.assertEqual(R.count(comments, R.REJECTED), 2)
        self.assertTrue(R.present(comments, R.KSM_FROZEN))
        self.assertFalse(R.present(comments, R.KSM_LOOP_BREAK))

    def test_mutation_declaration_reading(self):
        self.assertIs(R.declares_mutation([f"{R.DONE}\n{R.MUTATED_KEY}: true"]), True)
        self.assertIs(R.declares_mutation([f"{R.DONE} {R.MUTATED_KEY}: false"]), False)
        # The newest declaration wins (a card can go build → reject → build again).
        self.assertIs(
            R.declares_mutation(
                [f"{R.DONE} {R.MUTATED_KEY}: false", f"{R.DONE} {R.MUTATED_KEY}: true"]
            ),
            True,
        )
        # Undeclared is NOT "false" — the caller must treat it as a protocol violation.
        self.assertIsNone(R.declares_mutation([f"{R.DONE} finished"]))
        self.assertIsNone(R.declares_mutation([]))


if __name__ == "__main__":
    unittest.main(verbosity=2)
