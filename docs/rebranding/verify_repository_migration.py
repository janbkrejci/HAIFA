"""Exercise the documented Git migration against disposable local repositories."""

from __future__ import annotations

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

DOCUMENT = Path(__file__).with_name("repository-migration.md")


class RepositoryMigrationTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory(prefix="giro-migration-test-")
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "HAIFA"
        self.destination = self.root / "GIRO.git"
        self.staging = self.root / "migration"
        self.environment = {
            **os.environ,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_AUTHOR_NAME": "Migration test",
            "GIT_AUTHOR_EMAIL": "migration@example.invalid",
            "GIT_COMMITTER_NAME": "Migration test",
            "GIT_COMMITTER_EMAIL": "migration@example.invalid",
            "GIT_TERMINAL_PROMPT": "0",
            "SRC": str(self.source),
            "DST": str(self.destination),
            "MIGRATION_DIR": str(self.staging),
        }
        self.git("init", "--initial-branch=main", str(self.source))
        self.git("-C", str(self.source), "commit", "--allow-empty", "-m", "HAIFA source")
        self.git("-C", str(self.source), "branch", "unfinished-work")
        self.git("-C", str(self.source), "tag", "v0.1.613")
        self.git(
            "-C",
            str(self.source),
            "tag",
            "-a",
            "haifa-transition-source",
            "-m",
            "Retained source",
        )
        self.git("-C", str(self.source), "commit", "--allow-empty", "-m", "GIRO source")
        self.git("init", "--bare", "--initial-branch=main", str(self.destination))
        self.source_before = self.refs(self.source)

    def git(self, *arguments: str) -> str:
        return subprocess.run(
            ["git", *arguments],
            env=self.environment,
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        ).stdout

    def refs(self, repo: Path) -> str:
        # Include ^{} entries to verify both tag objects and peeled commits.
        return "\n".join(sorted(self.git("ls-remote", "--heads", "--tags", str(repo)).splitlines()))

    def migrate(self) -> subprocess.CompletedProcess[str]:
        text = DOCUMENT.read_text(encoding="utf-8")
        block = (
            text.split("<!-- migration-git:start -->", 1)[1]
            .split("<!-- migration-git:end -->", 1)[0]
            .split("```bash\n", 1)[1]
            .split("```", 1)[0]
        )
        return subprocess.run(
            ["bash", "-c", block],
            env=self.environment,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def test_preserves_branches_history_and_both_tag_types(self) -> None:
        result = self.migrate()
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(self.refs(self.source), self.source_before)
        self.assertEqual(self.refs(self.destination), self.source_before)
        self.assertIn("refs/heads/unfinished-work", self.source_before)
        self.assertIn("refs/tags/haifa-transition-source^{}", self.source_before)
        for repo in (self.source, self.destination):
            self.git("-C", str(repo), "fsck", "--full")
        self.assertEqual(
            (self.staging / "snapshot.refs").read_bytes(),
            (self.staging / "destination-after.refs").read_bytes(),
        )

    def test_rejects_nonempty_destination_without_changing_either_repo(self) -> None:
        self.git("-C", str(self.source), "push", str(self.destination), "main:occupied")
        destination_before = self.refs(self.destination)
        result = self.migrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.refs(self.destination), destination_before)
        self.assertEqual(self.refs(self.source), self.source_before)
        self.assertFalse((self.staging / "source.git").exists())

    def test_rejects_same_source_and_destination(self) -> None:
        self.environment["DST"] = str(self.source)
        result = self.migrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.refs(self.source), self.source_before)
        self.assertFalse(self.staging.exists())

    def test_rejects_existing_staging_directory(self) -> None:
        self.staging.mkdir()
        marker = self.staging / "keep"
        marker.write_text("existing data", encoding="utf-8")
        result = self.migrate()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(marker.read_text(encoding="utf-8"), "existing data")
        self.assertEqual(self.refs(self.source), self.source_before)
        self.assertEqual(self.refs(self.destination), "")


if __name__ == "__main__":
    unittest.main()
