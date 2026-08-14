#!/usr/bin/env python3
"""Offline unit tests for cm_parser — runnable anywhere: python3 tests/test_cm_parser.py

Synthetic fixtures always run. TestRealLedger additionally parses a work-ledger
checkout, so parser drift against the live ledger fails loudly — point it at one:

    WORK_LEDGER_DIR=/path/to/work-ledger python3 tests/test_cm_parser.py

Without that env var, the shipped synthetic example ledger is used.
"""

import os
import pathlib
import re
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "sync"))
import cm_parser


def _find_ledger():
    candidates = []
    if os.environ.get("WORK_LEDGER_DIR"):
        candidates.append(pathlib.Path(os.environ["WORK_LEDGER_DIR"]))
    candidates.append(pathlib.Path(__file__).parent.parent / "examples" / "ledger")
    for c in candidates:
        if (c / "MASTER.md").exists():
            return c
    return None


REPO = _find_ledger()
NO_LEDGER = REPO is None
SKIP_MSG = "no work-ledger checkout found (set WORK_LEDGER_DIR)"
MASTER_DATA_ROW = re.compile(r"^\|\s*(M\d+)\s*\|(?:[^|]*\|){4}\s*$")


class TestSynthetic(unittest.TestCase):
    def test_master_row(self):
        text = "| M99 | **Test item** — details | builder | active | some notes |"
        objs = cm_parser.parse_master(text)
        self.assertEqual(len(objs), 1)
        o = objs[0]
        self.assertEqual(o.cm_ref, "M99")
        self.assertEqual(o.title, "Test item — details")
        self.assertEqual(o.owner, "builder")
        self.assertEqual(o.status, "active")

    def test_master_status_normalisation(self):
        cases = {
            "**blocked on human**": "blocked",
            "done → drops to LOG": "done",
            "needs-decision": "needs-decision",
            "later": "later",
            "backlog": "backlog",
        }
        for raw, want in cases.items():
            text = f"| M1 | item | O | {raw} | n |"
            self.assertEqual(cm_parser.parse_master(text)[0].status, want, raw)

    def test_daily_row_and_emoji(self):
        text = "| D2 | Build the thing | M20 | Fable | ✅ done |"
        objs = cm_parser.parse_daily(text, "2026-07-19")
        self.assertEqual(objs[0].cm_ref, "2026-07-19#D2")
        self.assertEqual(objs[0].status, "done")
        self.assertIn("M20", objs[0].notes)

    def test_project_next_skips_struck(self):
        text = "## Next\n1. **Do this** first\n2. ~~already done~~\n3. Then this\n## Other\n9. not next"
        objs = cm_parser.parse_project_next(text, "projects/x.md")
        self.assertEqual(
            [o.cm_ref for o in objs], ["projects/x.md#next-1", "projects/x.md#next-3"]
        )

    def test_project_next_gaps_are_permanent(self):
        text = (
            "## Next\n"
            "1. ~~done~~ Completed 2026-07-30.\n"
            "2. Still current\n"
            "4. Added later without recycling 1 or 3"
        )
        objs = cm_parser.parse_project_next(text, "projects/x.md")
        self.assertEqual(
            [o.cm_ref for o in objs],
            ["projects/x.md#next-2", "projects/x.md#next-4"],
        )

    def test_cardable_filter(self):
        objs = cm_parser.parse_master(
            "| M1 | a | O | active | |\n| M2 | b | O | done | |\n| M3 | c | O | later | |"
        )
        self.assertEqual([o.cm_ref for o in cm_parser.cardable(objs)], ["M1"])

    def test_body_roundtrip(self):
        o = cm_parser.WorkObject(
            cm_ref="M20", title="t", owner="Fable", source="MASTER.md"
        )
        body = cm_parser.render_card_body(o)
        self.assertEqual(cm_parser.extract_cm_ref(body), "M20")
        self.assertIsNone(cm_parser.extract_cm_ref("no ref here"))


@unittest.skipIf(NO_LEDGER, SKIP_MSG)
class TestRealLedger(unittest.TestCase):
    def test_real_master(self):
        assert REPO is not None
        master = (REPO / "MASTER.md").read_text()
        row_refs = [
            match.group(1)
            for line in master.splitlines()
            if (match := MASTER_DATA_ROW.fullmatch(line))
        ]
        objs = cm_parser.parse_master(master)
        refs = [o.cm_ref for o in objs]
        self.assertEqual(refs, row_refs, "parsed refs differ from MASTER data rows")
        self.assertEqual(len(refs), len(set(refs)), "duplicate cm_refs")
        for o in objs:
            self.assertTrue(o.title, f"{o.cm_ref} has empty title")
            self.assertTrue(o.status, f"{o.cm_ref} has empty status")
        active = {o.cm_ref for o in cm_parser.cardable(objs)}
        expected = {o.cm_ref for o in objs if o.status in cm_parser.CARDABLE}
        self.assertEqual(active, expected)

    def test_real_dailies(self):
        assert REPO is not None
        for f in sorted((REPO / "daily").glob("*.md")):
            objs = cm_parser.parse_daily(f.read_text(), f.stem)
            self.assertTrue(objs, f"no rows parsed from {f.name}")
            for o in objs:
                self.assertTrue(o.cm_ref.startswith(f.stem + "#"))

    def test_real_project_cards(self):
        assert REPO is not None
        cards = sorted((REPO / "projects").glob("*.md"))
        objs = [
            obj
            for card in cards
            for obj in cm_parser.parse_project_next(
                card.read_text(), f"projects/{card.name}"
            )
        ]
        self.assertTrue(objs)
        self.assertTrue(all("#next-" in o.cm_ref for o in objs))


if __name__ == "__main__":
    unittest.main(verbosity=2)
