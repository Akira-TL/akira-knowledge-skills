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


class Release04BlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    def run_cli(
        self,
        *args: str,
        expect: int = 0,
    ) -> subprocess.CompletedProcess[str]:
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

    def register(self, notes: dict[str, str]) -> dict[str, str]:
        for name, text in notes.items():
            path = self.knowledge / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        args = [
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--default-write-root", "Knowledge",
        ]
        for name in notes:
            args += ["--note", f"Knowledge/{name}"]
        payload = json.loads(self.run_cli(*args).stdout)
        return {
            Path(item["locator"]).name: str(item["identity"])
            for item in payload["registered"]
        }

    def revision_snapshot(
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

    def create_source_backed_asset(self) -> tuple[str, str]:
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Initial source-backed evidence.",
                "--source", "https://example.org/release-04-source",
            ).stdout
        )
        proposal = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(material["identity"]),
                "--body", "# Source-backed\n\nVersion one knowledge.\n",
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
        return str(created["asset_identity"]), str(created["asset_locator"])

    def test_complete_04_public_maintenance_gate(self) -> None:
        ids = self.register(
            {
                "Nav-A.md": "# Nav A\n\n[[Nav-B]]\n",
                "Nav-B.md": "# Nav B\n\nNo outward navigation.\n",
                "Orphan.md": "# Orphan\n\nNo links.\n",
                "Superseded.md": "# Superseded\n\nOld knowledge.\n",
                "Replacement.md": "# Replacement\n\nNew knowledge.\n",
                "Batch-Stale.md": "# Batch stale\n\nOriginal.\n",
                "Batch-Fresh.md": (
                    "---\nowner: old\ncustom: preserve\n---\n"
                    "# Batch fresh\n\nKeep this body.\n"
                    "<!-- preserve comment -->\n"
                ),
            }
        )

        relation_candidate = json.loads(
            self.run_cli(
                "relation-propose",
                "--vault", str(self.vault),
                "--source-id", ids["Nav-A.md"],
                "--type", "supports",
                "--target-id", ids["Nav-B.md"],
                "--provenance", "0.4 release-gate relation evidence.",
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
        self.assertEqual("accepted", relation["status"])

        before_health = self.revision_snapshot()
        health = json.loads(
            self.run_cli(
                "maintain-health-scan",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertIn(
            ids["Orphan.md"],
            {item["identity"] for item in health["orphan"]},
        )
        self.assertIn(
            ids["Nav-B.md"],
            {item["identity"] for item in health["dead_end"]},
        )
        self.assertEqual(before_health, self.revision_snapshot())

        source_id, source_locator = self.create_source_backed_asset()

        unknown = json.loads(
            self.run_cli(
                "maintain-review-source",
                "--vault", str(self.vault),
                "--identity", source_id,
                "--source", "https://example.org/release-04-source",
                "--unknown",
                "--evidence", "External Source cannot be verified right now.",
            ).stdout
        )
        self.assertEqual("unknown", unknown["source_state"])
        self.assertIsNone(unknown["candidate"])
        self.assertIsNone(unknown["basis"])

        reviewed = json.loads(
            self.run_cli(
                "maintain-review-source",
                "--vault", str(self.vault),
                "--identity", source_id,
                "--source", "https://example.org/release-04-source",
                "--basis-source-id", "doi:10.1000/release-04",
                "--basis-revision", "v1",
                "--basis-fingerprint", "sha256:old",
                "--observed-source-id", "doi:10.1000/release-04",
                "--observed-revision", "v2",
                "--observed-fingerprint", "sha256:new",
                "--evidence", "Verified revision v2 and changed content fingerprint.",
            ).stdout
        )
        source_candidate_id = str(reviewed["candidate"]["candidate_id"])
        self.assertEqual("pending", reviewed["candidate"]["status"])

        update_material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "Verified revision v2 update material.",
                "--source", "https://example.org/release-04-source",
            ).stdout
        )
        update = json.loads(
            self.run_cli(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", str(update_material["identity"]),
                "--target-id", source_id,
                "--base-revision", "1",
                "--body", "# Source-backed\n\nVersion two knowledge.\n",
            ).stdout
        )
        applied_update = json.loads(
            self.run_cli(
                "maintain-apply-update",
                "--vault", str(self.vault),
                "--proposal-id", str(update["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(2, applied_update["revision"])
        self.assertIn(
            "Version two knowledge.",
            (self.vault / source_locator).read_text(encoding="utf-8"),
        )
        stale_source = json.loads(
            self.run_cli(
                "maintain-inspect-review-candidate",
                "--vault", str(self.vault),
                "--candidate-id", source_candidate_id,
            ).stdout
        )
        self.assertEqual("stale", stale_source["status"])

        retire = json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", ids["Orphan.md"],
                "--base-revision", "1",
                "--reason", "No longer part of current knowledge.",
            ).stdout
        )
        retired = json.loads(
            self.run_cli(
                "maintain-apply-retire",
                "--vault", str(self.vault),
                "--proposal-id", str(retire["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(ids["Orphan.md"], retired["stable_identity"])
        self.assertEqual(2, retired["revision"])
        retired_exact = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--scope", "retired",
                "--identity", ids["Orphan.md"],
            ).stdout
        )
        self.assertEqual(
            ids["Orphan.md"],
            retired_exact["result"]["stable_identity"],
        )

        supersede = json.loads(
            self.run_cli(
                "maintain-propose-supersede",
                "--vault", str(self.vault),
                "--identity", ids["Superseded.md"],
                "--base-revision", "1",
                "--replacement-id", ids["Replacement.md"],
                "--replacement-revision", "1",
                "--reason", "Replacement is now canonical for future use.",
            ).stdout
        )
        superseded = json.loads(
            self.run_cli(
                "maintain-apply-supersede",
                "--vault", str(self.vault),
                "--proposal-id", str(supersede["proposal_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(ids["Superseded.md"], superseded["stable_identity"])
        self.assertEqual(
            ids["Replacement.md"],
            superseded["replacement_identity"],
        )
        self.assertEqual(2, superseded["revision"])
        self.assertEqual(1, superseded["replacement_revision"])
        old_exact = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--scope", "superseded",
                "--identity", ids["Superseded.md"],
            ).stdout
        )
        replacement_exact = json.loads(
            self.run_cli(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--identity", ids["Replacement.md"],
            ).stdout
        )
        self.assertEqual(
            ids["Superseded.md"],
            old_exact["result"]["stable_identity"],
        )
        self.assertEqual(
            ids["Replacement.md"],
            replacement_exact["result"]["stable_identity"],
        )

        batch_retire = json.loads(
            self.run_cli(
                "maintain-propose-retire",
                "--vault", str(self.vault),
                "--identity", ids["Batch-Stale.md"],
                "--base-revision", "1",
                "--reason", "Retire through batch if still fresh.",
            ).stdout
        )
        batch_edit = json.loads(
            self.run_cli(
                "maintain-propose-authority-edit",
                "--vault", str(self.vault),
                "--identity", ids["Batch-Fresh.md"],
                "--base-revision", "1",
                "--set-property", "owner", "new-owner",
                "--reason", "Approved property correction.",
            ).stdout
        )
        batch = json.loads(
            self.run_cli(
                "maintain-batch-create",
                "--vault", str(self.vault),
                "--retire-proposal", str(batch_retire["proposal_id"]),
                "--authority-edit-proposal", str(batch_edit["proposal_id"]),
            ).stdout
        )
        approved = json.loads(
            self.run_cli(
                "maintain-batch-approve",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
                "--item-id", str(batch["items"][0]["item_id"]),
                "--item-id", str(batch["items"][1]["item_id"]),
                "--confirmed-approval",
            ).stdout
        )
        self.assertTrue(
            all(item["approval_result"] == "approved" for item in approved["items"])
        )

        stale_path = self.knowledge / "Batch-Stale.md"
        stale_path.write_text(
            stale_path.read_text(encoding="utf-8").replace(
                "Original.",
                "Newer direct edit must survive.",
            ),
            encoding="utf-8",
        )
        batch_result = json.loads(
            self.run_cli(
                "maintain-batch-execute",
                "--vault", str(self.vault),
                "--batch-id", str(batch["batch_id"]),
            ).stdout
        )
        self.assertEqual("partial", batch_result["status"])
        by_kind = {item["item_kind"]: item for item in batch_result["items"]}
        self.assertEqual("stale", by_kind["lifecycle_retire"]["status"])
        self.assertEqual("succeeded", by_kind["authority_edit"]["status"])
        self.assertIn(
            "Newer direct edit must survive.",
            stale_path.read_text(encoding="utf-8"),
        )
        fresh_text = (self.knowledge / "Batch-Fresh.md").read_text(encoding="utf-8")
        self.assertIn("owner: new-owner\n", fresh_text)
        self.assertIn("custom: preserve\n", fresh_text)
        self.assertIn("<!-- preserve comment -->\n", fresh_text)

        before_projection = self.revision_snapshot()
        self.run_cli("maintain-health-scan", "--vault", str(self.vault))
        self.run_cli("views-rebuild", "--vault", str(self.vault))
        self.run_cli("relation-graph-rebuild", "--vault", str(self.vault))
        self.assertEqual(before_projection, self.revision_snapshot())


if __name__ == "__main__":
    unittest.main()
