#!/usr/bin/env python3
"""Validate and install the persistent Hermes profile team.

The installer deliberately creates blank profiles and then applies explicit
configuration. It never clones the default profile, its .env, auth.json,
memory, sessions, or gateway state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "profiles" / "manifest.json"
FORBIDDEN_TOOLSETS = {"delegation", "hermes-cli", "hermes-cron", "coding"}
OPEN_NOTEBOOK_READ_TOOLS = [
    "list_notebooks",
    "get_notebook",
    "list_sources",
    "get_source",
    "list_notes",
    "get_note",
    "search_notebook",
]
OPEN_NOTEBOOK_WRITE_TOOLS = [
    *OPEN_NOTEBOOK_READ_TOOLS,
    "create_notebook",
    "update_notebook",
    "create_link_source",
    "update_source",
    "create_note",
    "update_note",
]
COMMON_CONFIG: dict[str, Any] = {
    "_config_version": 33,
    "model": {
        "default": "glm-5.2",
        "provider": "opencode-go",
        "persist_switch_by_default": False,
    },
    "terminal": {"home_mode": "profile"},
    "agent": {
        "disabled_toolsets": ["delegation"],
        "restart_drain_timeout": 180,
    },
    "delegation": {
        "orchestrator_enabled": False,
        "max_spawn_depth": 1,
        "max_concurrent_children": 1,
        "subagent_auto_approve": False,
    },
    "kanban": {
        "dispatch_in_gateway": False,
        "max_in_progress_per_profile": 1,
        "auto_decompose": False,
    },
    "memory": {"write_approval": True},
}


class TeamError(ValueError):
    pass


def load_manifest(path: Path = MANIFEST) -> dict[str, Any]:
    data = json.loads(path.read_text())
    errors: list[str] = []
    if data.get("schema_version") != 2:
        errors.append("schema_version must be 2")
    orchestrator = data.get("orchestrator") or {}
    if orchestrator.get("profile") != "default":
        errors.append("the live orchestrator must remain the default profile")
    routing = data.get("routing_policy") or {}
    primary = routing.get("primary") or {}
    fallback_providers = routing.get("fallback_providers") or []
    if not primary.get("provider") or not primary.get("model"):
        errors.append("routing_policy.primary requires provider and model")
    fallback_provider_names = [item.get("provider") for item in fallback_providers]
    if len(fallback_providers) < 2:
        errors.append("routing_policy requires at least two independent fallbacks")
    if any(
        not item.get("provider") or not item.get("model") for item in fallback_providers
    ):
        errors.append("every fallback requires provider and model")
    if primary.get("provider") in fallback_provider_names:
        errors.append("fallback providers must be independent of the primary provider")
    if len(set(fallback_provider_names)) != len(fallback_provider_names):
        errors.append("fallback provider identities must be unique")
    profiles = data.get("profiles") or []
    names = [item.get("name") for item in profiles]
    if len(profiles) != 15 or len(set(names)) != 15 or None in names:
        errors.append("manifest must define exactly 15 uniquely named child profiles")
    roster = {"default", *names}
    integrations = data.get("integrations") or {}
    last30days = integrations.get("last30days") or {}
    if last30days.get("profiles") != ["research-signal"]:
        errors.append("last30days must be assigned only to research-signal")
    if last30days.get("skill") != "last30days" or not last30days.get("commit"):
        errors.append("last30days requires a named skill and pinned commit")
    open_notebook = integrations.get("open_notebook") or {}
    writer_profile = open_notebook.get("writer_profile")
    read_profiles = set(open_notebook.get("read_profiles") or [])
    if writer_profile != "knowledge-custodian":
        errors.append("knowledge-custodian must be the sole Open Notebook writer")
    if writer_profile in read_profiles:
        errors.append("Open Notebook writer must not also be declared as a reader")
    if not open_notebook.get("image") or "@sha256:" not in open_notebook.get(
        "image", ""
    ):
        errors.append("Open Notebook image must be pinned by digest")
    declared_access = {
        name: item.get("open_notebook_access")
        for name, item in [
            (orchestrator.get("profile"), orchestrator),
            *((item.get("name"), item) for item in profiles),
        ]
        if item.get("open_notebook_access")
    }
    if {name for name, access in declared_access.items() if access == "write"} != {
        writer_profile
    }:
        errors.append(
            "exactly knowledge-custodian must declare Open Notebook write access"
        )
    if {
        name for name, access in declared_access.items() if access == "read"
    } != read_profiles:
        errors.append("Open Notebook read access must match integrations.open_notebook")
    if any(access not in {"read", "write"} for access in declared_access.values()):
        errors.append("Open Notebook access must be read or write")
    for item in profiles:
        name = item.get("name", "<missing>")
        if item.get("parent") not in roster:
            errors.append(f"{name}: unknown parent {item.get('parent')!r}")
        toolsets = set(item.get("toolsets") or [])
        forbidden = sorted(toolsets & FORBIDDEN_TOOLSETS)
        if forbidden:
            errors.append(f"{name}: forbidden toolsets {forbidden}")
        if "kanban" not in toolsets:
            errors.append(f"{name}: kanban toolset is required")
        has_last30days = "last30days" in (item.get("skills") or [])
        if has_last30days != (name == "research-signal"):
            errors.append(
                f"{name}: Last30days skill assignment violates research boundary"
            )
        soul = ROOT / "profiles" / name / "SOUL.md"
        if not soul.is_file():
            errors.append(f"{name}: missing {soul}")
    orchestrator_tools = set(orchestrator.get("toolsets") or [])
    forbidden = sorted(orchestrator_tools & FORBIDDEN_TOOLSETS)
    if forbidden:
        errors.append(f"default orchestrator: forbidden toolsets {forbidden}")
    if "kanban" not in orchestrator_tools:
        errors.append("default orchestrator: kanban toolset is required")
    if errors:
        raise TeamError("\n".join(errors))
    return data


def _atomic_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, staged_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            yaml.safe_dump(data, stream, sort_keys=False)
        os.chmod(staged_name, 0o600)
        os.replace(staged_name, path)
    finally:
        if os.path.exists(staged_name):
            os.unlink(staged_name)


def _runtime_routing(
    manifest: dict[str, Any],
) -> tuple[dict[str, str], list[dict[str, str]]]:
    routing = manifest["routing_policy"]
    primary = routing["primary"]
    model = {
        "default": primary["model"],
        "provider": primary["provider"],
        "persist_switch_by_default": False,
    }
    fallbacks = [
        {"provider": item["provider"], "model": item["model"]}
        for item in routing["fallback_providers"]
    ]
    return model, fallbacks


def _open_notebook_server(access: str) -> tuple[str, dict[str, Any]]:
    name = f"open-notebook-{access}"
    tools = OPEN_NOTEBOOK_WRITE_TOOLS if access == "write" else OPEN_NOTEBOOK_READ_TOOLS
    return name, {
        "command": sys.executable,
        "args": [str(ROOT / "mcp" / "open_notebook_mcp.py")],
        "env": {
            "OPEN_NOTEBOOK_GATEWAY_URL": os.environ.get(
                "OPEN_NOTEBOOK_GATEWAY_URL", "http://127.0.0.1:8765"
            ),
            "OPEN_NOTEBOOK_ACCESS_TOKEN": "${OPEN_NOTEBOOK_ACCESS_TOKEN}",
            "OPEN_NOTEBOOK_MODE": access,
        },
        "tools": {"include": tools},
        "connect_timeout": 30,
        "timeout": 90,
        "enabled": True,
    }


def _add_open_notebook(config: dict[str, Any], access: str | None) -> None:
    if access not in {"read", "write"}:
        return
    name, server = _open_notebook_server(access)
    config.setdefault("mcp_servers", {})[name] = server
    if name not in config["toolsets"]:
        config["toolsets"].append(name)
    for tools in config["platform_toolsets"].values():
        if name not in tools:
            tools.append(name)


def _profile_config(
    profile: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    config = json.loads(json.dumps(COMMON_CONFIG))
    model, fallbacks = _runtime_routing(manifest)
    config["model"] = model
    config["fallback_providers"] = fallbacks
    toolsets = list(profile["toolsets"])
    config["toolsets"] = toolsets
    config["platform_toolsets"] = {
        "cli": toolsets,
        "gateway": toolsets,
        "cron": toolsets,
    }
    _add_open_notebook(config, profile.get("open_notebook_access"))
    return config


def _merge_orchestrator_config(
    path: Path, orchestrator: dict[str, Any], manifest: dict[str, Any]
) -> dict[str, Any]:
    config = yaml.safe_load(path.read_text()) or {}
    model, fallbacks = _runtime_routing(manifest)
    config["model"] = model
    config["fallback_providers"] = fallbacks
    toolsets = list(orchestrator["toolsets"])
    config["toolsets"] = toolsets
    platform_toolsets = config.setdefault("platform_toolsets", {})
    for platform in ("cli", "gateway", "whatsapp", "whatsapp_cloud", "cron"):
        platform_toolsets[platform] = toolsets
    _add_open_notebook(config, orchestrator.get("open_notebook_access"))
    terminal = config.setdefault("terminal", {})
    terminal["home_mode"] = "profile"
    agent = config.setdefault("agent", {})
    disabled = {str(item) for item in agent.get("disabled_toolsets") or []}
    disabled.add("delegation")
    agent["disabled_toolsets"] = sorted(disabled)
    agent["restart_drain_timeout"] = COMMON_CONFIG["agent"]["restart_drain_timeout"]
    delegation = config.setdefault("delegation", {})
    delegation.update(COMMON_CONFIG["delegation"])
    kanban = config.setdefault("kanban", {})
    kanban.update(
        {
            "dispatch_in_gateway": True,
            "orchestrator_profile": "default",
            "default_assignee": "default",
            "max_in_progress_per_profile": 1,
            "auto_decompose": False,
        }
    )
    return config


def _copy_skills(source_root: Path, profile_home: Path, skills: list[str]) -> None:
    for relative in skills:
        source = source_root / relative
        if not source.is_dir():
            raise TeamError(f"approved skill source is missing: {source}")
        target = profile_home / "skills" / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, symlinks=True, dirs_exist_ok=True)


def apply_team(
    manifest: dict[str, Any],
    hermes_home: Path,
    hermes_bin: str,
    *,
    dry_run: bool,
) -> None:
    profiles_root = hermes_home / "profiles"
    source_skills = hermes_home / "skills"
    orchestrator = manifest["orchestrator"]
    if dry_run:
        print(
            f"DRY RUN default: merge explicit toolsets into {hermes_home / 'config.yaml'}"
        )
    else:
        merged = _merge_orchestrator_config(
            hermes_home / "config.yaml", orchestrator, manifest
        )
        _atomic_yaml(hermes_home / "config.yaml", merged)
        print("UPDATED default orchestrator config; existing identity preserved")

    for item in manifest["profiles"]:
        name = item["name"]
        profile_home = profiles_root / name
        if not profile_home.exists():
            if dry_run:
                print(f"DRY RUN create {name}")
            else:
                command_env = os.environ.copy()
                command_env["HERMES_HOME"] = str(hermes_home)
                subprocess.run(
                    [
                        hermes_bin,
                        "profile",
                        "create",
                        "--no-alias",
                        "--no-skills",
                        "--description",
                        item["description"],
                        name,
                    ],
                    check=True,
                    env=command_env,
                )
                print(f"CREATED {name}")
        else:
            print(f"EXISTS {name}; applying canonical identity and config")
        if dry_run:
            continue
        shutil.copy2(ROOT / "profiles" / name / "SOUL.md", profile_home / "SOUL.md")
        os.chmod(profile_home / "SOUL.md", 0o600)
        _atomic_yaml(profile_home / "config.yaml", _profile_config(item, manifest))
        _copy_skills(source_skills, profile_home, item.get("skills") or [])
        env_path = profile_home / ".env"
        if not env_path.exists():
            env_path.write_text("# Intentionally empty: profile-scoped secrets only.\n")
        os.chmod(env_path, 0o600)
        print(
            f"APPLIED {name}: {len(item['toolsets'])} toolsets, "
            f"{len(item.get('skills') or [])} approved skills"
        )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--hermes-home",
        type=Path,
        default=Path(os.environ.get("HERMES_HOME", "~/.hermes")).expanduser(),
    )
    parser.add_argument("--hermes-bin", default=shutil.which("hermes") or "hermes")
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    parser.add_argument("--validate-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    manifest = load_manifest(args.manifest)
    if args.validate_only:
        print("PASS team manifest: orchestrator plus 15 profiles; delegation absent")
        return 0
    apply_team(
        manifest, args.hermes_home.resolve(), args.hermes_bin, dry_run=args.dry_run
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
