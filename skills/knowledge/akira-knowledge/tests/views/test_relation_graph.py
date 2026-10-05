from __future__ import annotations

import json
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest

SKILL_ROOT = Path(__file__).resolve().parents[2]
CLI = SKILL_ROOT / "scripts" / "knowledge.py"


class RelationGraphBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.a_path = self.knowledge / "A.md"
        self.b_path = self.knowledge / "B.md"
        self.a_path.write_text(
            "# A\n\nHuman navigation only: [[B]].\n",
            encoding="utf-8",
        )
        self.b_path.write_text("# B\n\nTarget.\n", encoding="utf-8")
        registered = json.loads(
            self.run_cli(
                "register",
                "--vault", str(self.vault),
                "--scope", "Knowledge",
                "--note", "Knowledge/A.md",
                "--note", "Knowledge/B.md",
                "--default-write-root", "Knowledge",
            ).stdout
        )["registered"]
        self.identities = {
            Path(item["locator"]).name: item["identity"]
            for item in registered
        }

    def tearDown(self) -> None:
        self.tempdir.cleanup()

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    @property
    def graph_dir(self) -> Path:
        return self.vault / "AK Graph"

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

    def approve_relation(
        self,
        *,
        provenance: str = "graph-basis",
        target_external: str | None = None,
    ) -> dict[str, object]:
        args = [
            "relation-propose",
            "--vault", str(self.vault),
            "--source-id", self.identities["A.md"],
            "--type", "supports",
            "--provenance", provenance,
        ]
        if target_external is None:
            args.extend(["--target-id", self.identities["B.md"]])
        else:
            args.extend(["--target-external", target_external])
        candidate = json.loads(self.run_cli(*args).stdout)
        return json.loads(
            self.run_cli(
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", candidate["candidate_id"],
                "--confirmed-approval",
            ).stdout
        )

    def rebuild(self) -> dict[str, object]:
        return json.loads(
            self.run_cli(
                "relation-graph-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )

    def relation_state(self, relation_id: str) -> tuple[object, ...]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
                "FROM relation_records WHERE identity = ?",
                (relation_id,),
            ).fetchone()

    def object_state(self) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, locator, revision, authority_fingerprint "
                "FROM objects ORDER BY identity"
            ).fetchall()

    def test_active_relation_generates_readable_graph_node_without_new_knowledge_object(self) -> None:
        approved = self.approve_relation()
        relation_id = approved["relation_identity"]
        before_relation = self.relation_state(relation_id)
        before_objects = self.object_state()

        payload = self.rebuild()

        self.assertTrue(payload["projection"])
        self.assertEqual(1, payload["relation_count"])
        expected = self.graph_dir / f"relation-{relation_id}.md"
        self.assertTrue(expected.exists())
        text = expected.read_text(encoding="utf-8")
        self.assertIn(f"Relation identity: `{relation_id}`", text)
        self.assertIn("Type: `supports`", text)
        self.assertIn(f"[[Knowledge/A]] (`{self.identities['A.md']}`)", text)
        self.assertIn(f"[[Knowledge/B]] (`{self.identities['B.md']}`)", text)
        self.assertIn("`graph-basis`", text)
        self.assertNotIn("akira_knowledge_id", text)
        self.assertEqual(
            "akira-knowledge-relation-graph:v1\n",
            (self.graph_dir / ".akira-knowledge-projection").read_text(encoding="utf-8"),
        )

        with sqlite3.connect(self.database) as conn:
            relation_as_object = conn.execute(
                "SELECT COUNT(*) FROM objects WHERE identity = ?",
                (relation_id,),
            ).fetchone()[0]
        self.assertEqual(0, relation_as_object)
        self.assertEqual(before_relation, self.relation_state(relation_id))
        self.assertEqual(before_objects, self.object_state())

    def test_rename_move_rebuilds_wikilink_without_advancing_relation_or_object_revision(self) -> None:
        approved = self.approve_relation()
        relation_id = approved["relation_identity"]
        before_relation = self.relation_state(relation_id)
        before_objects = self.object_state()

        moved_dir = self.knowledge / "Moved"
        moved_dir.mkdir()
        moved = moved_dir / "Renamed-B.md"
        self.b_path.rename(moved)

        self.rebuild()

        node = self.graph_dir / f"relation-{relation_id}.md"
        text = node.read_text(encoding="utf-8")
        self.assertIn(f"[[Knowledge/Moved/Renamed-B]] (`{self.identities['B.md']}`)", text)
        self.assertNotIn("[[Knowledge/B]]", text)
        self.assertEqual(before_relation, self.relation_state(relation_id))
        self.assertEqual(before_objects, self.object_state())

    def test_deleted_or_corrupt_projection_rebuilds_from_relation_authority(self) -> None:
        approved = self.approve_relation(provenance="basis-one")
        relation_id = approved["relation_identity"]
        before_relation = self.relation_state(relation_id)
        before_objects = self.object_state()

        self.rebuild()
        node = self.graph_dir / f"relation-{relation_id}.md"
        canonical = node.read_text(encoding="utf-8")

        shutil.rmtree(self.graph_dir)
        self.rebuild()
        node = self.graph_dir / f"relation-{relation_id}.md"
        self.assertEqual(canonical, node.read_text(encoding="utf-8"))

        node.write_text("BROKEN PROJECTION\n", encoding="utf-8")
        self.rebuild()
        self.assertEqual(canonical, node.read_text(encoding="utf-8"))

        self.assertEqual(before_relation, self.relation_state(relation_id))
        self.assertEqual(before_objects, self.object_state())

    def test_revoked_relation_is_removed_from_active_graph_projection(self) -> None:
        approved = self.approve_relation()
        relation_id = approved["relation_identity"]
        self.rebuild()
        node = self.graph_dir / f"relation-{relation_id}.md"
        self.assertTrue(node.exists())

        revoked = json.loads(
            self.run_cli(
                "relation-revoke",
                "--vault", str(self.vault),
                "--relation-id", relation_id,
                "--expected-revision", "1",
                "--confirmed-revoke",
            ).stdout
        )
        self.assertEqual("revoked", revoked["status"])
        self.assertEqual(2, revoked["revision"])

        payload = self.rebuild()

        self.assertEqual(0, payload["relation_count"])
        self.assertFalse(node.exists())
        state = self.relation_state(relation_id)
        self.assertEqual("revoked", state[6])
        self.assertEqual(2, state[5])

    def test_owned_legacy_graph_directory_migrates_to_short_name(self) -> None:
        self.approve_relation()
        self.rebuild()
        legacy_dir = self.vault / "Akira Knowledge Graph"
        self.graph_dir.rename(legacy_dir)

        payload = self.rebuild()

        self.assertEqual("AK Graph", payload["projection_directory"])
        self.assertTrue(self.graph_dir.exists())
        self.assertFalse(legacy_dir.exists())
        self.assertEqual(1, payload["relation_count"])

    def test_unowned_same_name_directory_fails_closed(self) -> None:
        self.approve_relation()
        self.graph_dir.mkdir()
        user_file = self.graph_dir / "USER.md"
        user_file.write_text("USER FILE - MUST SURVIVE\n", encoding="utf-8")
        before_objects = self.object_state()

        failed = self.run_cli(
            "relation-graph-rebuild",
            "--vault", str(self.vault),
            expect=2,
        )

        self.assertIn("Refusing to overwrite unowned graph directory", failed.stderr)
        self.assertEqual("USER FILE - MUST SURVIVE\n", user_file.read_text(encoding="utf-8"))
        self.assertEqual(before_objects, self.object_state())
        self.assertEqual([], list(self.graph_dir.glob("relation-*.md")))

    def test_external_endpoint_is_text_not_fake_local_wikilink(self) -> None:
        approved = self.approve_relation(target_external="doi:10.1000/example")
        relation_id = approved["relation_identity"]

        self.rebuild()

        text = (self.graph_dir / f"relation-{relation_id}.md").read_text(encoding="utf-8")
        self.assertIn("external: `doi:10.1000/example`", text)
        self.assertNotIn("[[doi:10.1000/example]]", text)

    def test_plain_wikilink_without_relation_record_does_not_create_graph_relation(self) -> None:
        payload = self.rebuild()

        self.assertEqual(0, payload["relation_count"])
        self.assertEqual([], list(self.graph_dir.glob("relation-*.md")))
        with sqlite3.connect(self.database) as conn:
            relation_count = conn.execute("SELECT COUNT(*) FROM relation_records").fetchone()[0]
        self.assertEqual(0, relation_count)

    def test_missing_local_endpoint_fails_closed_instead_of_becoming_external(self) -> None:
        approved = self.approve_relation()
        relation_id = approved["relation_identity"]
        before_relation = self.relation_state(relation_id)
        self.b_path.unlink()

        failed = self.run_cli(
            "relation-graph-rebuild",
            "--vault", str(self.vault),
            expect=2,
        )

        self.assertIn("Local relation endpoint cannot resolve", failed.stderr)
        self.assertFalse(self.graph_dir.exists())
        self.assertEqual(before_relation, self.relation_state(relation_id))


if __name__ == "__main__":
    unittest.main()
