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


class RelationRetrievalBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)

        notes = {
            "A.md": "# A\n\nA links to [[B]] for navigation only.\n",
            "B.md": "# B\n\nTarget B.\n",
            "C.md": "# C\n\nSource C.\n",
        }
        for name, text in notes.items():
            (self.knowledge / name).write_text(text, encoding="utf-8")

        args = [
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--default-write-root", "Knowledge",
        ]
        for name in notes:
            args.extend(["--note", f"Knowledge/{name}"])
        payload = json.loads(self.run_cli(*args).stdout)
        self.identities = {
            Path(item["locator"]).name: item["identity"]
            for item in payload["registered"]
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

    def seed_relation(
        self,
        *,
        identity: str,
        source: str,
        relation_type: str,
        target: str,
        provenance: str,
    ) -> None:
        with sqlite3.connect(self.database) as conn:
            conn.execute(
                "INSERT INTO relation_records(identity, source_ref, relation_type, target_ref, provenance, revision) "
                "VALUES (?, ?, ?, ?, ?, 1)",
                (identity, source, relation_type, target, provenance),
            )
            conn.commit()

    def relation_state(self) -> list[tuple[str, str, str, str, str, int]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, revision "
                "FROM relation_records ORDER BY identity"
            ).fetchall()

    def task_relation(
        self,
        *,
        seed: str,
        direction: str,
        relation_type: str | None = None,
        scopes: tuple[str, ...] = (),
    ) -> dict[str, object]:
        args = [
            "retrieve-task",
            "--vault", str(self.vault),
            "--task", "沿已接受关系扩展当前任务知识",
            "--relation-seed", seed,
            "--relation-direction", direction,
        ]
        if relation_type is not None:
            args.extend(["--relation-type", relation_type])
        for scope in scopes:
            args.extend(["--scope", scope])
        return json.loads(self.run_cli(*args).stdout)

    def test_relation_traversal_respects_direction_and_exposes_provenance(self) -> None:
        a = self.identities["A.md"]
        b = self.identities["B.md"]
        c = self.identities["C.md"]
        self.seed_relation(
            identity="01991f4a-7abc-7def-8123-456789abc001",
            source=a,
            relation_type="supports",
            target=b,
            provenance="fixture:accepted:a-supports-b",
        )
        self.seed_relation(
            identity="01991f4a-7abc-7def-8123-456789abc002",
            source=c,
            relation_type="supports",
            target=a,
            provenance="fixture:accepted:c-supports-a",
        )

        before_relations = self.relation_state()
        outgoing = self.task_relation(seed=a, direction="outgoing", relation_type="supports")
        self.assertEqual([b], [item["stable_identity"] for item in outgoing["results"]])
        out_match = outgoing["results"][0]["matches"][0]
        self.assertEqual("relation", out_match["path"])
        self.assertIn("accepted typed relation outgoing expansion", out_match["retrieval_reason"])
        self.assertIn("a-supports-b", out_match["matched_evidence"])
        self.assertEqual("supports", out_match["relation"]["type"])
        self.assertEqual(a, out_match["relation"]["source"])
        self.assertEqual(b, out_match["relation"]["target"])
        self.assertEqual(
            "fixture:accepted:a-supports-b",
            out_match["relation"]["provenance"],
        )

        incoming = self.task_relation(seed=a, direction="incoming", relation_type="supports")
        self.assertEqual([c], [item["stable_identity"] for item in incoming["results"]])
        in_match = incoming["results"][0]["matches"][0]
        self.assertIn("accepted typed relation incoming expansion", in_match["retrieval_reason"])
        self.assertEqual(before_relations, self.relation_state())

    def test_relation_expansion_cannot_bypass_retrieval_scope(self) -> None:
        a = self.identities["A.md"]
        material = json.loads(
            self.run_cli(
                "capture",
                "--vault", str(self.vault),
                "--confirmed-intent",
                "--note", "RelationMaterialToken",
            ).stdout
        )
        self.seed_relation(
            identity="01991f4a-7abc-7def-8123-456789abc003",
            source=a,
            relation_type="references",
            target=material["identity"],
            provenance="fixture:accepted:a-references-material",
        )

        default_scope = self.task_relation(
            seed=a,
            direction="outgoing",
            relation_type="references",
        )
        self.assertEqual(["current"], default_scope["scope"])
        self.assertEqual([], default_scope["results"])

        expanded_scope = self.task_relation(
            seed=a,
            direction="outgoing",
            relation_type="references",
            scopes=("current", "material"),
        )
        self.assertEqual(["current", "material"], expanded_scope["scope"])
        self.assertEqual(
            [material["identity"]],
            [item["stable_identity"] for item in expanded_scope["results"]],
        )
        self.assertEqual(
            "material_record",
            expanded_scope["results"][0]["object_kind"],
        )

    def test_wikilink_is_not_upgraded_to_typed_relation(self) -> None:
        a = self.identities["A.md"]
        b = self.identities["B.md"]

        payload = self.task_relation(seed=a, direction="outgoing")

        self.assertEqual([], payload["results"])
        self.assertNotIn(
            b,
            [item["stable_identity"] for item in payload["results"]],
        )
        with sqlite3.connect(self.database) as conn:
            relation_count = conn.execute(
                "SELECT COUNT(*) FROM relation_records"
            ).fetchone()[0]
        self.assertEqual(0, relation_count)

    def test_zero_relation_is_a_normal_empty_expansion(self) -> None:
        c = self.identities["C.md"]

        payload = self.task_relation(
            seed=c,
            direction="outgoing",
            relation_type="supports",
        )

        self.assertEqual(["current"], payload["scope"])
        self.assertEqual("outgoing", payload["retrieval_plan"]["paths"][0]["direction"])
        self.assertEqual([], payload["results"])


if __name__ == "__main__":
    unittest.main()
