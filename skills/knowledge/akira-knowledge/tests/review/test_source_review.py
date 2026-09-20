from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[2]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class SourceReviewBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.seed = self.knowledge / "Existing.md"
        self.seed.write_text(
            "---\n"
            "topic: review\n"
            "---\n"
            "# Existing\n\n"
            "SourceReviewToken.\n",
            encoding="utf-8",
        )
        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/Existing.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )
        self.seed_identity = registered["registered"][0]["identity"]

        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Evidence for source review.",
                "--source", "https://example.org/source-review",
            ).stdout
        )
        self.material_identity = str(material["identity"])
        proposal = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", self.material_identity,
                "--body", "# Reviewed Knowledge\n\nDerivedFromSourceToken.\n",
            ).stdout
        )
        created = json.loads(
            self.run_cli(
                "curate-approve",
                "--vault", str(self.vault),
                "--proposal-id", str(proposal["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.asset_identity = str(created["asset_identity"])

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    def run_cli(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            [sys.executable, str(CLI), *args],
            text=True,
            capture_output=True,
            check=False,
        )
        self.assertEqual(
            expect,
            result.returncode,
            msg=f"stdout:\n{result.stdout}\nstderr:\n{result.stderr}",
        )
        return result

    def asset_revision(self) -> int:
        with sqlite3.connect(self.database) as conn:
            return int(
                conn.execute(
                    "SELECT revision FROM objects WHERE identity = ?",
                    (self.asset_identity,),
                ).fetchone()[0]
            )

    def review_source(self, *extra: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "maintain-review-source",
            "--vault", str(self.vault),
            "--identity", self.asset_identity,
            "--source", "https://example.org/source-review",
            *extra,
            expect=expect,
        )

    def create_changed_candidate(self) -> dict[str, object]:
        return json.loads(
            self.review_source(
                "--basis-source-id", "doi:10.1000/example",
                "--basis-revision", "v1",
                "--basis-fingerprint", "sha256:old",
                "--observed-source-id", "doi:10.1000/example",
                "--observed-revision", "v2",
                "--observed-fingerprint", "sha256:new",
                "--evidence", "Publisher metadata reports revision v2.",
            ).stdout
        )

    def test_review_plan_lists_target_provenance_sources_without_creating_governance_records(self) -> None:
        before_revision = self.asset_revision()
        before_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }

        planned = json.loads(
            self.run_cli(
                "maintain-review-plan",
                "--vault", str(self.vault),
                "--identity", self.asset_identity,
            ).stdout
        )

        self.assertEqual(self.asset_identity, planned["target_identity"])
        self.assertEqual(before_revision, planned["target_revision"])
        self.assertTrue(planned["canonical_locator"].endswith(".md"))
        self.assertEqual("current", planned["current_lifecycle"])
        self.assertEqual(
            [
                {
                    "material_identity": self.material_identity,
                    "source_locator": "https://example.org/source-review",
                }
            ],
            [
                {
                    "material_identity": item["material_identity"],
                    "source_locator": item["source_locator"],
                }
                for item in planned["sources"]
            ],
        )
        self.assertEqual(
            "verify each Source with source-specific access, then call maintain-review-source",
            planned["next_step"],
        )

        after_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.assertEqual(before_markdown, after_markdown)
        self.assertEqual(before_revision, self.asset_revision())
        with sqlite3.connect(self.database) as conn:
            finding_count = conn.execute(
                "SELECT COUNT(*) FROM review_findings"
            ).fetchone()[0]
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM maintenance_candidates"
            ).fetchone()[0]
        self.assertEqual(0, finding_count)
        self.assertEqual(0, candidate_count)

    def test_review_plan_reuses_latest_verified_source_observation_as_future_basis(self) -> None:
        reviewed = self.create_changed_candidate()
        self.assertEqual("changed", reviewed["source_state"])

        unknown = json.loads(
            self.review_source(
                "--basis-source-id", "doi:10.1000/example",
                "--basis-revision", "v2",
                "--basis-fingerprint", "sha256:new",
                "--unknown",
                "--evidence", "Temporary network failure after the verified v2 observation.",
            ).stdout
        )
        self.assertEqual("unknown", unknown["source_state"])

        planned = json.loads(
            self.run_cli(
                "maintain-review-plan",
                "--vault", str(self.vault),
                "--identity", self.asset_identity,
            ).stdout
        )
        source = planned["sources"][0]
        self.assertEqual(
            {
                "source_id": "doi:10.1000/example",
                "revision": "v2",
                "fingerprint": "sha256:new",
            },
            {
                "source_id": source["last_verified"]["source_id"],
                "revision": source["last_verified"]["revision"],
                "fingerprint": source["last_verified"]["fingerprint"],
            },
        )

    def test_candidate_revalidation_marks_stale_when_target_authority_changes(self) -> None:
        reviewed = self.create_changed_candidate()
        candidate_id = str(reviewed["candidate"]["candidate_id"])
        asset_path = self.vault / str(reviewed["canonical_locator"])
        edited = asset_path.read_text(encoding="utf-8").replace(
            "DerivedFromSourceToken.",
            "NewerAuthorityMustWin.",
        )
        asset_path.write_text(edited, encoding="utf-8")

        inspected = json.loads(
            self.run_cli(
                "maintain-inspect-review-candidate",
                "--vault", str(self.vault),
                "--candidate-id", candidate_id,
            ).stdout
        )

        self.assertEqual("stale", inspected["status"])
        self.assertEqual(candidate_id, inspected["candidate_id"])
        self.assertEqual(edited, asset_path.read_text(encoding="utf-8"))
        with sqlite3.connect(self.database) as conn:
            row = conn.execute(
                "SELECT status FROM maintenance_candidates WHERE candidate_id = ?",
                (candidate_id,),
            ).fetchone()
        self.assertEqual(("stale",), row)

    def test_user_can_reject_pending_stale_candidate_without_authority_change(self) -> None:
        reviewed = self.create_changed_candidate()
        candidate_id = str(reviewed["candidate"]["candidate_id"])
        before_revision = self.asset_revision()
        before = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }

        denied = self.run_cli(
            "maintain-reject-review-candidate",
            "--vault", str(self.vault),
            "--candidate-id", candidate_id,
            expect=2,
        )
        self.assertIn("explicit user rejection", denied.stderr)

        rejected = json.loads(
            self.run_cli(
                "maintain-reject-review-candidate",
                "--vault", str(self.vault),
                "--candidate-id", candidate_id,
                "--confirmed-rejection",
            ).stdout
        )
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual(before_revision, self.asset_revision())
        after = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.assertEqual(before, after)

    def test_changed_source_creates_pending_stale_candidate_without_modifying_authority(self) -> None:
        before_revision = self.asset_revision()
        before_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }

        reviewed = self.create_changed_candidate()

        self.assertEqual("changed", reviewed["source_state"])
        self.assertEqual(self.asset_identity, reviewed["target_identity"])
        self.assertEqual(before_revision, reviewed["target_revision"])
        self.assertTrue(reviewed["canonical_locator"].endswith(".md"))
        self.assertEqual(
            "knowledge-curate update proposal or knowledge-maintain lifecycle proposal",
            reviewed["governance_path"],
        )
        self.assertEqual("pending", reviewed["candidate"]["status"])
        self.assertEqual("source_stale", reviewed["candidate"]["candidate_kind"])
        self.assertEqual(
            "https://example.org/source-review",
            reviewed["candidate"]["source_locator"],
        )
        self.assertEqual(
            "Publisher metadata reports revision v2.",
            reviewed["candidate"]["evidence"],
        )
        self.assertEqual(before_revision, self.asset_revision())
        after_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.assertEqual(before_markdown, after_markdown)

        with sqlite3.connect(self.database) as conn:
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM maintenance_candidates"
            ).fetchone()[0]
            object_count = conn.execute(
                "SELECT COUNT(*) FROM objects"
            ).fetchone()[0]
        self.assertEqual(1, candidate_count)
        self.assertEqual(3, object_count)

    def test_unknown_source_check_records_finding_without_stale_candidate(self) -> None:
        reviewed = json.loads(
            self.review_source(
                "--basis-source-id", "doi:10.1000/example",
                "--basis-revision", "v1",
                "--basis-fingerprint", "sha256:old",
                "--unknown",
                "--evidence", "Network unavailable; current source revision cannot be confirmed.",
            ).stdout
        )

        self.assertEqual("unknown", reviewed["source_state"])
        self.assertIsNone(reviewed["candidate"])
        with sqlite3.connect(self.database) as conn:
            findings = conn.execute(
                "SELECT source_state, evidence FROM review_findings ORDER BY rowid"
            ).fetchall()
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM maintenance_candidates"
            ).fetchone()[0]
        self.assertEqual(
            [
                (
                    "unknown",
                    "Network unavailable; current source revision cannot be confirmed.",
                )
            ],
            findings,
        )
        self.assertEqual(0, candidate_count)

    def test_unchanged_source_records_finding_without_candidate(self) -> None:
        reviewed = json.loads(
            self.review_source(
                "--basis-source-id", "doi:10.1000/example",
                "--basis-revision", "v1",
                "--basis-fingerprint", "sha256:same",
                "--observed-source-id", "doi:10.1000/example",
                "--observed-revision", "v1",
                "--observed-fingerprint", "sha256:same",
                "--evidence", "Publisher metadata and content fingerprint still match.",
            ).stdout
        )

        self.assertEqual("unchanged", reviewed["source_state"])
        self.assertIsNone(reviewed["candidate"])
        with sqlite3.connect(self.database) as conn:
            finding = conn.execute(
                "SELECT source_state, observed_source_id, observed_revision, "
                "observed_fingerprint FROM review_findings"
            ).fetchone()
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM maintenance_candidates"
            ).fetchone()[0]
        self.assertEqual(
            (
                "unchanged",
                "doi:10.1000/example",
                "v1",
                "sha256:same",
            ),
            finding,
        )
        self.assertEqual(0, candidate_count)

    def test_v3_database_migrates_review_authority_to_v4_without_markdown_rewrite(self) -> None:
        before_revision = self.asset_revision()
        before_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        with sqlite3.connect(self.database) as conn:
            conn.execute("DROP TABLE maintenance_candidates")
            conn.execute("DROP TABLE review_findings")
            conn.execute(
                "UPDATE schema_meta SET value = '3' WHERE key = 'schema_version'"
            )
            conn.commit()

        exact = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--identity", self.asset_identity,
            ).stdout
        )

        self.assertEqual(self.asset_identity, exact["result"]["stable_identity"])
        self.assertEqual(before_revision, self.asset_revision())
        after_markdown = {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }
        self.assertEqual(before_markdown, after_markdown)
        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type = 'table' "
                    "AND name IN ('review_findings', 'maintenance_candidates')"
                ).fetchall()
            }
        self.assertEqual("4", schema_version)
        self.assertEqual(
            {"review_findings", "maintenance_candidates"},
            tables,
        )

    def test_v4_missing_review_authority_fails_closed_instead_of_recreating_empty_state(self) -> None:
        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            self.assertEqual("4", schema_version)
            conn.execute("DROP TABLE maintenance_candidates")
            conn.commit()

        failed = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.asset_identity,
            expect=2,
        )

        self.assertIn("Review structured Authority is missing", failed.stderr)
        with sqlite3.connect(self.database) as conn:
            missing = conn.execute(
                "SELECT name FROM sqlite_master "
                "WHERE type = 'table' AND name = 'maintenance_candidates'"
            ).fetchall()
        self.assertEqual([], missing)

    def test_source_identity_change_fails_closed_without_candidate(self) -> None:
        failed = self.review_source(
            "--basis-source-id", "doi:10.1000/example",
            "--basis-revision", "v1",
            "--basis-fingerprint", "sha256:old",
            "--observed-source-id", "doi:10.1000/different",
            "--observed-revision", "v2",
            "--observed-fingerprint", "sha256:new",
            "--evidence", "Redirect resolved to a different owner.",
            expect=2,
        )

        self.assertIn("source identity changed", failed.stderr.lower())
        with sqlite3.connect(self.database) as conn:
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM maintenance_candidates"
            ).fetchone()[0]
            finding_count = conn.execute(
                "SELECT COUNT(*) FROM review_findings"
            ).fetchone()[0]
        self.assertEqual(0, candidate_count)
        self.assertEqual(0, finding_count)

    def test_source_must_be_in_target_provenance_chain(self) -> None:
        failed = self.run_cli(
            "maintain-review-source",
            "--vault", str(self.vault),
            "--identity", self.seed_identity,
            "--source", "https://example.org/source-review",
            "--basis-source-id", "doi:10.1000/example",
            "--basis-revision", "v1",
            "--basis-fingerprint", "sha256:old",
            "--observed-source-id", "doi:10.1000/example",
            "--observed-revision", "v2",
            "--observed-fingerprint", "sha256:new",
            "--evidence", "This source was never provenance for the registered seed.",
            expect=2,
        )
        self.assertIn("not in the target knowledge provenance", failed.stderr.lower())


if __name__ == "__main__":
    unittest.main()
