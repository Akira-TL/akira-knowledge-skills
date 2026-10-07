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


class BatchMaintenanceBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        (self.knowledge / "A.md").write_text(
            "# A\n\nOriginal A.\n",
            encoding="utf-8",
        )
        (self.knowledge / "B.md").write_text(
            "# B\n\nOriginal B.\n",
            encoding="utf-8",
        )
        (self.knowledge / "C.md").write_text(
            "---\nowner: old\ncustom: preserve\n---\n"
            "# C\n\nOriginal C.\n<!-- preserve comment -->\n",
            encoding="utf-8",
        )

        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/A.md",
                "--note", "Knowledge/B.md",
                "--note", "Knowledge/C.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )
        self.ids = {
            Path(item["locator"]).name: str(item["identity"])
            for item in registered["registered"]
        }

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

    def object_revision(self, identity: str) -> int:
        with sqlite3.connect(self.database) as conn:
            return int(
                conn.execute(
                    "SELECT revision FROM objects WHERE identity = ?",
                    (identity,),
                ).fetchone()[0]
            )

    def lifecycle(self, identity: str) -> str:
        with sqlite3.connect(self.database) as conn:
            return str(
                conn.execute(
                    "SELECT status FROM knowledge_asset_lifecycle WHERE identity = ?",
                    (identity,),
                ).fetchone()[0]
            )

    def relation_state(self, identity: str) -> tuple[str, int]:
        with sqlite3.connect(self.database) as conn:
            row = conn.execute(
                "SELECT status, revision FROM relation_records WHERE identity = ?",
                (identity,),
            ).fetchone()
        return str(row[0]), int(row[1])

    def make_update_proposal(self) -> str:
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Evidence for batch update.",
                "--source", "https://example.org/batch-update",
            ).stdout
        )
        proposal = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(material["identity"]),
                "--target-id", self.ids["A.md"],
                "--base-revision", "1",
                "--body", "# A\n\nUpdated A through existing update governance.\n",
            ).stdout
        )
        return str(proposal["proposal_id"])

    def make_retire_proposal(self) -> str:
        proposal = json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", self.ids["B.md"],
                "--base-revision", "1",
                "--reason", "Retire B in the batch.",
            ).stdout
        )
        return str(proposal["proposal_id"])

    def make_authority_edit_proposal(self) -> str:
        proposal = json.loads(
            self.run_cli(
                "maintain-propose-authority-edit",
                "--vault", str(self.vault),
                "--identity", self.ids["C.md"],
                "--base-revision", "1",
                "--set-property", "owner", "new-owner",
                "--reason", "Update C owner through existing authority-edit governance.",
            ).stdout
        )
        return str(proposal["proposal_id"])

    def make_relation_revoke_candidate(self) -> tuple[str, str]:
        relation_candidate = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.ids["A.md"],
                "--type", "supports",
                "--target-id", self.ids["C.md"],
                "--provenance", "Batch relation provenance.",
            ).stdout
        )
        relation = json.loads(
            self.run_cli(
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", str(relation_candidate["candidate_id"]),
                "--confirmed-approval",
            ).stdout
        )
        relation_id = str(relation["relation_identity"])
        maintenance = json.loads(
            self.run_cli(
                "maintain-propose-relation-maintenance",
                "--vault", str(self.vault),
                "--relation-id", relation_id,
                "--kind", "relation_stale",
                "--evidence", "The batch may revoke this relation after explicit subset approval.",
            ).stdout
        )
        return str(maintenance["candidate_id"]), relation_id

    def create_batch(
        self,
        *,
        include_update: bool = True,
        include_retire: bool = True,
        include_authority_edit: bool = True,
        include_relation_revoke: bool = True,
    ) -> tuple[dict[str, object], dict[str, str]]:
        refs: dict[str, str] = {}
        args = ["maintain-batch-create", "--vault", str(self.vault)]
        if include_update:
            refs["knowledge_update"] = self.make_update_proposal()
            args += ["--update-proposal", refs["knowledge_update"]]
        if include_retire:
            refs["lifecycle_retire"] = self.make_retire_proposal()
            args += ["--retire-proposal", refs["lifecycle_retire"]]
        if include_authority_edit:
            refs["authority_edit"] = self.make_authority_edit_proposal()
            args += ["--authority-edit-proposal", refs["authority_edit"]]
        if include_relation_revoke:
            candidate_id, relation_id = self.make_relation_revoke_candidate()
            refs["relation_revoke"] = candidate_id
            refs["relation_identity"] = relation_id
            args += ["--relation-revoke-candidate", candidate_id]
        payload = json.loads(self.run_cli(*args).stdout)
        return payload, refs

    def test_batch_creation_and_subset_approval_do_not_execute_unapproved_authority(self) -> None:
        batch, refs = self.create_batch()
        before_markdown = {
            path.name: path.read_bytes()
            for path in sorted(self.knowledge.glob("*.md"))
        }

        self.assertEqual("pending", batch["status"])
        self.assertEqual(4, len(batch["items"]))
        by_kind = {item["item_kind"]: item for item in batch["items"]}
        self.assertEqual(
            {
                "knowledge_update",
                "lifecycle_retire",
                "authority_edit",
                "relation_revoke",
            },
            set(by_kind),
        )
        for item in batch["items"]:
            self.assertEqual("pending", item["status"])
            self.assertTrue(item["item_id"])
            self.assertTrue(item["governance_ref"])
            self.assertTrue(item["evidence"])
            self.assertTrue(item["proposed_change"])
            self.assertTrue(item["bases"])

        approved = json.loads(
            self.run_cli(
                "maintain-batch-approve",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
                "--item-id", str(by_kind["knowledge_update"]["item_id"]),
                "--item-id", str(by_kind["authority_edit"]["item_id"]),
                "--confirmed-approval",
            ).stdout
        )

        self.assertEqual("approved", approved["status"])
        statuses = {
            item["item_kind"]: item["status"]
            for item in approved["items"]
        }
        self.assertEqual("approved", statuses["knowledge_update"])
        self.assertEqual("approved", statuses["authority_edit"])
        self.assertEqual("rejected", statuses["lifecycle_retire"])
        self.assertEqual("rejected", statuses["relation_revoke"])
        approvals = {
            item["item_kind"]: item["approval_result"]
            for item in approved["items"]
        }
        self.assertEqual("approved", approvals["knowledge_update"])
        self.assertEqual("approved", approvals["authority_edit"])
        self.assertEqual("rejected", approvals["lifecycle_retire"])
        self.assertEqual("rejected", approvals["relation_revoke"])

        after_markdown = {
            path.name: path.read_bytes()
            for path in sorted(self.knowledge.glob("*.md"))
        }
        self.assertEqual(before_markdown, after_markdown)
        self.assertEqual(1, self.object_revision(self.ids["A.md"]))
        self.assertEqual(1, self.object_revision(self.ids["B.md"]))
        self.assertEqual(1, self.object_revision(self.ids["C.md"]))
        self.assertEqual("current", self.lifecycle(self.ids["B.md"]))
        self.assertEqual(
            ("active", 1),
            self.relation_state(refs["relation_identity"]),
        )

    def test_batch_reuses_supersede_and_relation_candidate_governance(self) -> None:
        supersede = json.loads(
            self.run_cli(
                "maintain-propose-supersede",
                "--vault", str(self.vault),
                "--identity", self.ids["A.md"],
                "--base-revision", "1",
                "--replacement-id", self.ids["B.md"],
                "--replacement-revision", "1",
                "--reason", "B supersedes A in this batch.",
            ).stdout
        )
        relation = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.ids["C.md"],
                "--type", "supports",
                "--target-id", self.ids["B.md"],
                "--provenance", "Independent relation batch item.",
            ).stdout
        )

        batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--supersede-proposal", str(supersede["proposal_id"]),
                "--relation-candidate", str(relation["candidate_id"]),
            ).stdout
        )
        self.assertEqual(
            {"lifecycle_supersede", "relation_candidate"},
            {item["item_kind"] for item in batch["items"]},
        )

        approved = json.loads(
            self.run_cli(
                "maintain-batch-approve",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
                *sum(
                    (
                        ["--item-id", str(item["item_id"])]
                        for item in batch["items"]
                    ),
                    [],
                ),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual("approved", approved["status"])

        executed = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("completed", executed["status"])
        self.assertTrue(
            all(item["status"] == "succeeded" for item in executed["items"])
        )
        self.assertEqual("superseded", self.lifecycle(self.ids["A.md"]))
        self.assertEqual(2, self.object_revision(self.ids["A.md"]))
        self.assertEqual(1, self.object_revision(self.ids["B.md"]))
        with sqlite3.connect(self.database) as conn:
            relation_row = conn.execute(
                "SELECT source_ref, relation_type, target_ref, revision, status "
                "FROM relation_records"
            ).fetchone()
        self.assertEqual(
            (self.ids["C.md"], "supports", self.ids["B.md"], 1, "active"),
            relation_row,
        )

        before = self.revision_snapshot_for_projection()
        self.run_cli("views-rebuild", "--vault", str(self.vault))
        self.run_cli("relation-graph-rebuild", "--vault", str(self.vault))
        self.assertEqual(before, self.revision_snapshot_for_projection())

    def revision_snapshot_for_projection(
        self,
    ) -> tuple[list[tuple[str, int]], list[tuple[str, int]]]:
        with sqlite3.connect(self.database) as conn:
            objects = conn.execute(
                "SELECT identity, revision FROM objects ORDER BY identity"
            ).fetchall()
            relations = conn.execute(
                "SELECT identity, revision FROM relation_records ORDER BY identity"
            ).fetchall()
        return objects, relations

    def test_batch_preserves_existing_disjoint_move_semantics_for_update_and_relation_candidate(self) -> None:
        update_id = self.make_update_proposal()
        relation = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", self.ids["C.md"],
                "--type", "supports",
                "--target-id", self.ids["B.md"],
                "--provenance", "Relation candidate created before a pure endpoint move.",
            ).stdout
        )
        update_batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--update-proposal", update_id,
            ).stdout
        )
        relation_batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--relation-candidate", str(relation["candidate_id"]),
            ).stdout
        )
        for batch in (update_batch, relation_batch):
            self.run_cli(
                "maintain-batch-approve",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
                "--item-id", str(batch["items"][0]["item_id"]),
                "--confirmed-approval",
            )

        (self.knowledge / "A.md").rename(self.knowledge / "A-moved.md")
        (self.knowledge / "C.md").rename(self.knowledge / "C-moved.md")
        self.run_cli(
            "maintain-sync",
            "--vault", str(self.vault),
            "--identity", self.ids["A.md"],
        )
        self.run_cli(
            "maintain-sync",
            "--vault", str(self.vault),
            "--identity", self.ids["C.md"],
        )

        update_result = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(update_batch["batch_id"]),
            ).stdout
        )
        relation_result = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(relation_batch["batch_id"]),
            ).stdout
        )

        self.assertEqual("completed", update_result["status"])
        self.assertEqual("succeeded", update_result["items"][0]["status"])
        self.assertEqual("completed", relation_result["status"])
        self.assertEqual("succeeded", relation_result["items"][0]["status"])
        self.assertEqual(3, self.object_revision(self.ids["A.md"]))
        self.assertEqual(2, self.object_revision(self.ids["C.md"]))
        self.assertTrue((self.knowledge / "A-moved.md").exists())
        self.assertIn(
            "Updated A through existing update governance.",
            (self.knowledge / "A-moved.md").read_text(encoding="utf-8"),
        )

    def test_batch_relation_revoke_is_revision_safe_and_idempotent(self) -> None:
        maintenance_id, relation_id = self.make_relation_revoke_candidate()
        batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--relation-revoke-candidate", maintenance_id,
            ).stdout
        )
        item_id = str(batch["items"][0]["item_id"])
        self.run_cli(
            "maintain-batch-approve",
            "--vault", str(self.vault),
            "--batch-id", str(batch["batch_id"]),
            "--item-id", item_id,
            "--confirmed-approval",
        )
        executed = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("completed", executed["status"])
        self.assertEqual("succeeded", executed["items"][0]["status"])
        self.assertEqual("approved", executed["items"][0]["approval_result"])
        self.assertEqual(("revoked", 2), self.relation_state(relation_id))

        rerun = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("completed", rerun["status"])
        self.assertEqual("succeeded", rerun["items"][0]["status"])
        self.assertEqual(("revoked", 2), self.relation_state(relation_id))

    def test_batch_relation_revoke_revalidates_relation_maintenance_endpoint_basis(self) -> None:
        maintenance_id, relation_id = self.make_relation_revoke_candidate()
        batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--relation-revoke-candidate", maintenance_id,
            ).stdout
        )
        self.run_cli(
            "maintain-batch-approve",
            "--vault", str(self.vault),
            "--batch-id", str(batch["batch_id"]),
            "--item-id", str(batch["items"][0]["item_id"]),
            "--confirmed-approval",
        )

        a_path = self.knowledge / "A.md"
        a_path.write_text(
            a_path.read_text(encoding="utf-8").replace(
                "Original A.",
                "Endpoint changed after batch approval.",
            ),
            encoding="utf-8",
        )

        executed = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("partial", executed["status"])
        self.assertEqual("stale", executed["items"][0]["status"])
        self.assertEqual("approved", executed["items"][0]["approval_result"])
        self.assertEqual(("active", 1), self.relation_state(relation_id))
        self.assertIn(
            "Endpoint changed after batch approval.",
            a_path.read_text(encoding="utf-8"),
        )

    def test_failed_governance_item_does_not_block_independent_fresh_item(self) -> None:
        update_id = self.make_update_proposal()
        authority_id = self.make_authority_edit_proposal()
        batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--update-proposal", update_id,
                "--authority-edit-proposal", authority_id,
            ).stdout
        )
        item_ids = [str(item["item_id"]) for item in batch["items"]]
        self.run_cli(
            "maintain-batch-approve",
            "--vault", str(self.vault),
            "--batch-id", str(batch["batch_id"]),
            *sum((["--item-id", item_id] for item_id in item_ids), []),
            "--confirmed-approval",
        )

        self.run_cli(
            "curate-reject",
            "--vault", str(self.vault),
            "--proposal-id", update_id,
            "--confirmed-rejection",
        )

        executed = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("partial", executed["status"])
        by_kind = {item["item_kind"]: item for item in executed["items"]}
        self.assertEqual("failed", by_kind["knowledge_update"]["status"])
        self.assertEqual("succeeded", by_kind["authority_edit"]["status"])
        self.assertEqual(1, self.object_revision(self.ids["A.md"]))
        self.assertEqual(2, self.object_revision(self.ids["C.md"]))

    def test_v6_migrates_to_v7_and_v7_missing_batch_governance_fails_closed(self) -> None:
        before = self.revision_snapshot_for_projection()
        before_markdown = {
            path.name: path.read_bytes()
            for path in sorted(self.knowledge.glob("*.md"))
        }
        with sqlite3.connect(self.database) as conn:
            conn.execute("DROP TABLE maintenance_batch_item_bases")
            conn.execute("DROP TABLE maintenance_batch_items")
            conn.execute("DROP TABLE maintenance_batches")
            conn.execute(
                "UPDATE schema_meta SET value = '6' WHERE key = 'schema_version'"
            )
            conn.commit()

        self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.ids["A.md"],
        )
        with sqlite3.connect(self.database) as conn:
            self.assertEqual(
                "8",
                conn.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0],
            )
            tables = {
                row[0]
                for row in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' "
                    "AND name IN ('maintenance_batches', "
                    "'maintenance_batch_items', "
                    "'maintenance_batch_item_bases')"
                ).fetchall()
            }
        self.assertEqual(
            {
                "maintenance_batches",
                "maintenance_batch_items",
                "maintenance_batch_item_bases",
            },
            tables,
        )
        self.assertEqual(before, self.revision_snapshot_for_projection())
        self.assertEqual(
            before_markdown,
            {
                path.name: path.read_bytes()
                for path in sorted(self.knowledge.glob("*.md"))
            },
        )

        with sqlite3.connect(self.database) as conn:
            conn.execute("DROP TABLE maintenance_batch_item_bases")
            conn.commit()
        failed = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.ids["A.md"],
            expect=2,
        )
        self.assertIn("Batch structured governance is missing", failed.stderr)

    def test_batch_execution_is_partial_revision_safe_and_idempotent_for_completed_items(self) -> None:
        batch, _ = self.create_batch(
            include_update=False,
            include_relation_revoke=False,
        )
        by_kind = {item["item_kind"]: item for item in batch["items"]}
        approved = json.loads(
            self.run_cli(
                "maintain-batch-approve",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
                "--item-id", str(by_kind["lifecycle_retire"]["item_id"]),
                "--item-id", str(by_kind["authority_edit"]["item_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual("approved", approved["status"])

        b_path = self.knowledge / "B.md"
        edited_b = b_path.read_text(encoding="utf-8").replace(
            "Original B.",
            "Newer B edit must win.",
        )
        b_path.write_text(edited_b, encoding="utf-8")

        executed = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )

        self.assertEqual("partial", executed["status"])
        result_by_kind = {
            item["item_kind"]: item
            for item in executed["items"]
        }
        self.assertEqual("stale", result_by_kind["lifecycle_retire"]["status"])
        self.assertEqual("succeeded", result_by_kind["authority_edit"]["status"])

        self.assertEqual("current", self.lifecycle(self.ids["B.md"]))
        self.assertEqual(edited_b, b_path.read_text(encoding="utf-8"))
        self.assertEqual(2, self.object_revision(self.ids["B.md"]))

        c_text = (self.knowledge / "C.md").read_text(encoding="utf-8")
        self.assertIn("owner: new-owner\n", c_text)
        self.assertIn("custom: preserve\n", c_text)
        self.assertIn("<!-- preserve comment -->\n", c_text)
        self.assertEqual(2, self.object_revision(self.ids["C.md"]))

        rerun = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("partial", rerun["status"])
        rerun_by_kind = {
            item["item_kind"]: item
            for item in rerun["items"]
        }
        self.assertEqual("stale", rerun_by_kind["lifecycle_retire"]["status"])
        self.assertEqual("succeeded", rerun_by_kind["authority_edit"]["status"])
        self.assertEqual(2, self.object_revision(self.ids["B.md"]))
        self.assertEqual(2, self.object_revision(self.ids["C.md"]))


if __name__ == "__main__":
    unittest.main()
