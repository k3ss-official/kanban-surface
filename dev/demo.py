#!/usr/bin/env python3
"""Run the whole Kanban Surface locally — no Hermes, no VPS, no config.

    python3 dev/demo.py                      # seeded sample board
    python3 dev/demo.py --repo ~/work-ledger # cards parsed from a compatible ledger

Starts the permission gateway on an in-memory board and prints a URL to open. The point
is that the visual and permission design can be evaluated NOW, before anyone picks a host:
drag a card and watch the move land, hit a refusal with a narrow token, read the receipts.

Nothing here touches a real board, a real Hermes, or the source ledger (the ledger,
if given, is only READ to seed cards).
"""

from __future__ import annotations

import argparse
import json
import pathlib
import sys
import tempfile
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer

ROOT = pathlib.Path(__file__).parent.parent
for sub in ("sync", "gateway"):
    sys.path.insert(0, str(ROOT / sub))

import board as board_mod  # noqa: E402
import cm_parser  # noqa: E402
import intake_sync  # noqa: E402
import receipts as R  # noqa: E402
from gateway import Gateway, make_handler  # noqa: E402

TOKENS = {
    "demo-owner": {
        "agent": "owner",
        "create": True,
        "comment": True,
        "archive": True,
        "move_to": [
            "sys-intake",
            "work-research",
            "work-knowledge",
            "work-engineering",
            "work-infra",
            "work-writer",
            "sys-input",
            "sys-audit",
            "sys-done",
        ],
    },
    "demo-orchestrator": {
        "agent": "orchestrator",
        "create": True,
        "comment": True,
        "archive": False,
        "move_to": [
            "sys-intake",
            "work-research",
            "work-knowledge",
            "work-engineering",
            "work-infra",
            "work-writer",
            "sys-audit",
        ],
    },
    "demo-contributor": {
        "agent": "contributor",
        "create": True,
        "comment": True,
        "archive": False,
        "move_to": ["sys-intake", "work-research", "work-engineering", "work-writer"],
    },
}

SAMPLE = [
    ("sys-intake", "M12", "Prepare the first customer pilot", [], "ready"),
    (
        "work-research",
        "M21",
        "Survey current local-agent deployment patterns",
        [],
        "ready",
    ),
    (
        "work-knowledge",
        "M22",
        "Validate sources before notebook admission",
        [],
        "ready",
    ),
    (
        "work-engineering",
        "M18",
        "Implement the document ingestion adapter",
        [(R.CLAIMED, "work-engineering")],
        "running",
    ),
    ("work-infra", "M23", "Verify loopback-only ingress", [], "ready"),
    ("work-writer", "M24", "Draft launch note from verified evidence", [], "ready"),
    (
        "sys-input",
        "M19",
        "Choose the deployment target",
        [
            (
                f"{R.HUMAN_HOLD} which approved environment should host the service?",
                "work-engineering",
            ),
            (f"{R.KSM_NOTIFIED} owner/telegram", "ksm-watcher"),
        ],
        "blocked",
    ),
    (
        "sys-audit",
        "M10",
        "Repository hygiene — archive stale repositories",
        [
            (R.CLAIMED, "work-engineering"),
            (
                f"{R.DONE}\n{R.MUTATED_KEY}: true — archived approved repositories via the API",
                "work-engineering",
            ),
        ],
        "ready",
    ),
    (
        "sys-done",
        "M20",
        "Kanban Surface — spec + implementation",
        [
            (R.CLAIMED, "work-engineering"),
            (f"{R.DONE}\n{R.MUTATED_KEY}: true", "work-engineering"),
            (f"{R.VERIFIED} commit b513a49 present on main", "sys-audit"),
        ],
        "done",
    ),
]


def seed_sample(brd: board_mod.Board) -> int:
    for assignee, ref, title, comments, status in SAMPLE:
        task = brd.create(
            title=title,
            body=f"cm_ref: {ref}\nsource: MASTER.md",
            assignee=assignee,
            idempotency_key=f"demo:{ref}",
        )
        brd.promote(task["id"])
        for body, author in comments:
            brd.comment(task["id"], body, author=author)
        if status == "blocked":
            brd.block(task["id"], "waiting on a human answer")
    return len(SAMPLE)


def seed_from_ledger(
    brd: board_mod.Board, repo: pathlib.Path, cfg: dict
) -> tuple[int, int]:
    """Card the real ledger, then admit under the WIP limit — so the demo shows the actual
    behaviour: a big backlog held on Intake with only a few cards actually in play."""
    objs = cm_parser.cardable(intake_sync.collect(repo))
    for obj in objs:
        brd.create(
            title=obj.title[:120],
            body=cm_parser.render_card_body(obj),
            assignee="sys-intake",
            idempotency_key=intake_sync.key_for(obj.cm_ref),
        )
    return len(objs), len(intake_sync.admit(cfg, brd))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--repo",
        help="a compatible work-ledger checkout to seed cards from (read-only)",
    )
    ap.add_argument("--port", type=int, default=8742)
    ap.add_argument("--no-browser", action="store_true")
    args = ap.parse_args()

    tmp = tempfile.mkdtemp(prefix="ks-demo-")
    cfg = {
        "repo_dir": args.repo or tmp,
        "repo_branch": "main",
        "boards": [
            "sys-intake",
            "work-research",
            "work-knowledge",
            "work-engineering",
            "work-infra",
            "work-writer",
            "sys-input",
            "sys-audit",
            "sys-done",
        ],
        "board": {"backend": "memory", "path": f"{tmp}/board.json"},
        "gateway": {
            "bind": "127.0.0.1",
            "port": args.port,
            "audit_log": f"{tmp}/audit.jsonl",
            "tokens": TOKENS,
        },
        "triggers": {
            "human_telegram_chat_id": None,
            "reject_limit": 2,
            "watch_interval_secs": 15,
        },
        "sync": {
            "snapshot_path": "docs/board-state.md",
            "push_retries": [0],
            "wip_limit": 5,
        },
    }
    brd = board_mod.MemoryBoard(cfg["board"]["path"])

    if args.repo:
        n, admitted = seed_from_ledger(brd, pathlib.Path(args.repo), cfg)
        source = (
            f"{n} cards parsed from {args.repo}\n"
            f"  {admitted} admitted to the pipeline (WIP limit "
            f"{cfg['sync']['wip_limit']}); {n - admitted} held as backlog"
        )
    else:
        n = seed_sample(brd)
        source = f"{n} sample cards across all nine boards"

    srv = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(Gateway(cfg, brd)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    url = f"http://127.0.0.1:{args.port}/"
    print(
        f"""
  Kanban Surface — demo
  ─────────────────────────────────────────────────────────────
  {source}
  Board (in memory):  {cfg['board']['path']}
  Audit log:          {cfg['gateway']['audit_log']}

  Open: {url}

  Paste one of these tokens when the page asks:
    demo-owner          full authority — may move anywhere, archive
    demo-orchestrator   intake · engineering · audit   (no archive)
    demo-contributor    intake · engineering only      (try dragging to Audit — refused)

  Drag a card between columns: that IS the dispatch. Click a card to read
  its receipts. Ctrl-C to stop; nothing is written outside {tmp}.
"""
    )
    if not args.no_browser:
        try:
            webbrowser.open(url)
        except Exception:
            pass
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        print("\n  stopped. Audit trail:")
        audit = pathlib.Path(cfg["gateway"]["audit_log"])
        if audit.exists():
            for line in audit.read_text().splitlines()[-10:]:
                e = json.loads(line)
                mark = "ok " if e["allowed"] else "REFUSED"
                print(
                    f"    {mark} {e['agent']:>10} {e['verb']:<8} {e.get('board', '')}"
                )
    return 0


if __name__ == "__main__":
    sys.exit(main())
