"""CI-HOSTED: guard public-runner isolation and mandatory workflow coverage.

These checks inspect the checked-in configuration. The supply-chain fixture
executes one workflow shell fragment against isolated local fakes; it does not
execute GitHub's expression engine, download from the network, or provide
native QEMU acceptance.
"""

import hashlib
import io
import os
from pathlib import Path
import re
import shlex
import subprocess
import tarfile
import tempfile
import tomllib
import unicodedata
import unittest

import yaml


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ACTION = ".github/actions/preserve-evidence/action.yml"
CACHE_ACTION_VERSION = "v6.1.0"
CACHE_ACTION_SHA = "55cc8345863c7cc4c66a329aec7e433d2d1c52a9"
ACTIONLINT_VERSION = "1.7.12"
ACTIONLINT_SHA256 = "8aca8db96f1b94770f1b0d72b6dddcb1ebb8123cb3712530b08cc387b349a3d8"
ACTIONLINT_TAG_COMMIT = "914e7df21a07ef503a81201c76d2b11c789d3fca"
# Non-required workflows skip only documentation and project metadata. The
# required ci.yml gates stay unfiltered (see test_required_gates_...).
METADATA_PATHS_IGNORE = [
    "docs/**",
    "**.md",
    ".github/ISSUE_TEMPLATE/**",
    ".github/DISCUSSION_TEMPLATE/**",
    ".github/workflows/project-classification.yml",
    "tools/project_classification.py",
    "tests/test_project_classification.py",
]


def github_path_filter_matches(pattern, path):
    """Match GitHub path-filter globs: '*' stays within a segment, '**' spans."""
    regex, i = "", 0
    while i < len(pattern):
        if pattern.startswith("**", i):
            regex += ".*"
            i += 2
        elif pattern[i] == "*":
            regex += "[^/]*"
            i += 1
        else:
            regex += re.escape(pattern[i])
            i += 1
    return re.fullmatch(regex, path) is not None


def uses_reference_is_pinned(reference):
    """Accept immutable external references and checkout-contained local actions."""
    if not isinstance(reference, str) or not reference:
        return False
    if reference.startswith("./"):
        relative = reference[2:]
        if not relative or "\\" in relative or "@" in relative:
            return False
        path = Path(relative)
        if path.is_absolute() or ".." in path.parts:
            return False
        resolved = (ROOT / path).resolve()
        return resolved.is_relative_to(ROOT.resolve()) and resolved.exists()
    if reference.startswith("docker://"):
        return re.fullmatch(
            r"docker://[^\s@]+@sha256:[0-9a-f]{64}", reference
        ) is not None
    source, separator, revision = reference.rpartition("@")
    if not separator or re.fullmatch(r"[0-9a-f]{40}", revision) is None:
        return False
    parts = source.split("/")
    return len(parts) >= 2 and all(
        part not in {"", ".", ".."}
        and re.fullmatch(r"[A-Za-z0-9_.-]+", part) is not None
        for part in parts
    )


MILESTONE_DOCUMENT = ROOT / "docs/GITHUB-MILESTONES.md"
ROADMAP_DOCUMENT = ROOT / "docs/ROADMAP.md"
CANONICAL_MILESTONE_TITLES = (
    "M6 — Storage and Recovery",
    "M7 — Native Product Integration",
    "M8 — Networking and Security Hardening",
    "M9 — First Reference PC",
    "M10 — Second Architecture",
    "M11 — Experimental Community Release",
)
MILESTONE_FIELDS = (
    "Required outcome",
    "Acceptance evidence",
    "Decision gate",
    "Canonical sources",
)
CANONICAL_MILESTONE_LINKS = (
    "https://github.com/simonvanieperen/BaryonOS/blob/main/"
    "docs/ROADMAP.md#technical-milestones",
    "https://github.com/simonvanieperen/BaryonOS/blob/main/docs/PROGRESS.md",
)
LEGACY_MILESTONE_DESTINATIONS = {
    "K06 — Multicore and process isolation": "M7",
    "B02 / S09 — Encrypted storage and backups": "M6",
    "U02–U06 — A native desktop for everyday use": "M7",
    "N02–N04 — Internet, TLS and network permissions": "M8",
    "A02–A04 — Installing apps and using them daily": "M7",
    "P01–P04 — NAS, synchronisation and multiple devices": "M8",
    "L01 — Local system AI": "M7",
    "H02–H06 — Hardware, drivers and power": "M9",
    "B04–B06 — Chain of trust and security review": "M8",
    "R01–R03 — Full test release and maintenance": "M11",
}


class GitHubMilestoneDocumentContractTests(unittest.TestCase):
    """Validate checked-in governance, not the live GitHub metadata state."""

    @classmethod
    def setUpClass(cls):
        """Decode the actual tracked bytes and load the canonical roadmap."""
        cls.raw = MILESTONE_DOCUMENT.read_bytes()
        cls.text = cls.raw.decode("utf-8", errors="strict")
        cls.roadmap = ROADMAP_DOCUMENT.read_text(encoding="utf-8")

    def milestone_section(self, title):
        """Return one exact milestone body without including later sections."""
        heading = f"## {title}\n"
        self.assertEqual(self.text.count(heading), 1, title)
        body = self.text.split(heading, 1)[1]
        return body.split("\n## ", 1)[0]

    def test_document_is_normalized_utf8_without_mojibake(self):
        """Copy-ready titles must retain their intended Unicode punctuation."""
        self.assertFalse(self.raw.startswith(b"\xef\xbb\xbf"), "unexpected UTF-8 BOM")
        self.assertEqual(self.text, unicodedata.normalize("NFC", self.text))
        for marker in ("\ufffd", "Ã", "Â", "â€"):
            with self.subTest(marker=marker):
                self.assertNotIn(marker, self.text)

    def test_exact_titles_match_the_canonical_roadmap(self):
        """Keep one ordered M6–M11 title family in both active documents."""
        titles = re.findall(r"^## (M(?:6|7|8|9|10|11)\b[^\n]*)$", self.text, re.MULTILINE)
        self.assertEqual(titles, list(CANONICAL_MILESTONE_TITLES))
        for title in CANONICAL_MILESTONE_TITLES:
            with self.subTest(title=title):
                self.assertEqual(self.roadmap.count(f"**{title}**"), 1)

    def test_each_description_has_four_fields_and_both_sources(self):
        """Every copyable description keeps the complete governance contract."""
        for title in CANONICAL_MILESTONE_TITLES:
            section = self.milestone_section(title)
            fields = re.findall(r"^\*\*([^*:\n]+):\*\*", section, re.MULTILINE)
            with self.subTest(title=title):
                self.assertEqual(fields, list(MILESTONE_FIELDS))
                for link in CANONICAL_MILESTONE_LINKS:
                    self.assertEqual(section.count(link), 1, link)

                roadmap_row = re.search(
                    rf"^\| \*\*{re.escape(title)}\*\* \| ([^|]+) \| ([^|]+) \| ([^|]+) \|$",
                    self.roadmap,
                    re.MULTILINE,
                )
                self.assertIsNotNone(roadmap_row)
                for field, expected in zip(MILESTONE_FIELDS[:3], roadmap_row.groups()):
                    value = re.search(
                        rf"^\*\*{re.escape(field)}:\*\*\s*(.*?)(?=^\*\*|\Z)",
                        section,
                        re.MULTILINE | re.DOTALL,
                    )
                    self.assertIsNotNone(value)
                    self.assertEqual(
                        " ".join(value.group(1).split()),
                        " ".join(expected.split()),
                        field,
                    )

    def test_legacy_objects_have_one_closing_migration_route(self):
        """Ten rubric objects map once, close after migration, and retain history."""
        rows = re.findall(
            r"^\| `([^`]+)` \| (M(?:6|7|8|9|10|11)) \|",
            self.text,
            re.MULTILINE,
        )
        self.assertEqual(len(rows), len(LEGACY_MILESTONE_DESTINATIONS))
        self.assertEqual(dict(rows), LEGACY_MILESTONE_DESTINATIONS)

        compact = " ".join(self.text.split())
        for invariant in (
            "Re-query every issue assigned to a legacy object",
            "at most one primary GitHub Milestone",
            "close rather than delete all ten legacy objects",
            "descriptions and closed history remain available",
            "no parallel active taxonomy remains",
        ):
            with self.subTest(invariant=invariant):
                self.assertIn(invariant, compact)

    def test_accepted_criteria_are_not_presented_as_unfinished(self):
        """Assignments #39 and #41 cover only their current residual scope."""
        rows = {
            number: (destination.strip(), scope.strip())
            for number, destination, scope in re.findall(
                r"^\| \[#(39|41)\]\([^)]*\)[^|]*\| ([^|]+) \| ([^|]+) \|$",
                self.text,
                re.MULTILINE,
            )
        }
        self.assertEqual(set(rows), {"39", "41"})
        self.assertTrue(rows["39"][0].startswith("M8"))
        self.assertIn("N01 is accepted", rows["39"][1])
        self.assertTrue(rows["41"][0].startswith("M8"))
        self.assertIn("B03 is accepted", rows["41"][1])


class UniqueKeyLoader(yaml.BaseLoader):
    """Keep `on` and boolean scalars as text and reject overwritten YAML keys."""

    def construct_mapping(self, node, deep=False):
        """Fail instead of silently accepting a duplicate workflow setting."""
        result = {}
        for key_node, value_node in node.value:
            key = self.construct_object(key_node, deep=deep)
            if key in result:
                raise yaml.constructor.ConstructorError(
                    None, None, f"duplicate YAML key: {key}", key_node.start_mark,
                )
            result[key] = self.construct_object(value_node, deep=deep)
        return result


class DependabotContractTests(unittest.TestCase):
    """Cover independent Cargo workspaces without multiplying update PRs."""

    def setUp(self):
        self.config = yaml.load(
            (ROOT / ".github/dependabot.yml").read_text(encoding="utf-8"),
            Loader=UniqueKeyLoader,
        )

    def test_each_owned_cargo_workspace_is_covered_once(self):
        """Find workspace boundaries, excluding members and vendored packages."""
        manifests = subprocess.check_output(
            ["git", "ls-files", "-z", "--", "Cargo.toml", "**/Cargo.toml"],
            cwd=ROOT,
        ).decode().split("\0")
        expected = set()
        for manifest in filter(None, manifests):
            data = tomllib.loads((ROOT / manifest).read_text(encoding="utf-8"))
            if "workspace" in data:
                directory = Path(manifest).parent.as_posix()
                expected.add("/" if directory == "." else "/" + directory)
        self.assertTrue(expected)
        configured = []
        for update in self.config["updates"]:
            if update["package-ecosystem"] == "cargo":
                self.assertNotEqual("directory" in update, "directories" in update)
                configured.extend(
                    update["directories"] if "directories" in update
                    else [update["directory"]]
                )
        self.assertEqual(len(configured), len(set(configured)), "duplicate workspace")
        self.assertEqual(set(configured), expected)

    def test_multi_directory_updates_are_monthly_and_grouped(self):
        """Keep same-dependency updates together across independent roots."""
        for update in self.config["updates"]:
            if update["package-ecosystem"] != "cargo" or "directories" not in update:
                continue
            with self.subTest(directories=update["directories"]):
                self.assertEqual(update["schedule"]["interval"], "monthly")
                self.assertEqual(update["open-pull-requests-limit"], "2")
                self.assertEqual(update["groups"], {
                    "cargo-independent": {
                        "patterns": ["*"], "group-by": "dependency-name",
                    },
                })


class WorkflowContractTests(unittest.TestCase):
    """Detect runner, credential, gate and deduplication regressions."""

    @classmethod
    def setUpClass(cls):
        """Read the actual workflows and local composite actions once per run."""
        cls.workflows = {}
        cls.actions = {}
        for directory, pattern, destination in [
            (ROOT / ".github/workflows", "*.y*ml", cls.workflows),
            (ROOT / ".github/actions", "**/action.y*ml", cls.actions),
        ]:
            for path in sorted(directory.glob(pattern)):
                destination[path.relative_to(ROOT).as_posix()] = yaml.load(
                    path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader,
                )

    def jobs(self):
        """Yield every job, including manual and private-only maintenance jobs."""
        for path, workflow in self.workflows.items():
            for job_id, job in workflow["jobs"].items():
                yield path, job_id, job

    def steps(self):
        """Include nested local-action steps in supply-chain and error checks."""
        for path, job_id, job in self.jobs():
            for step in job.get("steps", []):
                yield path, job_id, step
        for path, action in self.actions.items():
            for step in action.get("runs", {}).get("steps", []):
                yield path, "composite", step

    def uses_references(self):
        """Yield job, workflow-step and composite-action executable references."""
        for path, job_id, job in self.jobs():
            self.assertIsInstance(
                job, dict, f"{path} job {job_id} must be a mapping"
            )
            if "uses" in job:
                yield path, f"job:{job_id}", job["uses"]
            steps = job.get("steps", [])
            self.assertIsInstance(
                steps, list, f"{path} job {job_id} steps must be a list"
            )
            for index, step in enumerate(steps):
                self.assertIsInstance(
                    step, dict, f"{path} job {job_id} step {index} must be a mapping"
                )
                if "uses" in step:
                    yield path, f"job:{job_id}:step:{index}", step["uses"]
        for path, action in self.actions.items():
            runs = action.get("runs", {})
            self.assertIsInstance(runs, dict, f"{path} runs must be a mapping")
            steps = runs.get("steps", [])
            self.assertIsInstance(steps, list, f"{path} composite steps must be a list")
            for index, step in enumerate(steps):
                self.assertIsInstance(
                    step, dict, f"{path} composite step {index} must be a mapping"
                )
                if "uses" in step:
                    yield path, f"composite:step:{index}", step["uses"]

    def test_all_jobs_use_standard_hosted_ubuntu(self):
        """No custom label, dynamic selector or persistent runner can return."""
        # ubuntu-26.04 is a standard hosted image; the K06 matrix pins QEMU 10.2.1 there.
        self.assertTrue(self.workflows)
        for path, job_id, job in self.jobs():
            with self.subTest(path=path, job=job_id):
                self.assertIn(job.get("runs-on"), ("ubuntu-24.04", "ubuntu-26.04"))

    def test_kvm_pilot_is_manual_hosted_and_cannot_replace_tcg_acceptance(self):
        """Keep KVM opt-in, fail-closed, narrow, and outside required checks."""
        path = ".github/workflows/kvm-pilot.yml"
        workflow = self.workflows[path]
        self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})
        self.assertEqual(workflow["permissions"], {"contents": "read"})
        self.assertEqual(set(workflow["jobs"]), {"kvm-pilot"})
        job = workflow["jobs"]["kvm-pilot"]
        self.assertEqual(job["runs-on"], "ubuntu-24.04")
        self.assertEqual(job["env"]["NOS_QEMU_ACCEL"], "kvm")
        self.assertEqual(job["strategy"]["matrix"]["gate"], ["system", "volume", "window"])

        report_steps = [
            step for step in job["steps"]
            if step.get("name") == "Require passing reports bound to KVM"
        ]
        self.assertEqual(len(report_steps), 1)
        self.assertEqual(report_steps[0].get("if"), "${{ always() }}")

        commands = "\n".join(step.get("run", "") for step in job["steps"])
        for required in (
            "test -c /dev/kvm", "test -r /dev/kvm", "test -w /dev/kvm",
            "qemu-system-x86_64 -accel help", "tools/test_system.py",
            "tools/test_volume.py", "native-window-session-probe",
            "tools/run_window_session.py", 'acceleration != "kvm"',
        ):
            self.assertIn(required, commands)
        for excluded in (
            "tools/test_net_system.py", "tools/test_tcp_system.py",
            "tools/run_smp.py", "tools/test_memory_system.py",
        ):
            self.assertNotIn(excluded, commands)

        for other_path in self.workflows:
            if other_path == path:
                continue
            with self.subTest(path=other_path):
                self.assertNotIn(
                    "NOS_QEMU_ACCEL",
                    (ROOT / other_path).read_text(encoding="utf-8"),
                )

    def test_public_prs_keep_minimal_token_permissions(self):
        """Allow narrowly scoped writes only for CodeQL and orphan-run cleanup."""
        for path, workflow in self.workflows.items():
            with self.subTest(path=path):
                self.assertNotIn("pull_request_target", workflow["on"])
                permissions = workflow.get("permissions")
                self.assertIsInstance(permissions, dict)
                self.assertEqual(permissions.get("contents"), "read")
                self.assertTrue(set(permissions.values()) <= {"read", "none"})

        for path, job_id, job in self.jobs():
            with self.subTest(path=path, job=job_id):
                permissions = job.get("permissions", {})
                self.assertIsInstance(permissions, dict)

                if (path, job_id) == (".github/workflows/codeql.yml", "analyze"):
                    self.assertEqual(
                        permissions,
                        {
                            "actions": "read",
                            "contents": "read",
                            "security-events": "write",
                        },
                    )
                elif (path, job_id) == (
                    ".github/workflows/clear-stale-actions.yml", "cancel-orphans"
                ):
                    self.assertEqual(permissions, {"actions": "write"})
                else:
                    self.assertTrue(
                        set(permissions.values()) <= {"read", "none"}
                    )

    def test_external_actions_are_pinned_to_full_commits(self):
        """All executable references are immutable or safe checkout-local paths."""
        references = list(self.uses_references())
        self.assertTrue(references, "no executable Actions references found")
        for path, scope, reference in references:
            with self.subTest(path=path, scope=scope, uses=reference):
                self.assertTrue(
                    uses_reference_is_pinned(reference),
                    f"mutable, invalid or checkout-escaping uses reference: {reference!r}",
                )

        fixtures = {
            "actions/checkout@" + "a" * 40: True,
            "owner/repository/.github/workflows/reuse.yml@" + "b" * 40: True,
            "./.github/actions/setup-python": True,
            "docker://ghcr.io/example/tool@sha256:" + "c" * 64: True,
            "actions/checkout@v7": False,
            "https://github.com/actions/checkout@" + "d" * 40: False,
            "owner/repository/../reuse.yml@" + "e" * 40: False,
            "./../outside": False,
            "../outside": False,
            "docker://ghcr.io/example/tool:latest": False,
            "docker://ghcr.io/example/tool@sha256:short": False,
        }
        for reference, expected in fixtures.items():
            with self.subTest(fixture=reference):
                self.assertEqual(uses_reference_is_pinned(reference), expected)

    def test_actionlint_is_pinned_in_required_host_gate(self):
        """Workflow validation is required, checksum-pinned and narrowly scoped."""
        workflow = self.workflows[".github/workflows/ci.yml"]
        steps = workflow["jobs"]["host-quality"]["steps"]
        matches = [
            (index, step)
            for index, step in enumerate(steps)
            if step.get("name") == f"Validate workflows with actionlint {ACTIONLINT_VERSION}"
        ]
        self.assertEqual(len(matches), 1)
        index, step = matches[0]
        checkout = next(
            position
            for position, candidate in enumerate(steps)
            if candidate.get("name") == "Checkout"
        )
        self.assertEqual(index, checkout + 1)
        self.assertNotIn("if", step)
        self.assertEqual(step.get("continue-on-error", "false"), "false")
        self.assertEqual(step.get("shell"), "bash")
        self.assertEqual(
            step.get("env"),
            {
                "ACTIONLINT_VERSION": ACTIONLINT_VERSION,
                "ACTIONLINT_SHA256": ACTIONLINT_SHA256,
            },
        )
        command = step["run"]
        self.assertIn(
            "https://github.com/rhysd/actionlint/releases/download/"
            "v${ACTIONLINT_VERSION}/actionlint_${ACTIONLINT_VERSION}_linux_amd64.tar.gz",
            command,
        )
        self.assertNotIn("|| true", command)
        checksum = command.index("sha256sum --check --strict")
        extraction = command.index("tar --extract")
        self.assertLess(checksum, extraction)
        self.assertIn('${ACTIONLINT_SHA256}', command[:checksum])
        self.assertIn('${actionlint_archive}', command[:checksum])
        self.assertIn('${actionlint_archive}', command[extraction:])
        self.assertRegex(
            command,
            r'tar[^\n]*--extract[^\n]*\\\n[^\n]*--directory "\$\{actionlint_dir\}" actionlint',
        )
        self.assertIn(
            '"${actionlint_dir}/actionlint" -shellcheck= -pyflakes=',
            [line.strip() for line in command.splitlines()],
        )

        policy = (ROOT / "docs/CI-EVIDENCE.md").read_text(encoding="utf-8")
        section_match = re.search(
            r"^## Workflow syntax validation\n(?P<section>.*?)(?=^## )",
            policy,
            re.MULTILINE | re.DOTALL,
        )
        self.assertIsNotNone(section_match)
        section = section_match.group("section")
        for fact in (
            f"actionlint v{ACTIONLINT_VERSION}",
            ACTIONLINT_SHA256,
            ACTIONLINT_TAG_COMMIT,
            "unsigned",
        ):
            self.assertIn(fact, section)

    def test_actionlint_step_fails_closed(self):
        """The verified archive and linter result are both mandatory (CI-HOSTED)."""
        workflow = self.workflows[".github/workflows/ci.yml"]
        expected_name = f"Validate workflows with actionlint {ACTIONLINT_VERSION}"
        step = next(
            candidate
            for candidate in workflow["jobs"]["host-quality"]["steps"]
            if candidate.get("name") == expected_name
        )

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            archive_path = root / "actionlint-fixture.tar.gz"
            actionlint = b'#!/usr/bin/env bash\nexit "${FAKE_ACTIONLINT_EXIT:-0}"\n'
            with tarfile.open(archive_path, "w:gz") as archive:
                entry = tarfile.TarInfo("actionlint")
                entry.mode = 0o755
                entry.size = len(actionlint)
                archive.addfile(entry, io.BytesIO(actionlint))

            fake_bin = root / "bin"
            fake_bin.mkdir()
            fake_curl = fake_bin / "curl"
            fake_curl.write_text(
                """#!/usr/bin/env bash
set -euo pipefail
output=''
while (( $# )); do
  case "$1" in
    --output) output="$2"; shift 2 ;;
    *) shift ;;
  esac
done
test -n "$output"
cp -- "$ACTIONLINT_FIXTURE" "$output"
""",
                encoding="utf-8",
            )
            fake_curl.chmod(0o755)
            expected_hash = hashlib.sha256(archive_path.read_bytes()).hexdigest()

            def run(label, checksum, actionlint_exit):
                runner_temp = root / label
                runner_temp.mkdir()
                environment = os.environ.copy()
                environment.update(
                    {
                        "PATH": f"{fake_bin}{os.pathsep}{environment['PATH']}",
                        "RUNNER_TEMP": str(runner_temp),
                        "ACTIONLINT_VERSION": ACTIONLINT_VERSION,
                        "ACTIONLINT_SHA256": checksum,
                        "ACTIONLINT_FIXTURE": str(archive_path),
                        "FAKE_ACTIONLINT_EXIT": str(actionlint_exit),
                    }
                )
                return subprocess.run(
                    ["bash", "-c", step["run"]],
                    cwd=ROOT,
                    env=environment,
                    capture_output=True,
                    text=True,
                    check=False,
                )

            self.assertEqual(run("success", expected_hash, 0).returncode, 0)

            checksum_failure = run("bad-checksum", "0" * 64, 0)
            self.assertNotEqual(checksum_failure.returncode, 0)
            self.assertFalse(
                (root / "bad-checksum" / f"actionlint-{ACTIONLINT_VERSION}").exists()
            )

            actionlint_failure = run("bad-actionlint", expected_hash, 23)
            self.assertEqual(actionlint_failure.returncode, 23)

    def test_cache_action_matches_documented_provenance(self):
        """Every cache use must match its reviewed pin, version and policy source."""
        references = [
            (path, job_id, step["uses"])
            for path, job_id, step in self.steps()
            if re.fullmatch(
                r"actions/cache(?:/(?:restore|save))?@[0-9a-f]{40}",
                step.get("uses", ""),
            )
        ]
        self.assertTrue(references, "no actions/cache use found")
        for path, job_id, reference in references:
            with self.subTest(path=path, job=job_id):
                self.assertEqual(reference.rsplit("@", 1)[1], CACHE_ACTION_SHA)

        labelled_reference = re.compile(
            rf"^\s*uses:\s*actions/cache(?:/(?:restore|save))?@"
            rf"{re.escape(CACHE_ACTION_SHA)}\s+"
            rf"#\s*{re.escape(CACHE_ACTION_VERSION)}\s*$",
            re.MULTILINE,
        )
        labelled_uses = sum(
            len(labelled_reference.findall((ROOT / path).read_text(encoding="utf-8")))
            for path in self.workflows
        )
        self.assertEqual(labelled_uses, len(references))

        policy = (ROOT / "CODEX-WORKFLOW.md").read_text(encoding="utf-8")
        self.assertIn(f"reviewed {CACHE_ACTION_VERSION} commit", policy)
        self.assertIn(
            f"*actions/cache*, version {CACHE_ACTION_VERSION.removeprefix('v')}.",
            policy,
        )
        self.assertIn(f"`{CACHE_ACTION_SHA}`", policy)
        self.assertIn(
            f"https://github.com/actions/cache/tree/{CACHE_ACTION_SHA}",
            policy,
        )

    def test_checkout_does_not_persist_credentials(self):
        """Builds and public PR scripts do not inherit checkout credentials."""
        for path, job_id, step in self.steps():
            if step.get("uses", "").startswith("actions/checkout@"):
                with self.subTest(path=path, job=job_id):
                    self.assertEqual(step.get("with", {}).get("persist-credentials"), "false")

    def test_required_gates_are_unfiltered_and_independent(self):
        """Required check names always exist and run without a serial dependency."""
        workflow = self.workflows[".github/workflows/ci.yml"]
        for event in ("pull_request", "push"):
            trigger = workflow["on"][event]
            with self.subTest(event=event):
                self.assertNotIn("paths", trigger)
                self.assertNotIn("paths-ignore", trigger)
        self.assertIn("main", workflow["on"]["push"]["branches"])
        for job_id in ("host-quality", "qemu-smoke"):
            job = workflow["jobs"][job_id]
            with self.subTest(job=job_id):
                self.assertEqual(job.get("name", job_id), job_id)
                self.assertNotIn("if", job)
                self.assertFalse(job.get("needs"))
                self.assertEqual(job.get("continue-on-error", "false"), "false")
                self.assertTrue(any("run" in step for step in job["steps"]))

    def test_paths_ignore_skips_only_documentation_and_project_metadata(self):
        """Metadata-only changes must not start native matrices; code still must."""
        filtered = 0
        for path, workflow in self.workflows.items():
            for event in ("pull_request", "push"):
                trigger = workflow["on"].get(event)
                if isinstance(trigger, dict) and "paths-ignore" in trigger:
                    filtered += 1
                    with self.subTest(path=path, event=event):
                        self.assertEqual(trigger["paths-ignore"], METADATA_PATHS_IGNORE)
        self.assertGreater(filtered, 0)

        def ignored(changed):
            return any(github_path_filter_matches(p, changed)
                       for p in METADATA_PATHS_IGNORE)

        for changed in ("README.md", "docs/PROJECT-STATE.md", "sdk/README.md",
                        ".github/pull_request_template.md",
                        ".github/ISSUE_TEMPLATE/bug.yml",
                        "tools/project_classification.py"):
            with self.subTest(ignored=changed):
                self.assertTrue(ignored(changed))
        for changed in ("kernel/src/main.rs", "Cargo.lock", "tools/build.py",
                        "tools/ci_evidence.py", "tests/test_ci_workflows.py",
                        ".github/workflows/ci.yml",
                        ".github/workflows/native-smp.yml",
                        ".github/actions/setup-qemu/action.yml",
                        "sdk/examples/window-session/src/main.rs",
                        "docs.rs", "tools/project_classification.py.orig"):
            with self.subTest(built=changed):
                self.assertFalse(ignored(changed))

    def test_merge_hold_is_an_unfiltered_live_read_required_gate(self):
        """The hold must always report, read live state and never be skipped."""
        path = ".github/workflows/merge-hold.yml"
        workflow = self.workflows[path]
        trigger = workflow["on"]["pull_request"]
        self.assertEqual(set(workflow["on"]), {"pull_request"})
        self.assertEqual(
            set(trigger["types"]),
            {"opened", "synchronize", "reopened", "labeled", "unlabeled"},
        )
        for key in ("paths", "paths-ignore", "branches", "branches-ignore"):
            self.assertNotIn(key, trigger)
        self.assertNotIn("defaults", workflow)
        self.assertEqual(list(workflow["jobs"]), ["merge-hold"])
        job = workflow["jobs"]["merge-hold"]
        self.assertEqual(job["name"], "merge-hold")
        self.assertEqual(
            job["permissions"],
            {"contents": "read", "issues": "read", "pull-requests": "read"},
        )
        for key in ("if", "needs", "continue-on-error", "strategy", "defaults",
                    "container", "services"):
            self.assertNotIn(key, job)
        checkout, decide = job["steps"]
        self.assertTrue(checkout["uses"].startswith("actions/checkout@"))
        self.assertEqual(checkout["with"], {"persist-credentials": "false"})
        for step in (checkout, decide):
            for key in ("if", "continue-on-error", "working-directory"):
                self.assertNotIn(key, step)
        self.assertNotIn("uses", decide)
        self.assertEqual(decide["shell"], "bash")
        self.assertEqual(decide["run"].strip(), "python3 -B tools/merge_hold.py")
        self.assertEqual(decide["env"], {
            "GH_TOKEN": "${{ github.token }}",
            "REPO": "${{ github.repository }}",
            "PR_NUMBER": "${{ github.event.pull_request.number }}",
            "HEAD_SHA": "${{ github.event.pull_request.head.sha }}",
        })

    def test_only_artifact_uploads_can_tolerate_errors(self):
        """Storage failure may be optional; failed builds, tests and collectors are not."""
        for path, job_id, job in self.jobs():
            with self.subTest(path=path, job=job_id):
                self.assertEqual(job.get("continue-on-error", "false"), "false")
        for path, job_id, step in self.steps():
            if step.get("continue-on-error", "false") != "false":
                with self.subTest(path=path, job=job_id, step=step.get("name")):
                    self.assertEqual(step["continue-on-error"], "true")
                    self.assertEqual(path, EVIDENCE_ACTION)
                    self.assertTrue(step.get("uses", "").startswith("actions/upload-artifact@"))

    def test_window_matrix_requires_package_only_for_scale_one(self):
        """Scale two must retain evidence without requiring or colliding on a scale-one bundle."""
        workflow = self.workflows[".github/workflows/native-window-session.yml"]
        job = workflow["jobs"]["native-window-session"]
        preserve = next(
            step for step in job["steps"]
            if step.get("uses") == "./.github/actions/preserve-evidence"
        )
        inputs = preserve["with"]
        self.assertEqual(
            inputs["package-path"],
            "${{ matrix.scale == 1 && "
            "'build/window-session-ci/evidence/NieuwOS-Venstersessie-Windows-QEMU.zip' || '' }}",
        )
        self.assertIn("${{ matrix.scale }}", inputs["name"])

        package = next(
            step for step in job["steps"]
            if step.get("name") == "Package the reviewable Windows QEMU bundle"
        )
        self.assertIn("matrix.scale == 1", package["if"])

    def test_pr_lifecycle_runs_once_without_skipping_drafts(self):
        """Draft changes are tested already, so becoming ready need not repeat them."""
        for path, workflow in self.workflows.items():
            if "pull_request" not in workflow["on"]:
                continue
            trigger = workflow["on"]["pull_request"] or {}
            types = trigger.get("types", ["opened", "synchronize", "reopened"])
            with self.subTest(path=path):
                self.assertTrue({"opened", "synchronize", "reopened"} <= set(types))
                self.assertNotIn("ready_for_review", types)
                for job in workflow["jobs"].values():
                    self.assertNotIn("draft", job.get("if", ""))

    def test_deduplication_keeps_host_and_scalar_component_coverage(self):
        """Both removed matrix entries retain tests, lint and scalar target builds."""
        matrix = self.workflows[".github/workflows/component-leaves.yml"]["jobs"][
            "component-quality"
        ]["strategy"]["matrix"]["include"]
        self.assertTrue({"artifact-store", "materiaal-ui"}.isdisjoint(
            entry["component"] for entry in matrix
        ))
        for filename, job_id, component in [
            ("artifact-store-quality.yml", "artifact-store-core", "artifact-store-core"),
            ("native-display-input.yml", "native-display-input", "ui/native/Cargo.toml"),
        ]:
            job = self.workflows[f".github/workflows/{filename}"]["jobs"][job_id]
            relevant = [step for step in job["steps"] if component in step.get("run", "")]
            commands = "\n".join(step["run"] for step in relevant)
            with self.subTest(component=component):
                for operation in ("test", "clippy", "fmt"):
                    self.assertRegex(commands, rf"\bcargo\b[^\n]*\b{operation}\b")
                scalar = [step for step in relevant if re.search(
                    r"\bcargo\b[^\n]*\bbuild\b", step["run"],
                ) and "x86_64-unknown-none" in step["run"]]
                self.assertTrue(scalar, "missing freestanding component build")
                for step in scalar:
                    flags = {**job.get("env", {}), **step.get("env", {})}.get("RUSTFLAGS", "")
                    if filename == "artifact-store-quality.yml":
                        args = shlex.split(step["run"])
                        extra = tomllib.loads(args[args.index("--config") + 1])
                        target = "x86_64-unknown-none"
                        base = tomllib.loads((ROOT / ".cargo/config.toml").read_text())
                        flags = " ".join(base["target"][target]["rustflags"] +
                                         extra["target"][target]["rustflags"])
                    self.assertIn("no-redzone=yes", flags)
                    self.assertIn("-sse2", flags)
                    self.assertIn("-avx2", flags)

    def test_artifact_build_preserves_target_rustflags(self):
        """Scalar CI additions must merge with the mandatory target contract."""
        workflow = self.workflows[".github/workflows/artifact-store-quality.yml"]
        job = workflow["jobs"]["artifact-store-core"]
        step = next(s for s in job["steps"] if s.get("name") == "Freestanding library build")
        for scope in (workflow, job, step):
            env = scope.get("env", {})
            for key in ("RUSTFLAGS", "CARGO_ENCODED_RUSTFLAGS",
                        "CARGO_TARGET_X86_64_UNKNOWN_NONE_RUSTFLAGS"):
                self.assertNotIn(key, env)
        args = shlex.split(step["run"])
        self.assertEqual(args[:3], ["cargo", "+1.90.0", "build"])
        self.assertEqual(args.count("--config"), 1)
        additions = tomllib.loads(args[args.index("--config") + 1])
        self.assertEqual(additions, {"target": {"x86_64-unknown-none": {
            "rustflags": ["-C", "target-feature=-sse,-sse2,-sse3,-ssse3,-sse4.1,-sse4.2,-avx,-avx2"],
        }}})

    def test_artifact_component_filter_includes_shared_build_inputs(self):
        """The dedicated gate replaces its broad matrix entry for shared changes too."""
        workflow = self.workflows[".github/workflows/artifact-store-quality.yml"]
        for event in ("pull_request", "push"):
            with self.subTest(event=event):
                self.assertTrue({
                    "Cargo.toml", "Cargo.lock", "rust-toolchain.toml", ".cargo/**",
                    ".github/actions/**", "crates/artifact-store-core/**",
                } <= set(workflow["on"][event]["paths"]))


if __name__ == "__main__":
    unittest.main()
