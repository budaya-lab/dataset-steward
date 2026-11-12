"""Contract checks for validation-gated release management."""
import json
import re
import tomllib
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def read_json(name):
    return json.loads((ROOT / name).read_text())


class ReleaseConfig(unittest.TestCase):
    def test_simple_releases_start_at_0_1_0(self):
        release = read_json("release-please-config.json")["packages"]["."]
        self.assertEqual(release["release-type"], "simple")
        self.assertEqual(release["initial-version"], "0.1.0")
        manifest = read_json(".release-please-manifest.json")
        self.assertTrue(set(manifest) <= {"."})
        if manifest:
            project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
            self.assertEqual(manifest["."], project["version"])

    def test_release_updates_project_and_only_the_virtual_lock_package(self):
        release = read_json("release-please-config.json")["packages"]["."]
        self.assertEqual(release["extra-files"], [
            {"type": "toml", "path": "pyproject.toml", "jsonpath": "$.project.version"},
            {"type": "toml", "path": "uv.lock", "jsonpath": "$.package[?(@.source.virtual)].version"},
        ])
        project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
        lock = tomllib.loads((ROOT / "uv.lock").read_text())
        targets = [package for package in lock["package"] if package["source"].get("virtual")]
        self.assertEqual(len(targets), 1, "the release selector must target only Steward")
        self.assertEqual(targets[0]["name"], project["name"])
        self.assertEqual(targets[0]["source"]["virtual"], ".")
        self.assertEqual(targets[0]["version"], project["version"])
        self.assertRegex(project["version"], r"^\d+\.\d+\.\d+$")

    def test_validation_runs_locked_python_and_javascript_tests(self):
        workflow = (ROOT / ".github/workflows/validate-steward.yml").read_text()
        self.assertIn("name: Validate steward", workflow)
        self.assertIn("  push:\n    branches: [main]", workflow)
        self.assertIn("  pull_request:\n    branches: [main]", workflow)
        self.assertIn("  workflow_dispatch:", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)
        self.assertIn("  tests:\n", workflow)
        self.assertIn('python-version: "3.13"', workflow)
        self.assertIn('version: "0.13.5"', workflow)
        self.assertIn('node-version: "22"', workflow)
        self.assertIn("uv sync --locked --no-build", workflow)
        self.assertIn("uv run --locked python -B -m unittest discover -p 'test_*.py'", workflow)
        self.assertIn("node --test static/*.test.mjs", workflow)
        self.assertNotIn("run: uv run validate.py", workflow)

    def test_release_requires_successful_current_main_push_validation(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("on:\n  workflow_run:\n    workflows: [Validate steward]\n    types: [completed]\n    branches: [main]", workflow)
        guard = re.search(r"    if: >-\n(.*?)\n    runs-on:", workflow, re.S)
        self.assertIsNotNone(guard)
        self.assertEqual(" ".join(guard[1].split()), " && ".join([
            "github.event.workflow_run.head_repository.full_name == github.repository",
            "github.event.workflow_run.event == 'push'",
            "github.event.workflow_run.conclusion == 'success'",
            "github.event.workflow_run.head_sha == github.sha",
        ]))
        self.assertIn("cancel-in-progress: false", workflow)
        self.assertIn("group: release-main", workflow)
        self.assertIn('test "$(gh api "repos/$GITHUB_REPOSITORY/commits/main" --jq .sha)" = "$VALIDATED_SHA"', workflow)
        self.assertNotIn("actions/checkout", workflow)

    def test_release_uses_builtin_token_and_template_action_pin(self):
        workflow = (ROOT / ".github/workflows/release.yml").read_text()
        self.assertIn("permissions:\n  contents: write\n  issues: write\n  pull-requests: write", workflow)
        self.assertIn("GH_TOKEN: ${{ github.token }}", workflow)
        self.assertIn("googleapis/release-please-action@5c625bfb5d1ff62eadeeb3772007f7f66fdcf071", workflow)
        self.assertIn("config-file: release-please-config.json", workflow)
        self.assertIn("manifest-file: .release-please-manifest.json", workflow)
        self.assertNotIn("secrets.", workflow)
        self.assertNotIn("workflow_dispatch:", workflow)
