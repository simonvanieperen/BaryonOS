"""CI-EVIDENCE: preservation must fail closed when its baseline is incomplete.

These fixtures execute the verifier and its bounded reporting simulations in
temporary Git repositories. They do not execute workflow jobs or upload data.
"""

import importlib.util
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
VERIFIER_PATH = ROOT / "docs/verification/ci-artifact-storage-20261108/verify_workflows.py"
SPEC = importlib.util.spec_from_file_location("ci_evidence_workflow_verifier", VERIFIER_PATH)
VERIFIER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(VERIFIER)


class WorkflowVerifierTests(unittest.TestCase):
    """Require real comparisons and reject workflow/collector regressions."""

    def setUp(self):
        """Copy the real workflow inputs into an isolated, disposable Git history."""
        self.temp = tempfile.TemporaryDirectory(prefix="ci-workflow-baseline-test-")
        self.addCleanup(self.temp.cleanup)
        self.repo = Path(self.temp.name)
        shutil.copytree(ROOT / ".github", self.repo / ".github")
        self.git("init", "--quiet")
        self.git("add", ".github")
        self.git("-c", "user.name=CI fixture", "-c", "user.email=fixture@example.invalid",
                 "commit", "--quiet", "-m", "Synthetic baseline for verifier host tests")
        self.baseline = self.git("rev-parse", "HEAD").strip()

    def git(self, *args):
        """Run fixed Git fixture operations without a shell or remote access."""
        return subprocess.check_output(["git", *args], cwd=self.repo, text=True,
                                       stderr=subprocess.STDOUT)

    def report(self):
        """Inspect the isolated workflow bytes against their committed baseline."""
        return VERIFIER.run(self.repo, self.baseline)

    def test_integrated_workflows_preserve_all_reporting_cases(self):
        """A valid baseline retains 18 workflow files and 23 preservation calls."""
        report = self.report()
        self.assertTrue(report["passed"], report["failed_checks"])
        self.assertEqual(report["archive_workflow_count"], 18)
        self.assertEqual(len(report["archive_workflows"]), 18)
        self.assertEqual(report["local_snapshot_baseline"], self.baseline)
        self.assertEqual(report["repository_path"], ".")
        self.assertTrue(all(comparison["status"] == "compared"
                            and comparison["remaining_configuration_preserved"]
                            for comparison in report["baseline_comparisons"].values()))
        for prefix in ("preservation-invocation:", "existing-preservation-step-unchanged:"):
            # Experimental SMP adds one call. KVM adds one workflow/call, while
            # H05 retains one workflow with distinct S5 and POWER-system calls.
            # Code coverage reporting adds three calls in ci.yml (Rust, Python,
            # JavaScript), each counted by both prefixes.
            self.assertEqual(sum(check["name"].startswith(prefix)
                                 for check in report["checks"]), 23)
        self.assertEqual(sum(check["name"].startswith("report-shell:")
                             for check in report["checks"]), 28)
        self.assertEqual(sum(check["name"].startswith("package-check:")
                             for check in report["checks"]), 6)

    def test_new_workflow_without_baseline_is_not_reported_as_preserved(self):
        """A newly added workflow cannot inherit an absent comparison as a pass."""
        path = ".github/workflows/new-workflow.yml"
        shutil.copyfile(self.repo / ".github/workflows/copilot-setup-steps.yml", self.repo / path)
        report = self.report()
        self.assertFalse(report["passed"])
        self.assertIn("workflow-inventory-preserved", report["failed_checks"])
        self.assertIn("original-tests-runners-gates-preserved:" + path, report["failed_checks"])
        self.assertEqual(report["baseline_comparisons"][path]["status"], "not-compared")

    def test_deleted_workflow_is_not_silently_ignored(self):
        """Comparing only surviving files must not hide deletion of a CI job."""
        (self.repo / ".github/workflows/copilot-setup-steps.yml").unlink()
        report = self.report()
        self.assertFalse(report["passed"])
        inventory = next(check for check in report["checks"]
                         if check["name"] == "workflow-inventory-preserved")
        self.assertIn(".github/workflows/copilot-setup-steps.yml", inventory["removed"])
        self.assertEqual(report["baseline_comparisons"][".github/workflows/copilot-setup-steps.yml"]["status"],
                         "missing-from-checkout")

    def test_runner_change_is_not_hidden_by_evidence_normalization(self):
        """The artifact comparison does not authorize a change back to self-hosting."""
        path = self.repo / ".github/workflows/ci.yml"
        text = path.read_text()
        self.assertIn("runs-on: ubuntu-24.04", text)
        path.write_text(text.replace("runs-on: ubuntu-24.04", "runs-on: self-hosted", 1))
        report = self.report()
        self.assertFalse(report["passed"])
        self.assertIn("original-tests-runners-gates-preserved:.github/workflows/ci.yml",
                      report["failed_checks"])

    def test_collector_error_cannot_become_optional(self):
        """Only upload failures may be tolerated; collection remains required."""
        path = self.repo / ".github/actions/preserve-evidence/action.yml"
        text = path.read_text()
        self.assertIn("      id: collect\n", text)
        path.write_text(text.replace("      id: collect\n",
                                     "      id: collect\n      continue-on-error: true\n", 1))
        report = self.report()
        self.assertFalse(report["passed"])
        self.assertIn("only-uploads-continue-on-error", report["failed_checks"])

    def test_default_missing_evidence_policy_cannot_be_weakened(self):
        """Already migrated calls still enforce the action's default error policy."""
        path = self.repo / ".github/actions/preserve-evidence/action.yml"
        text = path.read_text()
        self.assertIn("    default: 'error'\n", text)
        path.write_text(text.replace("    default: 'error'\n", "    default: 'warn'\n", 1))
        report = self.report()
        self.assertFalse(report["passed"])
        self.assertIn("default-required-evidence-policy", report["failed_checks"])

    def test_migrated_evidence_selection_must_remain_unchanged(self):
        """Removing already migrated action steps must not hide changed selections."""
        path = self.repo / ".github/workflows/ci.yml"
        text = path.read_text()
        self.assertIn("            build/ci-toolchain/emulator.txt\n", text)
        path.write_text(text.replace("            build/ci-toolchain/emulator.txt\n", "", 1))
        report = self.report()
        self.assertFalse(report["passed"])
        self.assertIn("preservation-calls-unchanged:.github/workflows/ci.yml",
                      report["failed_checks"])

    def test_invalid_baseline_writes_failed_report_and_exits_nonzero(self):
        """A missing ref yields inspectable failure evidence instead of a traceback."""
        output = self.repo / "failed-report.json"
        result = subprocess.run(
            [sys.executable, "-B", str(VERIFIER_PATH), "--repo", str(self.repo),
             "--baseline", "missing-baseline-ref", "--output", str(output)],
            text=True, capture_output=True, check=False,
        )
        self.assertEqual(result.returncode, 1, result.stderr)
        report = json.loads(output.read_text())
        self.assertFalse(report["passed"])
        self.assertIsNone(report["local_snapshot_baseline"])
        self.assertIn("baseline-resolves-to-commit", report["failed_checks"])
        self.assertNotIn("Traceback", result.stderr)


if __name__ == "__main__":
    unittest.main()
