#!/usr/bin/env python3
"""board → git (spec §7): the receipts leg.

Two callers, one job — get the truth back into the work ledger:
  done_render.py                          hourly snapshot (timer)
  done_render.py "AGENT DONE M20 — …"     terminal event (sys-done), receipt = commit message

Stages the WHOLE checkout, not just the snapshot: sys-done edits LOG.md, MASTER.md, the
project card and the daily before calling us, and a receipt commit that dropped those
edits would be a lie in the permanent record.
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


def render(
    tasks: list[dict],
    now: str | None = None,
    board_order: list[str] | tuple[str, ...] | None = None,
) -> str:
    now = now or datetime.datetime.now(datetime.timezone.utc).strftime(
        "%Y-%m-%d %H:%M UTC"
    )
    lines = [
        "# board-state — live Kanban Surface projection",
        "",
        f"_Machine-rendered {now} by kanban-surface/sync/done_render.py — do not hand-edit._",
        "_In-flight state lives on the board; this file exists so a KS outage loses nothing._",
        "",
    ]
    by_board: dict[str, list[dict]] = {}
    for t in tasks:
        by_board.setdefault(t.get("assignee") or "unassigned", []).append(t)

    board_order = board_order or ksconfig.BOARDS
    ordered = [b for b in board_order if b in by_board]
    ordered += [b for b in sorted(by_board) if b not in board_order]
    if not ordered:
        lines.append("_Board empty._")
    for b in ordered:
        lines.append(f"## {b}  ({len(by_board[b])})")
        lines.append("")
        lines.append("| id | status | cm_ref | title |")
        lines.append("|----|--------|--------|-------|")
        for t in sorted(by_board[b], key=lambda x: str(x.get("id", ""))):
            ref = cm_parser.extract_cm_ref(t.get("body", "")) or "—"
            title = str(t.get("title", "")).replace("|", "\\|")[:80]
            lines.append(
                f"| {t.get('id','?')} | {t.get('status','?')} | {ref} | {title} |"
            )
        lines.append("")
    return "\n".join(lines)


def publish(
    cfg: dict, brd: board_mod.Board, receipt: str = "", push: bool = True
) -> dict:
    repo = pathlib.Path(cfg["repo_dir"])
    retries = tuple(cfg.get("sync", {}).get("push_retries") or gitops.DEFAULT_RETRIES)
    tasks = brd.list_tasks()

    out = repo / cfg["sync"]["snapshot_path"]
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(tasks, board_order=cfg.get("boards")))

    msg = f"[ks] {receipt}" if receipt else "[ks] SNAPSHOT board-state"
    # A terminal event is always recorded, even if the rendered board is byte-identical —
    # the receipt itself is the point. A bare snapshot with no changes commits nothing.
    committed = gitops.commit_all(str(repo), msg, allow_empty=bool(receipt))
    pushed = (
        gitops.push(str(repo), cfg["repo_branch"], retries)
        if (committed and push)
        else False
    )
    if committed and push and not pushed:
        print(
            f"done_render: WARNING commit '{msg}' is local — push failed, will retry next run",
            file=sys.stderr,
        )
    return {
        "tasks": len(tasks),
        "message": msg,
        "committed": committed,
        "pushed": pushed,
    }


def main() -> int:
    cfg = ksconfig.load()
    receipt = sys.argv[1] if len(sys.argv) > 1 else ""
    r = publish(cfg, board_mod.get_board(cfg), receipt)
    print(
        f"done_render: {r['tasks']} tasks · "
        f"{'committed' if r['committed'] else 'no change'} · "
        f"{'pushed' if r['pushed'] else 'not pushed'} · {r['message']}"
    )
    # A stranded commit is not a failure of this run — the work and its receipt are safe
    # in local history and the next run pushes them. Only a lost receipt would be fatal.
    return 0


if __name__ == "__main__":
    sys.exit(main())
