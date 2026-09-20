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


class ConflictReviewBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.first = self.knowledge / "First.md"
        self.second = self.knowledge / "Second.md"
        self.first.write_text(
            "---\ntopic: conflict\n---\n# First\n\nClaimAlpha.\n",
            encoding="utf-8",
        )
        self.second.write_text(
            "---\ntopic: conflict\n---\n# Second\n\nClaimBeta.\n",
            encoding="utf-8",
        )
        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/First.md",
                "--note", "Knowledge/Second.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )
        by_locator = {
            item["locator"]: item["identity"]
            for item in registered["registered"]
        }
        self.first_id = str(by_locator["Knowledge/First.md"])
        self.second_id = str(by_locator["Knowledge/Second.md"])

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

    def object_state(self) -> list[tuple[str, int, str]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, revision, authority_fingerprint "
                "FROM objects ORDER BY identity"
            ).fetchall()

    def markdown_snapshot(self) -> dict[str, bytes]:
        return {
            path.relative_to(self.vault).as_posix(): path.read_bytes()
            for path in sorted(self.vault.rglob("*.md"))
        }

    def create_source_finding(self) -> tuple[str, str]:
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Source evidence for mixed conflict.",
                "--source", "https://example.org/conflict-source",
            ).stdout
        )
        proposal = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(material["identity"]),
                "--body", "# Source-backed\n\nSourceFindingTarget.\n",
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
        target_identity = str(created["asset_identity"])
        reviewed = json.loads(
            self.run_cli(
                "maintain-review-source",
                "--vault", str(self.vault),
                "--identity", target_identity,
                "--source", "https://example.org/conflict-source",
                "--basis-source-id", "doi:10.1000/conflict",
                "--basis-revision", "v1",
                "--basis-fingerprint", "sha256:old",
                "--observed-source-id", "doi:10.1000/conflict",
                "--observed-revision", "v2",
                "--observed-fingerprint", "sha256:new",
                "--evidence", "Verified source change for conflict review.",
            ).stdout
        )
        return str(reviewed["finding_id"]), target_identity

    def create_relation(self) -> str:
        candidate = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.first_id,
                "--type", "supports",
                "--target-id", self.second_id,
                "--provenance", "Initial relation provenance.",
            ).stdout
        )
        approved = json.loads(
            self.run_cli(
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", str(candidate["candidate_id"]),
                "--confirmed-approval",
            ).stdout
        )
        return str(approved["relation_identity"])

    def propose_knowledge_conflict(self) -> dict[str, object]:
        return json.loads(
            self.run_cli(
                "maintain-propose-conflict",
                "--vault", str(self.vault),
                "--knowledge-id", self.first_id,
                "--knowledge-id", self.second_id,
                "--conflict", "ClaimAlpha and ClaimBeta may not both remain current as written.",
                "--evidence", "The current main model compared both canonical Authority texts.",
            ).stdout
        )

    def test_mixed_conflict_candidate_binds_knowledge_source_finding_and_relation_record(self) -> None:
        finding_id, finding_target = self.create_source_finding()
        relation_id = self.create_relation()

        proposed = json.loads(
            self.run_cli(
                "maintain-propose-conflict",
                "--vault", str(self.vault),
                "--knowledge-id", self.first_id,
                "--source-finding-id", finding_id,
                "--relation-id", relation_id,
                "--conflict", "Knowledge, source evidence, and active relation may be inconsistent.",
                "--evidence", "The current main model reviewed all three governed records.",
            ).stdout
        )

        self.assertEqual(
            ["knowledge_asset", "source_finding", "relation_record"],
            [member["member_kind"] for member in proposed["members"]],
        )
        by_kind = {member["member_kind"]: member for member in proposed["members"]}
        self.assertEqual(self.first_id, by_kind["knowledge_asset"]["member_ref"])
        self.assertEqual(finding_id, by_kind["source_finding"]["member_ref"])
        self.assertEqual(finding_target, by_kind["source_finding"]["basis_identity"])
        self.assertEqual(relation_id, by_kind["relation_record"]["member_ref"])
        self.assertTrue(by_kind["relation_record"]["fingerprint"].startswith("sha256:"))

    def test_conflict_candidate_becomes_stale_when_member_basis_changes_and_can_be_rejected(self) -> None:
        proposed = self.propose_knowledge_conflict()
        candidate_id = str(proposed["candidate_id"])
        edited = self.first.read_text(encoding="utf-8").replace(
            "ClaimAlpha.",
            "ClaimAlpha changed after candidate creation.",
        )
        self.first.write_text(edited, encoding="utf-8")

        inspected = json.loads(
            self.run_cli(
                "maintain-inspect-conflict",
                "--vault", str(self.vault),
                "--candidate-id", candidate_id,
            ).stdout
        )
        self.assertEqual("stale", inspected["status"])

        before_objects = self.object_state()
        before_markdown = self.markdown_snapshot()
        rejected = json.loads(
            self.run_cli(
                "maintain-reject-conflict",
                "--vault", str(self.vault),
                "--candidate-id", candidate_id,
                "--confirmed-rejection",
            ).stdout
        )
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual(before_objects, self.object_state())
        self.assertEqual(before_markdown, self.markdown_snapshot())

    def test_conflict_relation_member_becomes_stale_when_relation_revision_changes(self) -> None:
        relation_id = self.create_relation()
        proposed = json.loads(
            self.run_cli(
                "maintain-propose-conflict",
                "--vault", str(self.vault),
                "--knowledge-id", self.first_id,
                "--relation-id", relation_id,
                "--conflict", "The current claim conflicts with the formal relation basis.",
                "--evidence", "The main model reviewed the claim and relation record.",
            ).stdout
        )

        extra = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.first_id,
                "--type", "supports",
                "--target-id", self.second_id,
                "--provenance", "Additional provenance after conflict candidate.",
            ).stdout
        )
        self.run_cli(
            "relation-approve",
            "--vault", str(self.vault),
            "--candidate-id", str(extra["candidate_id"]),
            "--confirmed-approval",
        )

        inspected = json.loads(
            self.run_cli(
                "maintain-inspect-conflict",
                "--vault", str(self.vault),
                "--candidate-id", str(proposed["candidate_id"]),
            ).stdout
        )
        self.assertEqual("stale", inspected["status"])

    def test_relation_maintenance_candidate_goes_stale_when_local_endpoint_changes(self) -> None:
        relation_id = self.create_relation()
        proposed = json.loads(
            self.run_cli(
                "maintain-propose-relation-maintenance",
                "--vault", str(self.vault),
                "--relation-id", relation_id,
                "--kind", "relation_stale",
                "--evidence", "Endpoint content requires relation review.",
            ).stdout
        )
        edited = self.first.read_text(encoding="utf-8").replace(
            "ClaimAlpha.",
            "ClaimAlpha endpoint changed.",
        )
        self.first.write_text(edited, encoding="utf-8")

        inspected = json.loads(
            self.run_cli(
                "maintain-inspect-relation-maintenance",
                "--vault", str(self.vault),
                "--candidate-id", str(proposed["candidate_id"]),
            ).stdout
        )
        self.assertEqual("stale", inspected["status"])
        self.assertEqual(2, inspected["current_source"]["revision"])

    def test_v4_review_authority_migrates_to_v5_without_losing_source_review_records(self) -> None:
        finding_id, _ = self.create_source_finding()
        with sqlite3.connect(self.database) as conn:
            finding_before = conn.execute(
                "SELECT finding_id, source_state, evidence FROM review_findings "
                "WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            source_candidate_before = conn.execute(
                "SELECT candidate_id, candidate_kind, status "
                "FROM maintenance_candidates WHERE source_finding_id = ?",
                (finding_id,),
            ).fetchone()
            conn.execute("DROP TABLE relation_maintenance_candidates")
            conn.execute("DROP TABLE conflict_candidate_members")
            conn.execute("DROP TABLE conflict_candidates")
            conn.execute(
                "UPDATE schema_meta SET value = '4' WHERE key = 'schema_version'"
            )
            conn.commit()

        self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.first_id,
        )

        with sqlite3.connect(self.database) as conn:
            schema_version = conn.execute(
                "SELECT value FROM schema_meta WHERE key = 'schema_version'"
            ).fetchone()[0]
            finding_after = conn.execute(
                "SELECT finding_id, source_state, evidence FROM review_findings "
                "WHERE finding_id = ?",
                (finding_id,),
            ).fetchone()
            source_candidate_after = conn.execute(
                "SELECT candidate_id, candidate_kind, status "
                "FROM maintenance_candidates WHERE source_finding_id = ?",
                (finding_id,),
            ).fetchone()
            v5_tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('conflict_candidates', "
                    "'conflict_candidate_members', "
                    "'relation_maintenance_candidates')"
                ).fetchall()
            }
        self.assertEqual("5", schema_version)
        self.assertEqual(finding_before, finding_after)
        self.assertEqual(source_candidate_before, source_candidate_after)
        self.assertEqual(
            {
                "conflict_candidates",
                "conflict_candidate_members",
                "relation_maintenance_candidates",
            },
            v5_tables,
        )

    def test_v5_missing_review_governance_table_fails_closed(self) -> None:
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(
                "5",
                conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0],
            )
            conn.execute("DROP TABLE relation_maintenance_candidates")
            conn.commit()

        failed = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.first_id,
            expect=2,
        )
        self.assertIn("missing required v5 tables", failed.stderr)

    def test_relation_maintenance_candidate_goes_stale_when_bound_source_evidence_basis_changes(self) -> None:
        finding_id, finding_target = self.create_source_finding()
        relation_id = self.create_relation()
        proposed = json.loads(
            self.run_cli(
                "maintain-propose-relation-maintenance",
                "--vault", str(self.vault),
                "--relation-id", relation_id,
                "--kind", "relation_stale",
                "--source-finding-id", finding_id,
                "--evidence", "Verified Source finding is part of the relation maintenance basis.",
            ).stdout
        )
        self.assertEqual(finding_id, proposed["source_finding"]["finding_id"])
        self.assertEqual(
            finding_target,
            proposed["source_finding"]["basis_identity"],
        )

        with sqlite3.connect(self.database) as conn:
            locator = conn.execute(
                "SELECT locator FROM objects WHERE identity = ?",
                (finding_target,),
            ).fetchone()[0]
        path = self.vault / str(locator)
        path.write_text(
            path.read_text(encoding="utf-8").replace(
                "SourceFindingTarget.",
                "SourceFindingTarget changed after relation maintenance candidate.",
            ),
            encoding="utf-8",
        )

        inspected = json.loads(
            self.run_cli(
                "maintain-inspect-relation-maintenance",
                "--vault", str(self.vault),
                "--candidate-id", str(proposed["candidate_id"]),
            ).stdout
        )
        self.assertEqual("stale", inspected["status"])

    def test_relation_maintenance_candidate_uses_existing_relation_governance_and_goes_stale(self) -> None:
        relation_id = self.create_relation()
        proposed = json.loads(
            self.run_cli(
                "maintain-propose-relation-maintenance",
                "--vault", str(self.vault),
                "--relation-id", relation_id,
                "--kind", "relation_conflict",
                "--evidence", "Endpoint evidence now conflicts with the active relation.",
            ).stdout
        )
        self.assertEqual("pending", proposed["status"])
        self.assertEqual("relation_conflict", proposed["candidate_kind"])
        self.assertEqual(relation_id, proposed["relation_identity"])
        self.assertEqual(
            "relation-revoke with expected revision",
            proposed["revoke_governance"],
        )
        self.assertEqual(
            "relation-propose -> relation-approve",
            proposed["replacement_governance"],
        )

        extra = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.first_id,
                "--type", "supports",
                "--target-id", self.second_id,
                "--provenance", "New provenance after maintenance candidate.",
            ).stdout
        )
        self.run_cli(
            "relation-approve",
            "--vault", str(self.vault),
            "--candidate-id", str(extra["candidate_id"]),
            "--confirmed-approval",
        )

        inspected = json.loads(
            self.run_cli(
                "maintain-inspect-relation-maintenance",
                "--vault", str(self.vault),
                "--candidate-id", str(proposed["candidate_id"]),
            ).stdout
        )
        self.assertEqual("stale", inspected["status"])

        with sqlite3.connect(self.database) as conn:
            relation = conn.execute(
                "SELECT source_ref, relation_type, target_ref, revision, status "
                "FROM relation_records WHERE identity = ?",
                (relation_id,),
            ).fetchone()
        self.assertEqual(
            (self.first_id, "supports", self.second_id, 2, "active"),
            relation,
        )

    def test_two_current_knowledge_assets_form_pending_conflict_candidate_without_authority_change(self) -> None:
        before_objects = self.object_state()
        before_markdown = self.markdown_snapshot()

        proposed = self.propose_knowledge_conflict()

        self.assertEqual("pending", proposed["status"])
        self.assertEqual("semantic_conflict", proposed["candidate_kind"])
        self.assertEqual(
            "ClaimAlpha and ClaimBeta may not both remain current as written.",
            proposed["conflict"],
        )
        self.assertEqual(
            "The current main model compared both canonical Authority texts.",
            proposed["evidence"],
        )
        self.assertEqual(2, len(proposed["members"]))
        self.assertEqual(
            {self.first_id, self.second_id},
            {member["identity"] for member in proposed["members"]},
        )
        for member in proposed["members"]:
            self.assertEqual("knowledge_asset", member["member_kind"])
            self.assertEqual(1, member["revision"])
            self.assertTrue(member["fingerprint"])
            self.assertTrue(member["canonical_locator"].endswith(".md"))

        self.assertEqual(before_objects, self.object_state())
        self.assertEqual(before_markdown, self.markdown_snapshot())
        with sqlite3.connect(self.database) as conn:
            object_count = conn.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
            candidate_count = conn.execute(
                "SELECT COUNT(*) FROM conflict_candidates"
            ).fetchone()[0]
            member_count = conn.execute(
                "SELECT COUNT(*) FROM conflict_candidate_members"
            ).fetchone()[0]
        self.assertEqual(2, object_count)
        self.assertEqual(1, candidate_count)
        self.assertEqual(2, member_count)
        with sqlite3.connect(self.database) as conn:
            relation_count = conn.execute(
                "SELECT COUNT(*) FROM relation_records"
            ).fetchone()[0]
        self.assertEqual(0, relation_count)


if __name__ == "__main__":
    unittest.main()
