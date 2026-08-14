"""Git operations against the work-ledger checkout.

Git is the source of truth and commits are the receipts (spec §1), so the rule here is
absolute: **never destroy a local commit.** An earlier version of the intake leg ran
`git reset --hard origin/<branch>`, which would silently delete any receipt commit whose
push had failed — losing the record of work that really happened. Everything below is
built so the worst case is "we stop and shout", never "we quietly drop a receipt".
"""

from __future__ import annotations

import subprocess
import time


DEFAULT_RETRIES = (0, 2, 4, 8, 16)


class GitError(RuntimeError):
    pass


def _git(repo: str, *args: str, check: bool = True, timeout: int = 120):
    proc = subprocess.run(
        ["git", "-C", repo, *args], capture_output=True, text=True, timeout=timeout
    )
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc


def unpushed(repo: str, branch: str) -> int:
    """How many local commits are not on the remote (i.e. receipts at risk)."""
    out = _git(repo, "rev-list", "--count", f"origin/{branch}..HEAD").stdout.strip()
    return int(out or 0)


def push(repo: str, branch: str, retries: tuple[int, ...] | None = None) -> bool:
    """Push with backoff. Returns success; never raises on network failure — the caller
    decides what to do, and the commit stays safely local either way."""
    for wait in retries or DEFAULT_RETRIES:
        if wait:
            time.sleep(wait)
        if (
            _git(
                repo, "push", "-u", "origin", branch, check=False, timeout=180
            ).returncode
            == 0
        ):
            return True
    return False


def sync(repo: str, branch: str, retries: tuple[int, ...] | None = None) -> None:
    """Bring the checkout up to date with the remote WITHOUT discarding local work.

    Order matters: push anything local first (those are receipts), then fast-forward.
    If the histories have genuinely diverged we rebase local work on top; if that can't
    be done cleanly we abort the rebase and raise, leaving the checkout exactly as it was.
    """
    _git(repo, "fetch", "origin", branch, timeout=180)

    current = _git(repo, "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
    if current != branch:
        _git(repo, "checkout", branch)

    ahead = unpushed(repo, branch)
    if ahead and not push(repo, branch, retries or DEFAULT_RETRIES):
        # Receipts are stranded locally. Do NOT reset — carry on with them intact and let
        # the next run try again; a stale board beats a lost receipt.
        raise GitError(
            f"{ahead} unpushed commit(s) and push failed — refusing to touch local history"
        )

    ff = _git(repo, "merge", "--ff-only", f"origin/{branch}", check=False)
    if ff.returncode == 0:
        return

    rebase = _git(repo, "rebase", f"origin/{branch}", check=False)
    if rebase.returncode != 0:
        _git(repo, "rebase", "--abort", check=False)
        raise GitError(
            f"diverged from origin/{branch} and rebase conflicted — human needed. "
            f"Checkout left untouched."
        )


def commit_all(repo: str, message: str, allow_empty: bool = False) -> bool:
    """Stage EVERYTHING in the checkout and commit.

    Deliberately `add -A`: the done-worker edits LOG.md, MASTER.md, project cards and the
    daily before calling us. Staging only the snapshot file (as an earlier version did)
    committed a receipt whose actual ledger update was silently dropped. The ledger is
    Markdown-only, so there is nothing here that should not be committed.
    """
    _git(repo, "add", "-A")
    staged_empty = (
        _git(repo, "diff", "--cached", "--quiet", check=False).returncode == 0
    )
    if staged_empty and not allow_empty:
        return False
    args = ["commit", "-m", message] + (["--allow-empty"] if staged_empty else [])
    _git(repo, *args)
    return True
