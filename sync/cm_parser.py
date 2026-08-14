"""Parse work-ledger Markdown into work objects.

Pure functions, no I/O beyond what callers hand in — this module is the tested heart of
intake. Every object carries a stable cm_ref (spec §3: no card without a cm_ref).

  MASTER.md row            -> cm_ref "M20"
  daily/2026-07-19.md row  -> cm_ref "2026-07-19#D4"
  projects/<n>.md Next item-> cm_ref "projects/<n>.md#next-1"
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict

_BOLD = re.compile(r"\*\*(.+?)\*\*")
_MASTER_ROW = re.compile(r"^\|\s*(M\d+)\s*\|(.+)\|(.+)\|(.+)\|(.*)\|\s*$")
_DAILY_ROW = re.compile(r"^\|\s*(D\d+)\s*\|(.+)\|(.+)\|(.+)\|(.*)\|\s*$")
_NEXT_ITEM = re.compile(r"^(\d+)\.\s+(.*\S)\s*$")

# Statuses that mean "this belongs on the board". done/later/superseded stay in git only.
CARDABLE = {"active", "backlog", "needs-decision", "blocked", "awaiting"}


@dataclass
class WorkObject:
    cm_ref: str
    title: str
    owner: str = ""
    status: str = ""
    notes: str = ""
    source: str = ""  # which file this came from

    def to_dict(self) -> dict:
        return asdict(self)


def _clean(cell: str) -> str:
    return _BOLD.sub(r"\1", cell).strip()


def _norm_status(cell: str) -> str:
    s = _clean(cell).lower()
    s = s.replace("✅", "done").replace("⏳", "awaiting").replace("◐", "active")
    # "done → drops to LOG" and friends normalise on the first word-ish token
    for key in ("done", "active", "backlog", "later", "needs-decision", "awaiting"):
        if s.startswith(key):
            return key
    if s.startswith("blocked"):
        return "blocked"
    return s.strip()


def parse_master(text: str) -> list[WorkObject]:
    out = []
    for line in text.splitlines():
        m = _MASTER_ROW.match(line)
        if not m:
            continue
        mid, item, owner, status, notes = m.groups()
        out.append(
            WorkObject(
                cm_ref=mid,
                title=_clean(item),
                owner=_clean(owner),
                status=_norm_status(status),
                notes=_clean(notes),
                source="MASTER.md",
            )
        )
    return out


def parse_daily(text: str, date: str) -> list[WorkObject]:
    out = []
    for line in text.splitlines():
        m = _DAILY_ROW.match(line)
        if not m:
            continue
        did, item, ties, owner, status = m.groups()
        # daily tables are | id | Item | Ties | Owner | Status |
        title = _clean(item)
        if title.lower() in ("item", "---", ""):
            continue
        out.append(
            WorkObject(
                cm_ref=f"{date}#{did}",
                title=title,
                owner=_clean(owner),
                status=_norm_status(status),
                notes=(
                    f"ties: {_clean(ties)}"
                    if _clean(ties) not in ("", "—", "-")
                    else ""
                ),
                source=f"daily/{date}.md",
            )
        )
    return out


def parse_project_next(text: str, path: str) -> list[WorkObject]:
    """Ordered items under '## Next'. Item 1 is THE next action (projects/README schema)."""
    out = []
    in_next = False
    for line in text.splitlines():
        if line.startswith("## "):
            in_next = line.lower().startswith("## next")
            continue
        if not in_next:
            continue
        m = _NEXT_ITEM.match(line.strip())
        if not m:
            continue
        n, body = m.groups()
        title = _clean(body)
        if title.startswith("~~"):  # struck-through = done in place
            continue
        out.append(
            WorkObject(
                cm_ref=f"{path}#next-{n}",
                title=title,
                owner="",
                status="backlog",
                source=path,
            )
        )
    return out


def cardable(objs: list[WorkObject]) -> list[WorkObject]:
    return [o for o in objs if o.status in CARDABLE]


def render_card_body(obj: WorkObject) -> str:
    """The kanban task body. First line is the machine-readable linkage key (spec §3)."""
    lines = [f"cm_ref: {obj.cm_ref}", f"source: {obj.source}"]
    if obj.owner:
        lines.append(f"owner: {obj.owner}")
    if obj.notes:
        lines.append(f"notes: {obj.notes}")
    return "\n".join(lines)


def extract_cm_ref(body: str) -> str | None:
    for line in (body or "").splitlines():
        if line.startswith("cm_ref:"):
            return line.split(":", 1)[1].strip()
    return None
