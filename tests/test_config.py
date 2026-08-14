#!/usr/bin/env python3
"""Config validation — the deploy guard. A missing key must fail at install time with a
readable message, not at 3am inside a systemd timer nobody is watching.

    python3 tests/test_config.py
"""

from __future__ import annotations

import copy
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).parent.parent
sys.path.insert(0, str(ROOT / "sync"))
import ksconfig  # noqa: E402

SECRET = "a" * 40


def good_config(repo_dir: str) -> dict:
    return {
        "repo_dir": repo_dir,
        "repo_url": "https://github.com/example/work-ledger.git",
        "repo_branch": "main",
        "boards": list(ksconfig.BOARDS),
        "board": {"backend": "hermes", "path": None},
        "gateway": {
            "bind": "127.0.0.1",
            "port": 8742,
            "audit_log": "/tmp/a.jsonl",
            "tokens": {
                SECRET: {
                    "agent": "owner",
                    "create": True,
                    "comment": True,
                    "archive": True,
                    "move_to": list(ksconfig.BOARDS),
                }
            },
        },
        "triggers": {
            "human_telegram_chat_id": "123",
            "reject_limit": 2,
            "watch_interval_secs": 15,
        },
        "sync": {
            "snapshot_path": "docs/board-state.md",
            "wip_limit": 5,
            "push_retries": [0, 2],
        },
    }


class TestValidation(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = good_config(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def broken(self, mutate):
        cfg = copy.deepcopy(self.cfg)
        mutate(cfg)
        return ksconfig.validate(cfg)

    def test_a_complete_config_passes(self):
        self.assertEqual(ksconfig.validate(self.cfg), [])

    def test_the_shipped_example_is_refused_until_filled_in(self):
        """config.example.json must NOT validate — its tokens are placeholders."""
        example = json.loads((ROOT / "config.example.json").read_text())
        problems = ksconfig.validate(example)
        self.assertTrue(
            any("placeholder" in p for p in problems),
            f"example config should be refused, got {problems}",
        )

    def test_catches_missing_required_keys(self):
        self.assertTrue(
            any("repo_url" in p for p in self.broken(lambda c: c.pop("repo_url")))
        )
        self.assertTrue(
            any("repo_branch" in p for p in self.broken(lambda c: c.pop("repo_branch")))
        )
        self.assertTrue(
            any(
                "snapshot_path" in p
                for p in self.broken(lambda c: c["sync"].pop("snapshot_path"))
            )
        )
        self.assertTrue(
            any(
                "reject_limit" in p
                for p in self.broken(lambda c: c["triggers"].pop("reject_limit"))
            )
        )

    def test_catches_a_non_loopback_bind(self):
        """The plugin docs warn explicitly against exposing the board to the network; the
        gateway must sit behind TLS, never bind the world directly."""
        problems = self.broken(lambda c: c["gateway"].update(bind="0.0.0.0"))
        self.assertTrue(
            any("nginx" in p or "loopback" in p for p in problems), problems
        )

    def test_allows_container_interface_only_when_explicit(self):
        problems = self.broken(
            lambda c: c["gateway"].update(bind="0.0.0.0", containerized=True)
        )
        self.assertEqual(problems, [])

    def test_catches_weak_and_placeholder_tokens(self):
        self.assertTrue(
            any(
                "short" in p
                for p in self.broken(
                    lambda c: c["gateway"].update(tokens={"abc": {"agent": "owner"}})
                )
            )
        )
        self.assertTrue(
            any(
                "placeholder" in p
                for p in self.broken(
                    lambda c: c["gateway"].update(
                        tokens={"REPLACE_ME_TOKEN_LONG_ENOUGH": {"agent": "owner"}}
                    )
                )
            )
        )

    def test_catches_a_token_with_no_identity(self):
        """Every audit line names the requester — a token without an agent breaks that."""
        problems = self.broken(
            lambda c: c["gateway"].update(tokens={SECRET: {"create": True}})
        )
        self.assertTrue(any("agent" in p for p in problems), problems)

    def test_catches_unknown_boards(self):
        self.assertTrue(
            any(
                "unknown board" in p
                for p in self.broken(
                    lambda c: c["gateway"]["tokens"][SECRET].update(
                        move_to=["unknown-board"]
                    )
                )
            )
        )
        self.assertTrue(
            any(
                "boards:" in p
                for p in self.broken(lambda c: c.update(boards=["sys-intake"]))
            )
        )

    def test_catches_a_bad_wip_limit_but_allows_null(self):
        self.assertTrue(
            any(
                "wip_limit" in p
                for p in self.broken(lambda c: c["sync"].update(wip_limit=0))
            )
        )
        self.assertEqual(self.broken(lambda c: c["sync"].update(wip_limit=None)), [])

    def test_warns_when_nobody_gets_pinged(self):
        problems = self.broken(
            lambda c: c["triggers"].update(human_telegram_chat_id=None)
        )
        self.assertTrue(any("ping" in p for p in problems), problems)

    def test_load_raises_with_every_problem_listed(self):
        bad = copy.deepcopy(self.cfg)
        bad.pop("repo_branch")
        bad["gateway"]["bind"] = "0.0.0.0"
        path = pathlib.Path(self.tmp.name) / "config.json"
        path.write_text(json.dumps(bad))
        with self.assertRaises(ksconfig.ConfigError) as ctx:
            ksconfig.load(path)
        self.assertIn("repo_branch", str(ctx.exception))
        self.assertIn("gateway.bind", str(ctx.exception))

    def test_load_can_skip_validation_for_dry_runs(self):
        path = pathlib.Path(self.tmp.name) / "config.json"
        path.write_text(json.dumps({"repo_dir": "nowhere"}))
        self.assertEqual(ksconfig.load(path, check=False)["repo_dir"], "nowhere")

    def test_missing_file_says_what_to_do(self):
        with self.assertRaises(FileNotFoundError) as ctx:
            ksconfig.load(pathlib.Path(self.tmp.name) / "nope.json")
        self.assertIn("config.example.json", str(ctx.exception))


if __name__ == "__main__":
    unittest.main(verbosity=2)
