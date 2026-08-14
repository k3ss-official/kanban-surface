"""The board backend — one interface, two implementations.

Why this exists: everything used to shell out to `hermes kanban` directly, which meant
NOTHING could be exercised without a live Hermes install. Two data-loss bugs survived to
review because of it. The interface below lets the whole pipeline run against an in-process
board, so intake → dispatch → receipts → git is testable anywhere.

  HermesBoard  — production. Drives `hermes kanban <verb> --json`, the plugin's stable
                 machine surface (its REST API uses ephemeral dashboard-session tokens,
                 the wrong shape for services).
  MemoryBoard  — tests + dry runs. JSON-file backed so separate processes (e.g. the gateway
                 under test) share one board.

Task shape (both backends): {id, title, body, assignee, status, comments[], updated}
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import subprocess
import threading
import time

# Board lifecycle statuses (the plugin's own vocabulary; boards are the *assignee*).
READY = "ready"
TODO = "todo"
RUNNING = "running"
BLOCKED = "blocked"
DONE = "done"
ARCHIVED = "archived"
# Hermes v0.19 creates ordinary cards ready-to-run. The only supported inert
# initial state is blocked, so KS uses blocked as its explicit intake backlog.
# Human-blocked work is assigned to sys-input, keeping the meanings distinct.
BACKLOG = BLOCKED


class BoardError(RuntimeError):
    pass


class Board:
    """Interface. Every method is used by at least one of: intake, done, gateway, watcher."""

    def list_tasks(
        self,
        assignee: str | None = None,
        status: str | None = None,
        archived: bool = False,
    ) -> list[dict]:
        raise NotImplementedError

    def show(self, task_id: str) -> dict:
        raise NotImplementedError

    def create(
        self, title: str, body: str, assignee: str, idempotency_key: str
    ) -> dict:
        raise NotImplementedError

    def assign(self, task_id: str, profile: str) -> None:
        raise NotImplementedError

    def promote(self, task_id: str) -> None:
        raise NotImplementedError

    def comment(self, task_id: str, text: str, author: str) -> None:
        raise NotImplementedError

    def block(self, task_id: str, reason: str) -> None:
        raise NotImplementedError

    def archive(self, task_id: str) -> None:
        raise NotImplementedError

    def notify_subscribe(self, task_id: str, platform: str, chat_id: str) -> None:
        raise NotImplementedError

    # --- shared behaviour ---

    def move_to_board(self, task_id: str, board: str, actor: str) -> None:
        """THE dispatch primitive (spec §3): reassign + promote ⇒ that station profile runs.

        Not atomic — the plugin has no cross-verb transaction. Ordered so a partial failure
        is always recoverable and never silently wrong: assign first (card is on the right
        board even if promote fails, and the watcher's reconcile pass promotes stragglers),
        comment last (a MOVED receipt only ever appears for a move that actually landed).
        """
        self.assign(task_id, board)
        self.promote(task_id)
        self.comment(task_id, f"MOVED to {board} by {actor}", author=actor)

    def comments_of(self, task: dict) -> list[str]:
        """Comment bodies for a task, fetching detail only when the summary lacks them."""
        if isinstance(task.get("comments"), list):
            raw = task["comments"]
        else:
            detail = self.show(task["id"])
            raw = detail.get("comments", []) if isinstance(detail, dict) else []
        return [c.get("body", "") if isinstance(c, dict) else str(c) for c in raw]


class HermesBoard(Board):
    """Production backend: the `hermes kanban` CLI."""

    def _run(self, args: list[str], json_out: bool = True):
        cmd = ["hermes", "kanban"] + args + (["--json"] if json_out else [])
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
        if proc.returncode != 0:
            raise BoardError(f"{' '.join(cmd)} failed: {proc.stderr.strip()}")
        if not json_out:
            return proc.stdout
        try:
            return json.loads(proc.stdout)
        except json.JSONDecodeError as e:
            # VERIFY-ON-BOX: confirm every verb we call emits clean JSON under --json.
            raise BoardError(
                f"non-JSON from {' '.join(cmd)}: {proc.stdout[:300]}"
            ) from e

    def list_tasks(self, assignee=None, status=None, archived=False):
        args = ["list"]
        if assignee:
            args += ["--assignee", assignee]
        if status:
            args += ["--status", status]
        if archived:
            args += ["--archived"]
        out = self._run(args)
        tasks = (
            out
            if isinstance(out, list)
            else out.get("tasks", []) if isinstance(out, dict) else []
        )
        for task in tasks:
            if not isinstance(task, dict) or task.get("status") != RUNNING:
                continue
            try:
                detail = self.show(task["id"])
            except BoardError:
                continue
            runs = detail.get("runs") if isinstance(detail, dict) else None
            if not isinstance(runs, list):
                continue
            active = [
                run
                for run in runs
                if isinstance(run, dict)
                and isinstance(run.get("id"), int)
                and not isinstance(run.get("id"), bool)
                and run["id"] > 0
                and run.get("status") == RUNNING
                and run.get("ended_at") is None
            ]
            if active:
                current = max(active, key=lambda run: run["id"])
                task["current_run_id"] = current["id"]
                pid = current.get("worker_pid")
                if isinstance(pid, int) and not isinstance(pid, bool) and pid > 0:
                    task["worker_pid"] = pid
        return tasks

    def show(self, task_id):
        detail = self._run(["show", task_id])
        # Hermes v0.19 wraps the task and its related records. Keep the board
        # interface stable for the gateway, watcher, and in-memory backend.
        if isinstance(detail, dict) and isinstance(detail.get("task"), dict):
            task = dict(detail["task"])
            for key in (
                "comments",
                "events",
                "runs",
                "parents",
                "children",
                "latest_summary",
            ):
                if key in detail:
                    task[key] = detail[key]
            return task
        return detail

    def create(self, title, body, assignee, idempotency_key):
        # VERIFY-ON-BOX: intake's dedupe rests on this returning the EXISTING task (not an
        # error, not a duplicate) when the key is already known. Confirm during smoke 1.
        return self._run(
            [
                "create",
                title,
                "--body",
                body,
                "--assignee",
                assignee,
                "--initial-status",
                BACKLOG,
                "--idempotency-key",
                idempotency_key,
            ]
        )

    def assign(self, task_id, profile):
        self._run(["assign", task_id, profile], json_out=False)

    def promote(self, task_id):
        self._run(["promote", task_id], json_out=False)

    def comment(self, task_id, text, author):
        self._run(["comment", task_id, text, "--author", author], json_out=False)

    def block(self, task_id, reason):
        self._run(["block", task_id, reason], json_out=False)

    def archive(self, task_id):
        self._run(["archive", task_id], json_out=False)

    def notify_subscribe(self, task_id, platform, chat_id):
        self._run(
            ["notify-subscribe", task_id, "--platform", platform, "--chat-id", chat_id],
            json_out=False,
        )


class MemoryBoard(Board):
    """Test/dry-run backend. JSON-file backed so multiple processes share one board."""

    def __init__(self, path: str | os.PathLike | None = None):
        self.path = pathlib.Path(path) if path else None
        self._lock = threading.Lock()
        self._state = {"tasks": [], "seq": 0, "keys": {}, "notifications": []}
        if self.path and self.path.exists():
            self._state = json.loads(self.path.read_text())

    def _load(self):
        if self.path and self.path.exists():
            self._state = json.loads(self.path.read_text())

    def _save(self):
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self.path.write_text(json.dumps(self._state, indent=2))

    def _find(self, task_id: str) -> dict:
        for t in self._state["tasks"]:
            if t["id"] == task_id:
                return t
        raise BoardError(f"no such task: {task_id}")

    def _touch(self, task: dict):
        task["updated"] = time.time()

    def list_tasks(self, assignee=None, status=None, archived=False):
        with self._lock:
            self._load()
            out = []
            for t in self._state["tasks"]:
                if not archived and t["status"] == ARCHIVED:
                    continue
                if assignee and t.get("assignee") != assignee:
                    continue
                if status and t.get("status") != status:
                    continue
                out.append(copy.deepcopy(t))
            return out

    def show(self, task_id):
        with self._lock:
            self._load()
            return copy.deepcopy(self._find(task_id))

    def create(self, title, body, assignee, idempotency_key):
        with self._lock:
            self._load()
            if idempotency_key in self._state["keys"]:
                return copy.deepcopy(self._find(self._state["keys"][idempotency_key]))
            self._state["seq"] += 1
            task = {
                "id": f"t_{self._state['seq']}",
                "title": title,
                "body": body,
                "assignee": assignee,
                "status": BACKLOG,
                "comments": [],
                "updated": time.time(),
                "idempotency_key": idempotency_key,
            }
            self._state["tasks"].append(task)
            self._state["keys"][idempotency_key] = task["id"]
            self._save()
            return copy.deepcopy(task)

    def assign(self, task_id, profile):
        with self._lock:
            self._load()
            t = self._find(task_id)
            t["assignee"] = profile
            self._touch(t)
            self._save()

    def promote(self, task_id):
        with self._lock:
            self._load()
            t = self._find(task_id)
            if t["status"] in (TODO, BLOCKED):
                t["status"] = READY
            self._touch(t)
            self._save()

    def comment(self, task_id, text, author):
        with self._lock:
            self._load()
            t = self._find(task_id)
            t["comments"].append({"author": author, "body": text, "at": time.time()})
            self._touch(t)
            self._save()

    def block(self, task_id, reason):
        with self._lock:
            self._load()
            t = self._find(task_id)
            t["status"] = BLOCKED
            t["comments"].append(
                {"author": "system", "body": reason, "at": time.time()}
            )
            self._touch(t)
            self._save()

    def archive(self, task_id):
        with self._lock:
            self._load()
            t = self._find(task_id)
            t["status"] = ARCHIVED
            self._touch(t)
            self._save()

    def notify_subscribe(self, task_id, platform, chat_id):
        with self._lock:
            self._load()
            self._state["notifications"].append(
                {"task": task_id, "platform": platform, "chat_id": chat_id}
            )
            self._save()


def get_board(cfg: dict | None = None) -> Board:
    """Pick the backend. Env KS_BOARD_BACKEND/KS_BOARD_PATH win over config, so tests and
    dry runs never depend on editing the deployed config."""
    cfg = cfg or {}
    backend = os.environ.get("KS_BOARD_BACKEND") or cfg.get("board", {}).get(
        "backend", "hermes"
    )
    if backend == "memory":
        path = os.environ.get("KS_BOARD_PATH") or cfg.get("board", {}).get("path")
        return MemoryBoard(path)
    if backend == "hermes":
        return HermesBoard()
    raise BoardError(f"unknown board backend: {backend}")
