#!/usr/bin/env python3
"""Read-only acceptance checks for an installed persistent Hermes team."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import sys
from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parent.parent
MANIFEST = ROOT / "profiles" / "manifest.json"
FORBIDDEN = {"delegation", "hermes-cli", "hermes-cron", "coding"}
ENV_KEY = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def env_keys(path: Path) -> list[str]:
    keys: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        match = ENV_KEY.match(line)
        if match:
            keys.append(match.group(1))
    return keys


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_native_resolution(hermes_home: Path, manifest: dict) -> int:
    source = hermes_home / "hermes-agent"
    if not (source / "toolsets.py").is_file():
        return 0
    sys.path[:0] = [str(source), str(source / "tools")]
    from hermes_cli.tools_config import _get_platform_tools
    from toolsets import resolve_toolset, validate_toolset

    checks = [
        (
            "default",
            hermes_home,
            ["cli", "gateway", "whatsapp", "whatsapp_cloud", "cron"],
        )
    ]
    checks.extend(
        (
            item["name"],
            hermes_home / "profiles" / item["name"],
            ["cli", "gateway", "cron"],
        )
        for item in manifest["profiles"]
    )
    count = 0
    for name, home, platforms in checks:
        config = yaml.safe_load((home / "config.yaml").read_text()) or {}
        for platform in platforms:
            enabled = _get_platform_tools(config, platform)
            require(
                "delegation" not in enabled, f"{name}/{platform}: delegation enabled"
            )
            require(
                "coding" not in enabled, f"{name}/{platform}: coding composite enabled"
            )
            resolved = {
                tool
                for toolset in enabled
                if validate_toolset(toolset)
                for tool in resolve_toolset(toolset)
            }
            blocked = sorted(
                tool
                for tool in resolved
                if tool == "delegate_task" or tool.startswith("delegate_")
            )
            require(not blocked, f"{name}/{platform}: delegation tools {blocked}")
            require(
                any(tool.startswith("kanban_") for tool in resolved),
                f"{name}/{platform}: no native Kanban tools",
            )
            count += 1
    return count


def validate(hermes_home: Path) -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    expected = {item["name"] for item in manifest["profiles"]}
    profiles_root = hermes_home / "profiles"
    installed = {
        path.name
        for path in profiles_root.iterdir()
        if path.is_dir() and not path.name.startswith(".")
    }
    require(installed == expected, f"profile roster mismatch: {installed ^ expected}")

    default_soul = (hermes_home / "SOUL.md").read_text(encoding="utf-8")
    require(bool(default_soul.strip()), "default orchestrator identity is empty")
    default_config = yaml.safe_load((hermes_home / "config.yaml").read_text()) or {}
    root_auth = hermes_home / "auth.json"
    root_auth_hash = sha256(root_auth) if root_auth.is_file() else None
    routing = manifest["routing_policy"]
    expected_fallbacks = [
        {"provider": item["provider"], "model": item["model"]}
        for item in routing["fallback_providers"]
    ]
    require(
        default_config.get("fallback_providers") == expected_fallbacks,
        "default fallback chain differs from routing policy",
    )
    require(
        default_config.get("toolsets")
        == [*manifest["orchestrator"]["toolsets"], "open-notebook-read"],
        "default toolsets differ from manifest",
    )
    default_open_notebook = default_config.get("mcp_servers", {}).get(
        "open-notebook-read", {}
    )
    require(
        default_open_notebook.get("enabled") is True, "default notebook reader missing"
    )
    require(
        default_config.get("delegation", {}).get("orchestrator_enabled") is False,
        "default delegation is enabled",
    )
    require(
        "delegation" in default_config.get("agent", {}).get("disabled_toolsets", []),
        "default delegation toolset is not hard-disabled",
    )
    require(
        default_config.get("agent", {}).get("restart_drain_timeout") == 180,
        "default gateway restart drain is not 180 seconds",
    )
    for platform in ("cli", "gateway", "whatsapp", "whatsapp_cloud", "cron"):
        require(
            default_config.get("platform_toolsets", {}).get(platform)
            == [*manifest["orchestrator"]["toolsets"], "open-notebook-read"],
            f"default {platform} tools differ from manifest",
        )
    require(
        default_config.get("kanban", {}).get("dispatch_in_gateway") is True,
        "default Kanban dispatcher is disabled",
    )

    for item in manifest["profiles"]:
        name = item["name"]
        home = profiles_root / name
        soul = home / "SOUL.md"
        config_path = home / "config.yaml"
        env_path = home / ".env"
        for path in (soul, config_path, env_path):
            require(path.is_file(), f"{name}: missing {path.name}")
            require(mode(path) == 0o600, f"{name}: {path.name} mode is {mode(path):o}")

        config = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
        require(
            config.get("fallback_providers") == expected_fallbacks,
            f"{name}: fallback chain differs from routing policy",
        )
        toolsets = config.get("toolsets") or []
        access = item.get("open_notebook_access")
        expected_toolsets = list(item["toolsets"])
        if access:
            expected_toolsets.append(f"open-notebook-{access}")
        require(toolsets == expected_toolsets, f"{name}: toolsets differ from manifest")
        require("kanban" in toolsets, f"{name}: Kanban unavailable")
        require(not (set(toolsets) & FORBIDDEN), f"{name}: forbidden toolset enabled")
        require(
            config.get("delegation", {}).get("orchestrator_enabled") is False,
            f"{name}: delegation is enabled",
        )
        require(
            "delegation" in config.get("agent", {}).get("disabled_toolsets", []),
            f"{name}: delegation toolset is not hard-disabled",
        )
        require(
            config.get("agent", {}).get("restart_drain_timeout") == 180,
            f"{name}: gateway restart drain is not 180 seconds",
        )
        for platform in ("cli", "gateway", "cron"):
            require(
                config.get("platform_toolsets", {}).get(platform) == expected_toolsets,
                f"{name}: {platform} tools differ from manifest",
            )
        if access:
            server_name = f"open-notebook-{access}"
            server = config.get("mcp_servers", {}).get(server_name, {})
            require(server.get("enabled") is True, f"{name}: notebook MCP missing")
            require(
                server.get("env", {}).get("OPEN_NOTEBOOK_MODE") == access,
                f"{name}: notebook MCP role mismatch",
            )
        require(
            config.get("terminal", {}).get("home_mode") == "profile",
            f"{name}: terminal is not profile-scoped",
        )
        profile_auth = home / "auth.json"
        if profile_auth.exists():
            require(profile_auth.is_file(), f"{name}: auth.json is not a regular file")
            require(not profile_auth.is_symlink(), f"{name}: auth.json is a symlink")
            require(mode(profile_auth) == 0o600, f"{name}: auth.json mode is unsafe")
            if root_auth_hash is not None:
                require(
                    sha256(profile_auth) != root_auth_hash,
                    f"{name}: root auth.json was cloned byte-for-byte",
                )
        keys = set(env_keys(env_path))
        if access:
            require(
                keys <= {"OPEN_NOTEBOOK_ACCESS_TOKEN"},
                f"{name}: unexpected profile credential keys {keys}",
            )
        else:
            require(not keys, f"{name}: credential keys were copied")
        require(
            (home / ".no-bundled-skills").is_file(), f"{name}: skill opt-out missing"
        )
        for relative in item.get("skills") or []:
            require(
                (home / "skills" / relative).is_dir(),
                f"{name}: missing skill {relative}",
            )

    native_checks = validate_native_resolution(hermes_home, manifest)
    print(
        "PASS live team: orchestrator plus 15 profiles; explicit tools, "
        "profile homes, no cloned root credential store, delegation disabled; "
        f"{native_checks} native platform surfaces resolved"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--hermes-home", type=Path, required=True)
    args = parser.parse_args()
    validate(args.hermes_home.expanduser().resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
