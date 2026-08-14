"""Project truthful working-worker rows from board task summaries."""

from __future__ import annotations


def _positive_int(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def project(tasks: list[dict]) -> dict:
    working = []
    for task in tasks:
        run_id = task.get("current_run_id")
        if task.get("status") != "running" or not _positive_int(run_id):
            continue
        worker = {
            "agent": task.get("assignee"),
            "task_id": task.get("id"),
            "run_id": run_id,
        }
        pid = task.get("worker_pid")
        if _positive_int(pid):
            worker["worker_pid"] = pid
        working.append(worker)
    return {"working_count": len(working), "working_workers": working}
