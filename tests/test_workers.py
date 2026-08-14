#!/usr/bin/env python3
"""Truthful worker projection from active Hermes run evidence."""

from __future__ import annotations

import json
import pathlib
import sys
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

ROOT = pathlib.Path(__file__).parent.parent
for sub in ("sync", "gateway"):
    sys.path.insert(0, str(ROOT / sub))

import board as board_mod  # noqa: E402
import workers  # noqa: E402
from gateway import Gateway, make_handler  # noqa: E402


class HermesBoardRunEvidence(unittest.TestCase):
    def test_list_enriches_only_running_summaries_from_highest_active_run(self):
        brd = board_mod.HermesBoard()
        summaries = [
            {"id": "t_running", "assignee": "engineering-builder", "status": "running"},
            {"id": "t_ready", "assignee": "engineering-review", "status": "ready"},
        ]

        def run(args, json_out=True):
            if args == ["list"]:
                return summaries
            if args == ["show", "t_running"]:
                return {
                    "task": summaries[0],
                    "runs": [
                        {
                            "id": 4,
                            "status": "running",
                            "ended_at": None,
                            "worker_pid": 444,
                        },
                        {
                            "id": 9,
                            "status": "running",
                            "ended_at": None,
                            "worker_pid": 999,
                        },
                        {"id": 12, "status": "done", "ended_at": 1, "worker_pid": 1212},
                    ],
                }
            raise AssertionError(f"unexpected Hermes call: {args}")

        with mock.patch.object(brd, "_run", side_effect=run) as cli:
            tasks = brd.list_tasks()

        self.assertEqual(tasks[0]["current_run_id"], 9)
        self.assertEqual(tasks[0]["worker_pid"], 999)
        self.assertNotIn("current_run_id", tasks[1])
        self.assertEqual(
            [call.args[0] for call in cli.call_args_list],
            [["list"], ["show", "t_running"]],
            "non-running summaries must not incur show calls",
        )

    def test_show_failures_and_malformed_or_stale_runs_leave_summary_unchanged(self):
        invalid_runs = [
            mock.DEFAULT,
            {},
            {"runs": None},
            {"runs": 3},
            {"runs": {}},
            {"runs": "running"},
            {"runs": [{"id": True, "status": "running", "ended_at": None}]},
            {"runs": [{"id": 0, "status": "running", "ended_at": None}]},
            {"runs": [{"id": -1, "status": "running", "ended_at": None}]},
            {"runs": [{"id": "7", "status": "running", "ended_at": None}]},
            {"runs": [{"id": 7.0, "status": "running", "ended_at": None}]},
            {"runs": [{"id": 7, "status": "running", "ended_at": 123}]},
            {"runs": [{"id": 7, "status": "done", "ended_at": None}]},
        ]

        for detail in invalid_runs:
            with self.subTest(detail=detail):
                brd = board_mod.HermesBoard()
                summary = {
                    "id": "t_running",
                    "assignee": "builder",
                    "status": "running",
                }

                def run(args, json_out=True):
                    if args == ["list"]:
                        return [dict(summary)]
                    if detail is mock.DEFAULT:
                        raise board_mod.BoardError("show unavailable")
                    return detail

                with mock.patch.object(brd, "_run", side_effect=run):
                    self.assertEqual(brd.list_tasks(), [summary])


class WorkerProjection(unittest.TestCase):
    def test_counts_only_running_tasks_with_canonical_run_evidence(self):
        tasks = [
            {
                "id": "t_build",
                "assignee": "engineering-builder",
                "status": "running",
                "current_run_id": 17,
                "worker_pid": 1700,
            },
            {
                "id": "t_review",
                "assignee": "engineering-review",
                "status": "running",
                "current_run_id": 22,
                "worker_pid": -1,
            },
            {
                "id": "t_ready",
                "assignee": "engineering-builder",
                "status": "ready",
                "current_run_id": 30,
            },
            {
                "id": "t_blocked",
                "assignee": "engineering-review",
                "status": "blocked",
                "current_run_id": 31,
            },
            {
                "id": "t_done",
                "assignee": "engineering-review",
                "status": "done",
                "current_run_id": 32,
            },
            {"id": "t_missing", "assignee": "other-profile", "status": "running"},
        ]
        for value in (True, 0, -1, "23", 23.0):
            tasks.append(
                {
                    "id": f"t_invalid_{value!r}",
                    "assignee": "other-profile",
                    "status": "running",
                    "current_run_id": value,
                }
            )

        result = workers.project(tasks)

        self.assertEqual(result["working_count"], 2)
        self.assertEqual(result["working_count"], len(result["working_workers"]))
        self.assertEqual(
            result["working_workers"],
            [
                {
                    "agent": "engineering-builder",
                    "task_id": "t_build",
                    "run_id": 17,
                    "worker_pid": 1700,
                },
                {"agent": "engineering-review", "task_id": "t_review", "run_id": 22},
            ],
        )

    def test_worker_pid_is_optional_and_must_be_a_canonical_positive_integer(self):
        for pid in (True, 0, -1, "1700", 1700.0):
            with self.subTest(pid=pid):
                result = workers.project(
                    [
                        {
                            "id": "t_build",
                            "assignee": "engineering-builder",
                            "status": "running",
                            "current_run_id": 17,
                            "worker_pid": pid,
                        }
                    ]
                )
                self.assertEqual(
                    result["working_workers"],
                    [
                        {
                            "agent": "engineering-builder",
                            "task_id": "t_build",
                            "run_id": 17,
                        }
                    ],
                )


class WorkerRoute(unittest.TestCase):
    def test_workers_route_requires_token_and_returns_consistent_projection(self):
        brd = board_mod.MemoryBoard()
        brd._state["tasks"] = [
            {
                "id": "t_build",
                "assignee": "engineering-builder",
                "status": "running",
                "current_run_id": 17,
                "worker_pid": 1700,
            },
            {
                "id": "t_review",
                "assignee": "engineering-review",
                "status": "running",
                "current_run_id": 22,
            },
        ]
        cfg = {"gateway": {"audit_log": "", "tokens": {"secret": {"agent": "tester"}}}}
        server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(Gateway(cfg, brd)))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}/workers"
        try:
            with self.assertRaises(urllib.error.HTTPError) as denied:
                urllib.request.urlopen(url)
            self.assertEqual(denied.exception.code, 401)

            request = urllib.request.Request(
                url, headers={"Authorization": "Bearer secret"}
            )
            with urllib.request.urlopen(request) as response:
                payload = json.load(response)
            self.assertEqual(payload["working_count"], 2)
            self.assertEqual(payload["working_count"], len(payload["working_workers"]))
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


class WorkerUiContract(unittest.TestCase):
    def test_header_consumes_workers_api_count_without_local_inference(self):
        source = (ROOT / "ui" / "index.html").read_text()
        self.assertIn(
            'const [tasks, workerState] = await Promise.all([api("/tasks"), api("/workers")]);',
            source,
        )
        self.assertIn("${workerState.working_count} working", source)
        self.assertNotIn('tasks.filter(t => t.status === "running")', source)
        self.assertNotIn('api("/activity")', source)


if __name__ == "__main__":
    unittest.main(verbosity=2)
