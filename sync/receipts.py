"""Legacy surface receipt grammar retained for historical comment compatibility.

The current persistent-profile team uses native Hermes Kanban lifecycle tools and does
not emit these prose tokens. The surface watcher may still parse historical cards, and
the parsing contract remains covered by ``tests/test_receipts.py``.
"""

from __future__ import annotations

# --- worker receipts (posted by station profiles) ---
CLAIMED = "AGENT CLAIMED"
DONE = "AGENT DONE"
BLOCKED = "AGENT BLOCKED"
HUMAN_HOLD = "AGENT HUMAN HOLD"
UNBLOCKED = "AGENT UNBLOCKED"
HUMAN_ANSWERED = "AGENT HUMAN ANSWERED"
RESUMED = "AGENT RESUMED"
VERIFIED = "AGENT VERIFIED"
REJECTED = "AGENT REJECTED"
FAILED = "AGENT FAILED"
STATUS = "AGENT STATUS"

ALL = (
    CLAIMED,
    DONE,
    BLOCKED,
    HUMAN_HOLD,
    UNBLOCKED,
    HUMAN_ANSWERED,
    RESUMED,
    VERIFIED,
    REJECTED,
    FAILED,
    STATUS,
)

# --- system markers (posted by KSM's own machinery, never by a station profile) ---
# Each doubles as an idempotency marker: the watcher checks for it before acting again.
KSM_NOTIFIED = "KSM NOTIFY-SUBSCRIBED"
KSM_LOOP_BREAK = "KSM LOOP-BREAK"
KSM_FROZEN = "KSM FROZEN"
KSM_RECONCILED = "KSM RECONCILED"
KSM_ADMITTED = "KSM ADMITTED"  # a card entered the pipeline within the WIP limit
KSM_MOVED = "MOVED to"  # written by move_to_board, carries the actor

SYSTEM = (KSM_NOTIFIED, KSM_LOOP_BREAK, KSM_FROZEN, KSM_RECONCILED, KSM_ADMITTED)

# Every domain station includes this declaration on its AGENT DONE receipt.
MUTATED_KEY = "mutated_external_state"


def find(text: str) -> str | None:
    """The receipt token a comment opens with, if any."""
    stripped = (text or "").strip()
    for token in ALL:
        if stripped.startswith(token):
            return token
    return None


def count(comments: list[str], token: str) -> int:
    return sum(1 for c in comments if (c or "").strip().startswith(token))


def present(comments: list[str], marker: str) -> bool:
    """Has this marker already been posted? (idempotency check for handlers)"""
    return any(marker in (c or "") for c in comments)


def declares_mutation(comments: list[str]) -> bool | None:
    """Read the domain worker's external-state declaration off the newest AGENT DONE receipt.

    Returns True/False as declared, or None if no AGENT DONE carries the key — which is
    itself a protocol violation worth routing to verify rather than trusting.
    """
    for c in reversed(comments or []):
        if (c or "").strip().startswith(DONE) and MUTATED_KEY in c:
            after = c.split(MUTATED_KEY, 1)[1].lstrip(" :\t")
            return after.lower().startswith("true")
    return None
