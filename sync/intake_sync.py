#!/usr/bin/env python3
"""git → board (spec §7). Timer-driven on the KSM box, or fired by a GitHub push webhook.

Syncs the work-ledger checkout (never destructively — see gitops.sync), parses MASTER +
today's daily + project cards, and upserts one card per cardable object. Git wins at
intake. New cards land on sys-intake; its worker routes them onward.
"""

from __future__ import annotations

import datetime
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import board as board_mod
import cm_parser
import gitops
import ksconfig
import receipts as R


def collect(repo: pathlib.Path, today: str | None = None) -> list[cm_parser.WorkObject]:
    today = today or datetime.date.today().isoformat()
    objs: list[cm_parser.WorkObject] = []
    master = repo / "MASTER.md"
    if master.exists():
        objs += cm_parser.parse_master(master.read_text())
    daily = repo / "daily" / f"{today}.md"
    if daily.exists():
        objs += cm_parser.parse_daily(daily.read_text(), today)
    projects = repo / "projects"
    if projects.is_dir():
        for card in sorted(projects.glob("*.md")):
            if card.name == "README.md":
                continue
            objs += cm_parser.parse_project_next(
                card.read_text(), f"projects/{card.name}"
            )
    return objs


def key_for(cm_ref: str) -> str:
    """One stable idempotency key per ledger object — the board dedupes on this, so a
    re-run (or two timers racing) can never produce a second card for the same work."""
    return f"cm:{cm_ref}"


def admit(cfg: dict, brd: board_mod.Board) -> list[str]:
    """Let work into the pipeline, but only up to the WIP limit.

    Cards are created inert (`blocked`) so the sync timer never dispatches the whole backlog —
    a first run against the real ledger cards ~28 items, and promoting them all would spawn
    28 worker runs at once. Instead we admit oldest-first while there is capacity, which
    encodes the configured WIP policy in machinery rather than trusting every worker to
    remember it.

    A human owner dragging a card in the UI bypasses this deliberately — a human override
    may exceed the limit; the automatic path is what needs the brake.
    """
    limit = cfg.get("sync", {}).get("wip_limit")
    if not limit:
        return []
    tasks = brd.list_tasks()
    in_play = [
        t for t in tasks if t.get("status") in (board_mod.READY, board_mod.RUNNING)
    ]
    capacity = limit - len(in_play)
    if capacity <= 0:
        return []

    waiting = [
        t
        for t in tasks
        if t.get("status") == board_mod.BACKLOG and t.get("assignee") == "sys-intake"
    ]
    waiting.sort(key=lambda t: (t.get("updated") or 0, str(t.get("id"))))

    admitted = []
    for task in waiting[:capacity]:
        brd.promote(task["id"])
        brd.comment(
            task["id"],
            f"{R.KSM_ADMITTED} to the pipeline "
            f"(WIP {len(in_play) + len(admitted) + 1}/{limit})",
            author="ksm-intake",
        )
        admitted.append(task["id"])
    return admitted


def sync(cfg: dict, brd: board_mod.Board, pull: bool = True) -> dict:
    repo = pathlib.Path(cfg["repo_dir"])
    if pull:
        gitops.sync(
            str(repo),
            cfg["repo_branch"],
            tuple(cfg.get("sync", {}).get("push_retries") or gitops.DEFAULT_RETRIES),
        )

    objs = cm_parser.cardable(collect(repo))
    known = {
        t["id"] for t in brd.list_tasks(archived=True)
    }  # one listing, not one per object
    created, existing = [], []
    for obj in objs:
        task = brd.create(
            title=obj.title[:120],
            body=cm_parser.render_card_body(obj),
            assignee="sys-intake",
            idempotency_key=key_for(obj.cm_ref),
        )
        # The board returns the pre-existing card when the key is known; an id we hadn't
        # seen means it was genuinely new. This needs no card bodies in the list output.
        if task.get("id") in known:
            existing.append(obj.cm_ref)
        else:
            created.append(obj.cm_ref)
            known.add(task.get("id"))
    admitted = admit(cfg, brd)
    return {
        "cardable": len(objs),
        "created": created,
        "existing": existing,
        "admitted": admitted,
    }


def main() -> int:
    cfg = ksconfig.load()
    result = sync(cfg, board_mod.get_board(cfg))
    print(
        f"intake_sync: {result['cardable']} cardable · "
        f"{len(result['created'])} created {result['created']} · "
        f"{len(result['existing'])} already carded · "
        f"{len(result['admitted'])} admitted to the pipeline {result['admitted']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
