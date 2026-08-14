"""Config loading and validation.

`KS_CONFIG` overrides the default location so tests, dry runs, and multiple instances on one
box never require editing a deployed file.

Validation is not ceremony: the sync legs run from systemd timers, so a missing or malformed
key would otherwise surface as a silent 3am failure in a journal nobody is reading. Every
problem is reported at once, by path, with what was expected.
"""

from __future__ import annotations

import json
import os
import pathlib

DEFAULT = pathlib.Path(__file__).parent.parent / "config.json"

LIFECYCLE_BOARDS = ("sys-intake", "sys-input", "sys-audit", "sys-done")
DOMAIN_BOARDS = (
    "work-research",
    "work-knowledge",
    "work-engineering",
    "work-infra",
    "work-writer",
)
BOARDS = (
    "sys-intake",
    *DOMAIN_BOARDS,
    "sys-input",
    "sys-audit",
    "sys-done",
)
TOKEN_FLAGS = ("create", "comment", "archive")


class ConfigError(ValueError):
    pass


def validate(cfg: dict) -> list[str]:
    """Every problem found, as human-readable strings. Empty list means good to run."""
    p: list[str] = []

    for key in ("repo_dir", "repo_url", "repo_branch"):
        if not cfg.get(key):
            p.append(f"{key}: required")
    if cfg.get("repo_dir") and not pathlib.Path(cfg["repo_dir"]).is_dir():
        p.append(
            f"repo_dir: {cfg['repo_dir']} is not a directory — clone the work ledger first"
        )

    boards = cfg.get("boards") or []
    if set(boards) != set(BOARDS):
        p.append(f"boards: expected exactly {list(BOARDS)}, got {boards}")

    backend = (cfg.get("board") or {}).get("backend")
    if backend not in ("hermes", "memory"):
        p.append(f"board.backend: expected 'hermes' or 'memory', got {backend!r}")
    if backend == "memory" and not (cfg.get("board") or {}).get("path"):
        p.append("board.path: required when board.backend is 'memory'")

    gw = cfg.get("gateway") or {}
    if not gw.get("bind"):
        p.append(
            "gateway.bind: required (use 127.0.0.1 — put TLS in front, never bind 0.0.0.0)"
        )
    elif gw["bind"] not in ("127.0.0.1", "localhost", "::1") and not (
        gw.get("containerized") is True and gw["bind"] == "0.0.0.0"
    ):
        p.append(
            f"gateway.bind: {gw['bind']} exposes the gateway directly; bind loopback and "
            f"front it with nginx/TLS"
        )
    if not isinstance(gw.get("port"), int):
        p.append("gateway.port: required, integer")

    tokens = gw.get("tokens")
    if not isinstance(tokens, dict) or not tokens:
        p.append("gateway.tokens: at least one token required")
    else:
        for tok, rule in tokens.items():
            where = f"gateway.tokens[{tok}]"
            if "REPLACE_" in tok:
                p.append(
                    f"{where}: placeholder token still in place — mint a real secret"
                )
            if len(tok) < 16 and "REPLACE_" not in tok:
                p.append(
                    f"{where}: token is short ({len(tok)} chars); use a long random secret"
                )
            if not isinstance(rule, dict) or not rule.get("agent"):
                p.append(
                    f"{where}.agent: required (the identity written to every audit line)"
                )
                continue
            for flag in TOKEN_FLAGS:
                if flag in rule and not isinstance(rule[flag], bool):
                    p.append(f"{where}.{flag}: must be true/false")
            bad = [b for b in (rule.get("move_to") or []) if b not in BOARDS]
            if bad:
                p.append(f"{where}.move_to: unknown board(s) {bad}")

    trig = cfg.get("triggers") or {}
    if not isinstance(trig.get("reject_limit"), int) or trig["reject_limit"] < 1:
        p.append("triggers.reject_limit: required, integer >= 1")
    if (
        not isinstance(trig.get("watch_interval_secs"), int)
        or trig["watch_interval_secs"] < 1
    ):
        p.append("triggers.watch_interval_secs: required, integer >= 1")
    human_chat_id = trig.get("human_telegram_chat_id")
    if not human_chat_id:
        p.append(
            "triggers.human_telegram_chat_id: not set — needs-input cards will not ping "
            "anyone (set it, or accept that humans must watch the board)"
        )

    sync = cfg.get("sync") or {}
    if not sync.get("snapshot_path"):
        p.append(
            "sync.snapshot_path: required (where board-state.md is written in the ledger)"
        )
    wip = sync.get("wip_limit")
    if wip is not None and (not isinstance(wip, int) or wip < 1):
        p.append(
            "sync.wip_limit: must be a positive integer, or null to disable admission"
        )
    retries = sync.get("push_retries")
    if retries is not None and (
        not isinstance(retries, list)
        or not all(isinstance(r, int) and r >= 0 for r in retries)
    ):
        p.append("sync.push_retries: must be a list of non-negative integers")

    return p


def load(path: str | os.PathLike | None = None, check: bool = True) -> dict:
    p = pathlib.Path(path or os.environ.get("KS_CONFIG") or DEFAULT)
    if not p.exists():
        raise FileNotFoundError(
            f"KS config not found at {p} — copy config.example.json to config.json, "
            f"or set KS_CONFIG."
        )
    cfg = json.loads(p.read_text())
    if check:
        problems = validate(cfg)
        if problems:
            listed = "\n".join(f"  - {x}" for x in problems)
            raise ConfigError(f"{p} has {len(problems)} problem(s):\n{listed}")
    return cfg


def main() -> int:
    """`python3 sync/ksconfig.py [path]` — validate a config without starting anything."""
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else None
    p = pathlib.Path(target or os.environ.get("KS_CONFIG") or DEFAULT)
    if not p.exists():
        print(f"✗ {p} does not exist")
        return 1
    problems = validate(json.loads(p.read_text()))
    if problems:
        print(f"✗ {p} — {len(problems)} problem(s):")
        for x in problems:
            print(f"  - {x}")
        return 1
    print(f"✓ {p} looks good")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
