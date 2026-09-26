#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import pathlib
import unittest

import yaml


ROOT = pathlib.Path(__file__).parent.parent
MANIFEST_PATH = ROOT / "profiles" / "manifest.json"
EXPECTED_PROFILES = {
    "research-lead",
    "research-signal",
    "research-source",
    "knowledge-custodian",
    "knowledge-provenance",
    "engineering-lead",
    "engineering-builder",
    "engineering-review",
    "infra-guardian",
    "infra-sysops",
    "infra-netops",
    "writer-director",
    "writer-longform",
    "writer-social",
    "audit-controller",
}


class TestProfileArchitecture(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.manifest = json.loads(MANIFEST_PATH.read_text())
        cls.profiles = {item["name"]: item for item in cls.manifest["profiles"]}

    def test_manifest_defines_reference_team_of_sixteen(self):
        self.assertEqual(self.manifest["schema_version"], 2)
        self.assertEqual(self.manifest["orchestrator"]["profile"], "default")
        self.assertEqual(set(self.profiles), EXPECTED_PROFILES)
        self.assertEqual(len(self.profiles) + 1, 16)

    def test_routing_policy_uses_independent_subscriptions(self):
        routing = self.manifest["routing_policy"]
        self.assertEqual(
            routing["primary"], {"provider": "opencode-go", "model": "glm-5.2"}
        )
        fallbacks = routing["fallback_providers"]
        providers = [item["provider"] for item in fallbacks]
        self.assertEqual(providers, ["opencode-zen", "openai-codex"])
        self.assertNotIn(routing["primary"]["provider"], providers)
        self.assertEqual(fallbacks[0]["model"], "kimi-k2.7-code")
        self.assertEqual(fallbacks[1]["model"], "gpt-5.6-sol")

    def test_hierarchy_is_explicit_and_grounded(self):
        roster = {"default", *self.profiles}
        for name, profile in self.profiles.items():
            self.assertIn(profile["parent"], roster, name)
            if profile["kind"] in {"lead", "audit"}:
                self.assertEqual(profile["parent"], "default", name)
        for name in ("research-signal", "research-source"):
            self.assertEqual(self.profiles[name]["parent"], "research-lead")
        for name in ("engineering-builder", "engineering-review"):
            self.assertEqual(self.profiles[name]["parent"], "engineering-lead")

    def test_every_profile_has_a_specific_soul(self):
        for name in self.profiles:
            soul = ROOT / "profiles" / name / "SOUL.md"
            self.assertTrue(soul.is_file(), name)
            text = soul.read_text()
            self.assertIn(name, text.splitlines()[0], name)
            self.assertIn("delegate_task", text, name)

    def test_delegation_is_absent_from_every_toolset(self):
        all_profiles = [self.manifest["orchestrator"], *self.profiles.values()]
        for profile in all_profiles:
            toolsets = set(profile["toolsets"])
            self.assertIn("kanban", toolsets)
            self.assertTrue(
                toolsets.isdisjoint(
                    {"delegation", "hermes-cli", "hermes-cron", "coding"}
                )
            )

    def test_knowledge_and_operational_audit_are_separate(self):
        custodian = (ROOT / "profiles" / "knowledge-custodian" / "SOUL.md").read_text()
        provenance = (
            ROOT / "profiles" / "knowledge-provenance" / "SOUL.md"
        ).read_text()
        audit = (ROOT / "profiles" / "audit-controller" / "SOUL.md").read_text()
        self.assertIn("ONLY Hermes profile", custodian)
        self.assertIn("Never write Open Notebook", provenance)
        self.assertIn("never repair", audit.lower())
        self.assertIn("epistemic", audit)

    def test_last30days_is_pinned_and_only_on_signal_scout(self):
        integration = self.manifest["integrations"]["last30days"]
        self.assertEqual(integration["profiles"], ["research-signal"])
        self.assertEqual(len(integration["commit"]), 40)
        assigned = {
            name
            for name, profile in self.profiles.items()
            if "last30days" in profile.get("skills", [])
        }
        self.assertEqual(assigned, {"research-signal"})

    def test_open_notebook_access_has_one_writer(self):
        integration = self.manifest["integrations"]["open_notebook"]
        self.assertEqual(integration["writer_profile"], "knowledge-custodian")
        self.assertIn("@sha256:", integration["image"])
        writers = {
            name
            for name, profile in self.profiles.items()
            if profile.get("open_notebook_access") == "write"
        }
        self.assertEqual(writers, {"knowledge-custodian"})

    def test_installer_creates_blank_profiles_through_team_applier(self):
        installer = (ROOT / "install" / "install_ksm.sh").read_text()
        applier = (ROOT / "profiles" / "apply_team.py").read_text()
        self.assertIn("profiles/apply_team.py", installer)
        self.assertNotIn("profile create --clone", installer)
        self.assertIn('"--no-skills"', applier)
        self.assertNotIn('"--clone"', applier)

    def test_team_applier_validates_manifest(self):
        spec = importlib.util.spec_from_file_location(
            "apply_team", ROOT / "profiles" / "apply_team.py"
        )
        module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(module)
        loaded = module.load_manifest()
        self.assertEqual(len(loaded["profiles"]), 15)

    def test_compose_has_project_scoping_and_no_docker_socket(self):
        compose = (ROOT / "compose.yaml").read_text()
        self.assertIn("COMPOSE_PROJECT_NAME", compose)
        self.assertIn("127.0.0.1:${KSM_PORT:-8742}:8742", compose)
        self.assertNotIn("container_name:", compose)
        self.assertNotIn("/var/run/docker.sock", compose)
        self.assertNotIn("OP_SERVICE_ACCOUNT_TOKEN", compose)

    def test_docker_orchestrator_disables_delegation(self):
        cfg = (ROOT / "docker" / "hermes.config.yaml").read_text()
        for fragment in (
            "_config_version: 33",
            "multiplex_profiles: true",
            "home_mode: profile",
            "orchestrator_enabled: false",
            "max_in_progress_per_profile: 1",
            "auto_decompose: false",
            "disabled_toolsets:",
            "restart_drain_timeout: 180",
        ):
            self.assertIn(fragment, cfg)
        parsed = yaml.safe_load(cfg)
        self.assertEqual(parsed["model"]["provider"], "opencode-go")
        self.assertEqual(parsed["model"]["default"], "glm-5.2")
        self.assertEqual(
            [item["provider"] for item in parsed["fallback_providers"]],
            ["opencode-zen", "openai-codex"],
        )
        self.assertNotIn("delegation", parsed["toolsets"])
        self.assertNotIn("hermes-cli", parsed["toolsets"])
        self.assertIn("delegation", parsed["agent"]["disabled_toolsets"])


if __name__ == "__main__":
    unittest.main(verbosity=2)
