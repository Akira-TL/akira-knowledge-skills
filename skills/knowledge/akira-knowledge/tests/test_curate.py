from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[1]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class CurateBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        root = self.vault / "Knowledge"
        root.mkdir(parents=True)
        seed = root / "Existing.md"
        seed.write_text("existing\n", encoding="utf-8")
        self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Existing.md",
            "--default-write-root", "Knowledge",
        )

    def tearDown(self) -> None:
        self.tempdir.cleanup()

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

    def capture(self, note: str) -> dict[str, object]:
        result = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--confirmed-intent",
            "--note", note,
        )
        return json.loads(result.stdout)

    def propose_create(self, material_ids: list[str], body: str) -> dict[str, object]:
        args = ["curate-propose", "--vault", str(self.vault)]
        for identity in material_ids:
            args.extend(["--material-id", identity])
        args.extend(["--body", body])
        return json.loads(self.run_cli(*args).stdout)

    def approve(self, proposal_id: str, *, expect: int = 0) -> subprocess.CompletedProcess[str]:
        return self.run_cli(
            "curate-approve",
            "--vault", str(self.vault),
            "--proposal-id", proposal_id,
            "--confirmed-approval",
            expect=expect,
        )

    def test_materials_to_proposal_to_approved_knowledge_asset(self) -> None:
        first = self.capture("材料一")
        second = self.capture("材料二")
        body = "# 长期知识\n\n这是用户将要批准的完整正文。\n"

        proposal = self.propose_create([first["identity"], second["identity"]], body)
        self.assertEqual("pending", proposal["status"])
        self.assertEqual("create", proposal["proposal_kind"])
        self.assertEqual(body, proposal["proposed_body"])
        self.assertEqual([], list((self.vault / "Knowledge").glob("知识-*.md")))

        approved = json.loads(self.approve(proposal["proposal_id"]).stdout)
        asset = self.vault / approved["asset_locator"]
        text = asset.read_text(encoding="utf-8")
        self.assertIn(f"akira_knowledge_id: {approved['asset_identity']}\n", text)
        self.assertIn("akira_knowledge_kind: knowledge_asset\n", text)
        self.assertTrue(text.endswith(body))
        self.assertEqual(1, approved["revision"])
        self.assertTrue((self.vault / first["locator"]).exists())
        self.assertTrue((self.vault / second["locator"]).exists())

        for material in (first, second):
            material_text = (self.vault / material["locator"]).read_text(encoding="utf-8")
            self.assertIn("akira_knowledge_status: 已处理\n", material_text)
            self.assertEqual(2, approved["material_revisions"][material["identity"]])

        with sqlite3.connect(self.vault / ".akira-knowledge" / "knowledge.sqlite") as conn:
            proposal_row = conn.execute(
                "SELECT status, result_identity FROM proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()
            links = conn.execute(
                "SELECT material_identity, material_basis_revision FROM knowledge_asset_materials "
                "WHERE asset_identity = ? ORDER BY material_identity",
                (approved["asset_identity"],),
            ).fetchall()
        self.assertEqual(("applied", approved["asset_identity"]), proposal_row)
        self.assertEqual(2, len(links))
        self.assertEqual({1}, {row[1] for row in links})

    def test_unapproved_proposal_does_not_write_knowledge_authority(self) -> None:
        material = self.capture("等待用户批准")
        proposal = self.propose_create([material["identity"]], "候选正文")

        result = self.run_cli(
            "curate-approve",
            "--vault", str(self.vault),
            "--proposal-id", proposal["proposal_id"],
            expect=2,
        )
        self.assertIn("explicit user approval", result.stderr)
        self.assertEqual([], list((self.vault / "Knowledge").glob("知识-*.md")))
        with sqlite3.connect(self.vault / ".akira-knowledge" / "knowledge.sqlite") as conn:
            proposal_status = conn.execute(
                "SELECT status FROM proposals WHERE proposal_id = ?",
                (proposal["proposal_id"],),
            ).fetchone()[0]
            material_status = conn.execute(
                "SELECT status FROM material_records WHERE identity = ?",
                (material["identity"],),
            ).fetchone()[0]
        self.assertEqual("pending", proposal_status)
        self.assertEqual("待处理", material_status)

    def test_rejected_proposal_does_not_change_authority_or_material_state(self) -> None:
        material = self.capture("不会被批准的材料")
        material_path = self.vault / material["locator"]
        before = material_path.read_text(encoding="utf-8")
        proposal = self.propose_create([material["identity"]], "不会落地的正文")

        result = self.run_cli(
            "curate-reject",
            "--vault", str(self.vault),
            "--proposal-id", proposal["proposal_id"],
            "--confirmed-rejection",
        )
        payload = json.loads(result.stdout)
        self.assertEqual("rejected", payload["status"])
        self.assertEqual(before, material_path.read_text(encoding="utf-8"))
        self.assertEqual([], list((self.vault / "Knowledge").glob("知识-*.md")))

        with sqlite3.connect(self.vault / ".akira-knowledge" / "knowledge.sqlite") as conn:
            status = conn.execute(
                "SELECT status FROM material_records WHERE identity = ?",
                (material["identity"],),
            ).fetchone()[0]
        self.assertEqual("待处理", status)

    def test_update_proposal_is_candidate_only_until_revision_safe_workflow(self) -> None:
        first_material = self.capture("用于创建初始知识")
        create = self.propose_create([first_material["identity"]], "初始正文")
        created = json.loads(self.approve(create["proposal_id"]).stdout)
        asset_path = self.vault / created["asset_locator"]
        before = asset_path.read_text(encoding="utf-8")

        update_material = self.capture("用于更新知识的新材料")
        args = [
            "curate-propose",
            "--vault", str(self.vault),
            "--material-id", update_material["identity"],
            "--target-id", created["asset_identity"],
            "--body", "更新后的候选正文",
        ]
        proposal = json.loads(self.run_cli(*args).stdout)
        self.assertEqual("update", proposal["proposal_kind"])
        self.assertEqual(created["asset_identity"], proposal["target_identity"])
        self.assertEqual(1, proposal["base_revision"])
        self.assertEqual(before, asset_path.read_text(encoding="utf-8"))

        failed = self.approve(proposal["proposal_id"], expect=2)
        self.assertIn("revision-safe update workflow", failed.stderr)
        self.assertEqual(before, asset_path.read_text(encoding="utf-8"))
        self.assertEqual(1, len(list((self.vault / "Knowledge").glob("知识-*.md"))))


if __name__ == "__main__":
    unittest.main()
