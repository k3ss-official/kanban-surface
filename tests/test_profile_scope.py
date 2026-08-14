#!/usr/bin/env python3
"""Run inside the pinned Hermes image; proves multiplex secret resolution fails closed."""

from __future__ import annotations

import os
import pathlib
import tempfile

from agent.secret_scope import (  # type: ignore
    UnscopedSecretError,
    build_profile_secret_scope,
    get_secret,
    reset_secret_scope,
    set_multiplex_active,
    set_secret_scope,
)


def main() -> int:
    research_key = "RESEARCH_CANARY_KSM_TEST"
    knowledge_key = "KNOWLEDGE_CANARY_KSM_TEST"
    os.environ.pop(research_key, None)
    os.environ.pop(knowledge_key, None)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        research = root / "research"
        knowledge = root / "knowledge"
        research.mkdir()
        knowledge.mkdir()
        (research / ".env").write_text(f"{research_key}=research-only\n")
        (knowledge / ".env").write_text(f"{knowledge_key}=knowledge-only\n")

        set_multiplex_active(True)
        token = set_secret_scope(build_profile_secret_scope(research))
        try:
            assert get_secret(research_key) == "research-only"
            assert get_secret(knowledge_key) is None
        finally:
            reset_secret_scope(token)

        token = set_secret_scope(build_profile_secret_scope(knowledge))
        try:
            assert get_secret(knowledge_key) == "knowledge-only"
            assert get_secret(research_key) is None
        finally:
            reset_secret_scope(token)

        try:
            get_secret(research_key)
        except UnscopedSecretError:
            pass
        else:
            raise AssertionError(
                "multiplex secret read outside a profile scope did not fail closed"
            )

    print(
        "PASS Hermes multiplex profile secret scope: own canary visible; sibling absent; unscoped denied"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
