#!/usr/bin/env python3
"""End-to-end: a REAL git repo with a REAL remote, driven through the whole pipeline.

This is the test the architecture was refactored to make possible. It exercises
git → intake → dispatch → receipts → git against a MemoryBoard and a throwaway bare
remote, with no Hermes install anywhere. Both data-loss bugs found in review are
regression-tested here by name.

    python3 tests/test_integration.py
"""

from __future__ import annotations

import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parent.parent
for sub in ("sync", "gateway", "triggers"):
    sys.path.insert(0, str(ROOT / sub))

import board as board_mod  # noqa: E402
import done_render  # noqa: E402
import gitops  # noqa: E402
import intake_sync  # noqa: E402
import receipts as R  # noqa: E402
import ksconfig  # noqa: E402
from gateway import Gateway  # noqa: E402
from watcher import Watcher  # noqa: E402

MASTER = """# MASTER — the backlog

| id | Item | Owner | Status | Notes |
|----|------|-------|--------|-------|
| M1 | **Ship the thing** — a real work item | builder | active | notes here |
| M2 | **Old finished item** | builder | done | dropped to LOG |
| M3 | **Someday item** | owner | later | not now |
"""

LOG = "# LOG — what's been done (newest on top)\n"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    )


class Pipeline(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)

        # A real remote, so push/fetch are genuinely exercised.
        self.remote = base / "remote.git"
        subprocess.run(["git", "init", "--bare", "-q", str(self.remote)], check=True)

        self.repo = base / "work-ledger"
        subprocess.run(
            ["git", "clone", "-q", str(self.remote), str(self.repo)], check=True
        )
        git(self.repo, "config", "user.email", "ks@test")
        git(self.repo, "config", "user.name", "ks-test")
        (self.repo / "MASTER.md").write_text(MASTER)
        (self.repo / "LOG.md").write_text(LOG)
        (self.repo / "projects").mkdir()
        (self.repo / "projects" / "ship.md").write_text(
            "# Ship — the product\n\n## What\n\nCanonical detail.\n"
        )
        git(self.repo, "add", "-A")
        git(self.repo, "commit", "-qm", "seed")
        git(self.repo, "branch", "-M", "main")
        git(self.repo, "push", "-qu", "origin", "main")

        self.cfg = {
            "repo_dir": str(self.repo),
            "repo_branch": "main",
            "boards": list(ksconfig.BOARDS),
            "gateway": {
                "bind": "127.0.0.1",
                "port": 0,
                "audit_log": str(base / "audit.jsonl"),
                "tokens": {
                    "tok-owner": {
                        "agent": "owner",
                        "create": True,
                        "comment": True,
                        "archive": True,
                        "move_to": list(ksconfig.BOARDS),
                    },
                    "tok-contributor": {
                        "agent": "contributor",
                        "create": True,
                        "comment": True,
                        "archive": False,
                        "move_to": ["sys-intake", "work-engineering"],
                    },
                },
            },
            "triggers": {
                "human_telegram_chat_id": "123",
                "reject_limit": 2,
                "watch_interval_secs": 15,
            },
            "sync": {
                "intake_interval_secs": 600,
                "snapshot_path": "docs/board-state.md",
                "push_retries": [0],
            },
        }
        self.board = board_mod.MemoryBoard(base / "board.json")

    def tearDown(self):
        self.tmp.cleanup()

    def log_messages(self):
        return git(self.repo, "log", "--format=%s").stdout.splitlines()

    # ---------------------------------------------------------------- the happy path

    def test_full_round_trip(self):
        """git → card → build → done → receipt commit back in git."""
        result = intake_sync.sync(self.cfg, self.board)
        self.assertEqual(
            result["created"], ["M1"], "only the active item should be carded"
        )
        self.assertEqual(
            result["cardable"], 1, "done/later items must not reach the board"
        )

        card = self.board.list_tasks()[0]
        self.assertEqual(card["assignee"], "sys-intake")
        self.assertIn("cm_ref: M1", card["body"])

        # intake routes it; build works it and declares no external mutation.
        self.board.move_to_board(card["id"], "work-engineering", actor="sys-intake")
        self.board.comment(card["id"], R.CLAIMED, author="work-engineering")
        self.board.comment(
            card["id"], f"{R.DONE}\n{R.MUTATED_KEY}: false", author="work-engineering"
        )
        self.assertIs(
            R.declares_mutation(self.board.comments_of(self.board.show(card["id"]))),
            False,
        )
        self.board.move_to_board(card["id"], "sys-done", actor="work-engineering")

        # sys-done writes the ledger, then publishes. THIS is the regression that matters:
        # the ledger edit must ride along in the receipt commit.
        (self.repo / "LOG.md").write_text(LOG + "- did the thing (M1)\n")
        r = done_render.publish(self.cfg, self.board, f"{R.DONE} M1 — did the thing")
        self.assertTrue(r["committed"] and r["pushed"])

        self.assertIn("[ks] AGENT DONE M1 — did the thing", self.log_messages()[0])
        committed = git(self.repo, "show", "--stat", "--format=", "HEAD").stdout
        self.assertIn(
            "LOG.md",
            committed,
            "REGRESSION: ledger edit dropped from the receipt commit",
        )
        self.assertIn("board-state.md", committed)

        snapshot = (self.repo / "docs" / "board-state.md").read_text()
        self.assertIn("sys-done", snapshot)
        self.assertIn("M1", snapshot)

    # ------------------------------------------------------------------ the WIP limit

    def test_intake_admits_only_up_to_the_wip_limit(self):
        """A first sync against the real ledger cards ~28 items. Promoting them all would
        spawn 28 worker runs at once, so admission is capped — the rest wait as backlog.
        """
        cfg = {**self.cfg, "sync": {**self.cfg["sync"], "wip_limit": 3}}
        for i in range(8):
            self.board.create(f"backlog {i}", f"cm_ref: B{i}", "sys-intake", f"wip{i}")

        admitted = intake_sync.admit(cfg, self.board)
        self.assertEqual(len(admitted), 3, "admission must stop at the limit")
        in_play = [t for t in self.board.list_tasks() if t["status"] == board_mod.READY]
        self.assertEqual(len(in_play), 3)
        self.assertEqual(
            len(
                [t for t in self.board.list_tasks() if t["status"] == board_mod.BACKLOG]
            ),
            5,
            "rest stay as backlog",
        )

        # No capacity freed ⇒ a later run admits nothing new.
        self.assertEqual(intake_sync.admit(cfg, self.board), [])

        # Finish one; the next run lets exactly one more in.
        self.board.archive(admitted[0])
        self.assertEqual(len(intake_sync.admit(cfg, self.board)), 1)

    def test_admission_leaves_a_receipt(self):
        cfg = {**self.cfg, "sync": {**self.cfg["sync"], "wip_limit": 1}}
        card = self.board.create("one thing", "cm_ref: B1", "sys-intake", "w1")
        intake_sync.admit(cfg, self.board)
        comments = self.board.comments_of(self.board.show(card["id"]))
        self.assertTrue(
            any(R.KSM_ADMITTED in c and "1/1" in c for c in comments),
            f"expected an admission receipt, got {comments}",
        )

    def test_wip_limit_off_admits_nothing_automatically(self):
        """Without a configured limit the automatic path stays inert — explicit is better
        than a surprise flood."""
        self.board.create("thing", "cm_ref: B1", "sys-intake", "w1")
        cfg = {**self.cfg, "sync": {**self.cfg["sync"], "wip_limit": None}}
        self.assertEqual(intake_sync.admit(cfg, self.board), [])

    def test_intake_is_idempotent(self):
        first = intake_sync.sync(self.cfg, self.board)
        second = intake_sync.sync(self.cfg, self.board)
        self.assertEqual(first["created"], ["M1"])
        self.assertEqual(second["created"], [], "re-run must not duplicate cards")
        self.assertEqual(second["existing"], ["M1"])
        self.assertEqual(len(self.board.list_tasks(archived=True)), 1)

    # ------------------------------------------------------- the two data-loss bugs

    def test_intake_never_destroys_an_unpushed_receipt(self):
        """REGRESSION: intake used to `git reset --hard origin/<branch>`, which would
        silently delete a receipt commit whose push had failed."""
        (self.repo / "LOG.md").write_text(
            LOG + "- receipt that has not reached origin\n"
        )
        gitops.commit_all(str(self.repo), "[ks] AGENT DONE M1 — stranded receipt")
        self.assertEqual(gitops.unpushed(str(self.repo), "main"), 1)

        intake_sync.sync(self.cfg, self.board)  # pulls; must not eat the commit

        self.assertIn(
            "[ks] AGENT DONE M1 — stranded receipt",
            self.log_messages(),
            "REGRESSION: unpushed receipt commit was destroyed by intake sync",
        )
        self.assertEqual(
            gitops.unpushed(str(self.repo), "main"),
            0,
            "a reachable remote means the stranded receipt should now be pushed",
        )

    def test_sync_refuses_rather_than_discarding_when_push_fails(self):
        """With the remote gone, a stranded receipt must survive and the run must fail
        loudly instead of resetting local history away."""
        (self.repo / "LOG.md").write_text(LOG + "- unpushable receipt\n")
        gitops.commit_all(str(self.repo), "[ks] AGENT DONE M1 — unpushable")
        git(
            self.repo, "remote", "set-url", "origin", str(self.repo.parent / "gone.git")
        )

        with self.assertRaises(gitops.GitError):
            gitops.sync(str(self.repo), "main")
        self.assertIn(
            "[ks] AGENT DONE M1 — unpushable",
            self.log_messages(),
            "receipt must survive a failed sync",
        )

    def test_publish_keeps_receipt_local_when_push_fails(self):
        git(
            self.repo, "remote", "set-url", "origin", str(self.repo.parent / "gone.git")
        )
        (self.repo / "LOG.md").write_text(LOG + "- offline work\n")
        r = done_render.publish(self.cfg, self.board, f"{R.DONE} M1 — offline")
        self.assertTrue(
            r["committed"], "must commit even when the remote is unreachable"
        )
        self.assertFalse(r["pushed"])
        self.assertIn("[ks] AGENT DONE M1 — offline", self.log_messages()[0])

    # ------------------------------------------------------------------- the gateway

    def test_gateway_permissions_and_audit(self):
        gw = Gateway(self.cfg, self.board)
        owner = self.cfg["gateway"]["tokens"]["tok-owner"]
        contributor = self.cfg["gateway"]["tokens"]["tok-contributor"]

        code, task = gw.create(
            contributor, {"title": "contributor's card", "body": "cm_ref: X1"}
        )
        self.assertEqual(code, 201)
        self.assertEqual(
            task["assignee"], "sys-intake", "creates always land on intake"
        )

        code, err = gw.move(contributor, task["id"], {"board": "sys-audit"})
        self.assertEqual(code, 403)
        self.assertIn("may not move to sys-audit", err["error"])

        self.assertEqual(
            gw.move(contributor, task["id"], {"board": "work-engineering"})[0], 200
        )
        self.assertEqual(gw.move(owner, task["id"], {"board": "sys-audit"})[0], 200)
        self.assertEqual(gw.archive(contributor, task["id"], {})[0], 403)
        self.assertEqual(gw.move(owner, task["id"], {"board": "nonsense"})[0], 400)

        audit = [
            json.loads(x)
            for x in pathlib.Path(self.cfg["gateway"]["audit_log"])
            .read_text()
            .splitlines()
        ]
        denied = [a for a in audit if not a["allowed"]]
        self.assertEqual(len(denied), 3, "every refusal is on the record")
        self.assertTrue(
            all(a["agent"] for a in audit), "every entry names the requester"
        )

    def test_gateway_create_titles_may_repeat(self):
        """REGRESSION: keying creates on the title meant a repeated title silently
        returned someone else's card instead of creating a new one."""
        gw = Gateway(self.cfg, self.board)
        owner = self.cfg["gateway"]["tokens"]["tok-owner"]
        a = gw.create(owner, {"title": "daily standup notes"})[1]
        b = gw.create(owner, {"title": "daily standup notes"})[1]
        self.assertNotEqual(a["id"], b["id"])

    def test_gateway_create_is_retry_safe_with_a_client_key(self):
        """A client that can't tell a timeout from a failure supplies its own key and
        retries safely; the second call returns the same card instead of a duplicate."""
        gw = Gateway(self.cfg, self.board)
        owner = self.cfg["gateway"]["tokens"]["tok-owner"]
        first = gw.create(
            owner, {"title": "flaky network", "idempotency_key": "req-42"}
        )[1]
        again = gw.create(
            owner, {"title": "flaky network", "idempotency_key": "req-42"}
        )[1]
        self.assertEqual(first["id"], again["id"])
        # Keys are namespaced per agent — one party can't collide with (or read) another's.
        contributor = self.cfg["gateway"]["tokens"]["tok-contributor"]
        other = gw.create(
            contributor, {"title": "different work", "idempotency_key": "req-42"}
        )[1]
        self.assertNotEqual(first["id"], other["id"])

    def test_gateway_reads_only_the_source_linked_by_the_card(self):
        gw = Gateway(self.cfg, self.board)
        owner = self.cfg["gateway"]["tokens"]["tok-owner"]
        linked = self.board.create(
            "project work",
            "cm_ref: projects/ship.md#next-1\nsource: projects/ship.md",
            "sys-intake",
            "source-1",
        )
        code, source = gw.source(owner, linked["id"])
        self.assertEqual(code, 200)
        self.assertEqual(source["path"], "projects/ship.md")
        self.assertIn("Canonical detail.", source["markdown"])

        unlinked = self.board.create(
            "bad source",
            "cm_ref: X\nsource: ../../etc/passwd",
            "sys-intake",
            "source-2",
        )
        self.assertEqual(gw.source(owner, unlinked["id"])[0], 404)

    # ------------------------------------------------------------------- the watcher

    def test_watcher_pings_needs_input_once(self):
        w = Watcher(self.cfg, self.board)
        card = self.board.create("needs a human", "cm_ref: M1", "sys-input", "k1")
        self.board.promote(card["id"])
        self.assertIn("notified", w.tick()[card["id"]])
        self.assertEqual(len(self.board._state["notifications"]), 1)
        w.tick()  # a second pass must not re-ping
        self.assertEqual(len(self.board._state["notifications"]), 1)

    def test_watcher_breaks_the_reject_loop(self):
        w = Watcher(self.cfg, self.board)
        card = self.board.create(
            "contested work", "cm_ref: M1", "work-engineering", "k2"
        )
        self.board.promote(card["id"])
        self.board.comment(
            card["id"], f"{R.REJECTED} — findings: 1. wrong", author="sys-audit"
        )
        self.assertNotIn("loop-break", w.tick().get(card["id"], []))

        self.board.comment(
            card["id"], f"{R.REJECTED} — findings: 1. still wrong", author="sys-audit"
        )
        self.assertIn("loop-break", w.tick()[card["id"]])
        self.assertEqual(self.board.show(card["id"])["assignee"], "sys-input")

    def test_watcher_freezes_failures(self):
        w = Watcher(self.cfg, self.board)
        card = self.board.create("doomed work", "cm_ref: M1", "work-engineering", "k3")
        self.board.promote(card["id"])
        self.board.comment(
            card["id"],
            f"{R.FAILED} — last safe step: none; retries: 2",
            author="work-engineering",
        )
        self.assertIn("frozen", w.tick()[card["id"]])
        self.assertEqual(self.board.show(card["id"])["status"], board_mod.BLOCKED)
        w.tick()
        frozen = [
            c
            for c in self.board.comments_of(self.board.show(card["id"]))
            if R.KSM_FROZEN in c
        ]
        self.assertEqual(len(frozen), 2, "block reason + marker, and never re-frozen")

    def test_watcher_reconciles_a_half_completed_move(self):
        """assign+promote is not atomic; a card whose move landed but never promoted must
        get finished rather than stalling forever."""
        w = Watcher(self.cfg, self.board)
        card = self.board.create("half moved", "cm_ref: M1", "work-engineering", "k4")
        self.board.comment(
            card["id"], "MOVED to work-engineering by owner", author="owner"
        )
        self.assertEqual(self.board.show(card["id"])["status"], board_mod.BACKLOG)
        self.assertIn("reconciled", w.tick()[card["id"]])
        self.assertEqual(self.board.show(card["id"])["status"], board_mod.READY)

    def test_watcher_leaves_freshly_carded_backlog_alone(self):
        """REGRESSION: reconcile used to promote ANY assigned card sitting in todo, which
        on a first sync would have dispatched the entire backlog at once."""
        w = Watcher(self.cfg, self.board)
        for i in range(6):
            self.board.create(
                f"backlog item {i}", f"cm_ref: M{i}", "sys-intake", f"b{i}"
            )
        w.tick()
        statuses = {t["status"] for t in self.board.list_tasks()}
        self.assertEqual(
            statuses,
            {board_mod.BACKLOG},
            "freshly carded backlog must stay inert until WIP allows it",
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)
