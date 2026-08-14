#!/usr/bin/env python3
"""Trigger handlers (spec §9) — v1: three, plus a reconcile pass. Hardcoded on purpose;
a rules engine is earned by the 4th trigger that doesn't fit this shape, not designed
on day one.

  0. reconcile          card with a MOVED receipt still inert ⇒ promote (heals a
                        half-completed move; freshly carded backlog is left alone)
  1. card on sys-input  ⇒ subscribe the human owner's Telegram (built-in notify bridge)
  2. AGENT REJECTED ×N  ⇒ break a domain⇄audit loop, route to sys-input
  3. AGENT FAILED       ⇒ freeze the card, ping the human owner, never auto-retry

Every action leaves a marker comment, so handlers are idempotent and a restart re-derives
all state from the board itself — the watcher holds no durable state of its own.
"""

from __future__ import annotations

import pathlib
import sys
import time

sys.path.insert(0, str(pathlib.Path(__file__).parent.parent / "sync"))
import board as board_mod  # noqa: E402
import ksconfig  # noqa: E402
import receipts as R  # noqa: E402

ACTOR = "ksm-watcher"


class Watcher:
    def __init__(self, cfg: dict, brd: board_mod.Board):
        self.cfg = cfg
        self.board = brd
        self.trig = cfg["triggers"]
        self.chat_id = self.trig.get("human_telegram_chat_id")
        # task id -> `updated` stamp last inspected. Fetching comments costs a call per
        # card, so only re-inspect cards the board says have changed.
        self._seen: dict[str, object] = {}

    def _ping(self, task_id: str) -> None:
        if self.chat_id:
            self.board.notify_subscribe(task_id, "telegram", str(self.chat_id))

    def reconcile(self, task: dict, comments: list[str]) -> bool:
        """Heal a half-completed move: assign landed, promote did not (the primitive is not
        atomic). The discriminator is the MOVED receipt — a move was genuinely attempted.

        A freshly created card also sits inert with an assignee and must NOT be touched:
        intake deliberately leaves cards inert so the WIP limit, not the sync timer, decides
        what enters the pipeline. Promoting those would dispatch the entire backlog at once.
        """
        if task.get("status") not in (
            board_mod.TODO,
            board_mod.BACKLOG,
        ) or not task.get("assignee"):
            return False
        if not R.present(comments, R.KSM_MOVED):
            return False
        self.board.promote(task["id"])
        self.board.comment(
            task["id"],
            f"{R.KSM_RECONCILED} promoted a half-completed move",
            author=ACTOR,
        )
        return True

    def handle(self, task: dict) -> list[str]:
        """Run every applicable handler for one card. Returns the actions taken."""
        acted = []
        comments = self.board.comments_of(task)
        board = task.get("assignee", "")
        tid = task["id"]

        if self.reconcile(task, comments):
            acted.append("reconciled")

        if board == "sys-input" and not R.present(comments, R.KSM_NOTIFIED):
            self._ping(tid)
            self.board.comment(tid, f"{R.KSM_NOTIFIED} human/telegram", author=ACTOR)
            acted.append("notified")

        rejects = R.count(comments, R.REJECTED)
        if (
            rejects >= self.trig["reject_limit"]
            and board in ksconfig.DOMAIN_BOARDS
            and not R.present(comments, R.KSM_LOOP_BREAK)
        ):
            self.board.comment(
                tid,
                f"{R.KSM_LOOP_BREAK} after {rejects} rejections — human eyes needed",
                author=ACTOR,
            )
            self.board.move_to_board(tid, "sys-input", actor=ACTOR)
            acted.append("loop-break")

        if R.count(comments, R.FAILED) and not R.present(comments, R.KSM_FROZEN):
            self.board.block(
                tid, f"{R.KSM_FROZEN}: {R.FAILED} — no auto-retry, see comments"
            )
            self.board.comment(
                tid, f"{R.KSM_FROZEN} pending human review", author=ACTOR
            )
            self._ping(tid)
            acted.append("frozen")

        return acted

    def tick(self) -> dict[str, list[str]]:
        actions: dict[str, list[str]] = {}
        for task in self.board.list_tasks():
            tid = task.get("id")
            if not tid:
                continue
            stamp = task.get("updated")
            # Unchanged since last inspection, and not mid-move ⇒ nothing to do.
            if (
                stamp is not None
                and self._seen.get(tid) == stamp
                and task.get("status") not in (board_mod.TODO, board_mod.BACKLOG)
            ):
                continue
            acted = self.handle(task)
            if acted:
                actions[tid] = acted
            # Re-read the stamp: our own handlers just bumped it.
            self._seen[tid] = self.board.show(tid).get("updated") if acted else stamp
        return actions


def main() -> int:
    cfg = ksconfig.load()
    w = Watcher(cfg, board_mod.get_board(cfg))
    interval = cfg["triggers"]["watch_interval_secs"]
    print(f"ks watcher: polling every {interval}s", flush=True)
    while True:
        try:
            for tid, acted in w.tick().items():
                print(f"  {tid}: {', '.join(acted)}", flush=True)
        except board_mod.BoardError as e:
            print(f"watcher tick error (will retry): {e}", file=sys.stderr, flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main())
