from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROUTER_ROOT = Path(__file__).resolve().parents[1]
CLI = ROUTER_ROOT / "scripts" / "knowledge.py"
SKILLS_ROOT = ROUTER_ROOT.parent


class RouterKnowledgeLoopBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        knowledge = self.vault / "Knowledge"
        knowledge.mkdir(parents=True)
        self.seed = knowledge / "Existing.md"
        self.seed.write_text("# Existing\nBootstrap seed.\n", encoding="utf-8")

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    def run_router(self, *args: str, expect: int = 0) -> subprocess.CompletedProcess[str]:
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

    def test_primary_router_executor_completes_the_full_0_1_knowledge_loop(self) -> None:
        inspected = json.loads(
            self.run_router("inspect", "--vault", str(self.vault)).stdout
        )
        self.assertTrue(inspected["ok"])
        self.assertFalse(inspected["system_exists"])

        self.run_router(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Existing.md",
            "--default-write-root", "Knowledge",
        )

        captured = json.loads(
            self.run_router(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "这是完整闭环中的原始材料。",
                "--source", "https://example.org/router-loop",
            ).stdout
        )
        self.assertEqual("material_record", captured["kind"])

        proposal = json.loads(
            self.run_router(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", captured["identity"],
                "--body", "# Router Loop Knowledge\n\nIntegratedKnowledgeToken.\n",
            ).stdout
        )
        self.assertEqual("pending", proposal["status"])

        created = json.loads(
            self.run_router(
                "curate-approve",
                "--vault", str(self.vault),
                "--proposal-id", proposal["proposal_id"],
                "--confirmed-approval",
            ).stdout
        )
        asset_identity = created["asset_identity"]

        found = json.loads(
            self.run_router(
                "retrieve-full-text",
                "--vault", str(self.vault),
                "--query", "IntegratedKnowledgeToken",
            ).stdout
        )
        self.assertEqual(asset_identity, found["results"][0]["stable_identity"])

        update_material = json.loads(
            self.run_router(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "这是更新长期知识的新材料。",
            ).stdout
        )
        synced = json.loads(
            self.run_router(
                "maintain-sync",
                "--vault", str(self.vault),
                "--identity", asset_identity,
            ).stdout
        )
        update_proposal = json.loads(
            self.run_router(
                "curate-propose",
                "--vault", str(self.vault),
                "--material-id", update_material["identity"],
                "--target-id", asset_identity,
                "--base-revision", str(synced["revision"]),
                "--body", "# Router Loop Knowledge\n\nUpdatedKnowledgeToken.\n",
            ).stdout
        )
        updated = json.loads(
            self.run_router(
                "maintain-apply-update",
                "--vault", str(self.vault),
                "--proposal-id", update_proposal["proposal_id"],
                "--confirmed-approval",
            ).stdout
        )
        self.assertEqual(asset_identity, updated["stable_identity"])

        exact = json.loads(
            self.run_router(
                "retrieve-exact",
                "--vault", str(self.vault),
                "--identity", asset_identity,
            ).stdout
        )
        self.assertIn("UpdatedKnowledgeToken", exact["result"]["authority_text"])
        self.assertEqual(updated["revision"], 2)

    def test_router_package_has_four_domain_skills_and_one_shared_executor(self) -> None:
        router_text = (ROUTER_ROOT / "SKILL.md").read_text(encoding="utf-8")
        domain_skills = (
            "knowledge-capture",
            "knowledge-curate",
            "knowledge-retrieve",
            "knowledge-maintain",
        )
        for name in domain_skills:
            skill_dir = SKILLS_ROOT / name
            skill_file = skill_dir / "SKILL.md"
            self.assertTrue(skill_file.is_file(), name)
            self.assertIn(name, router_text)
            self.assertIn(
                "<akira-knowledge-skill-root>/scripts/knowledge.py",
                skill_file.read_text(encoding="utf-8"),
            )
            self.assertEqual([], list(skill_dir.rglob("*.py")))

        self.assertFalse((SKILLS_ROOT / "knowledge-obsidian").exists())
        self.assertIn("obsidian-cli", router_text)
        self.assertIn("fail closed", router_text)
        self.assertIn("filesystem fallback", router_text)


if __name__ == "__main__":
    unittest.main()
