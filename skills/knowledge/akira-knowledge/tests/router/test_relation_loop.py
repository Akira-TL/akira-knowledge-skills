from __future__ import annotations

import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest

ROUTER_ROOT = Path(__file__).resolve().parents[2]
CLI = ROUTER_ROOT / "scripts" / "knowledge.py"
SKILLS_ROOT = ROUTER_ROOT.parent


class RouterRelationLoopBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)

        self.paths = {}
        contents = {
            "A.md": (
                "---\n"
                "topic: network\n"
                "tags:\n"
                "  - shared\n"
                "---\n"
                "# A\n\n"
                "Ordinary navigation [[B]]. SharedRelationToken.\n"
            ),
            "B.md": (
                "---\n"
                "topic: network\n"
                "tags:\n"
                "  - shared\n"
                "---\n"
                "# B\n\n"
                "B Authority body. SharedRelationToken.\n"
            ),
            "C.md": "# C\n\nC Authority body.\n",
        }
        for name, content in contents.items():
            path = self.knowledge / name
            path.write_text(content, encoding="utf-8")
            self.paths[name] = path

        args = [
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--default-write-root", "Knowledge",
        ]
        for name in contents:
            args.extend(["--note", f"Knowledge/{name}"])
        registered = json.loads(self.run_router(*args).stdout)["registered"]
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
        return self.vault / "Akira Knowledge Graph"

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

    def candidate_count(self) -> int:
        with sqlite3.connect(self.database) as conn:
            return conn.execute("SELECT COUNT(*) FROM relation_candidates").fetchone()[0]

    def relation_rows(self) -> list[tuple[object, ...]]:
        with sqlite3.connect(self.database) as conn:
            return conn.execute(
                "SELECT identity, source_ref, relation_type, target_ref, provenance, revision, status "
                "FROM relation_records ORDER BY identity"
            ).fetchall()

    def propose(
        self,
        *,
        source: str,
        relation_type: str,
        target: str | None = None,
        target_external: str | None = None,
        provenance: str,
    ) -> dict[str, object]:
        args = [
            "relation-propose",
            "--vault", str(self.vault),
            "--source-id", source,
            "--type", relation_type,
            "--provenance", provenance,
        ]
        if target is not None:
            args.extend(["--target-id", target])
        else:
            assert target_external is not None
            args.extend(["--target-external", target_external])
        return json.loads(self.run_router(*args).stdout)

    def approve(self, candidate_id: str) -> dict[str, object]:
        return json.loads(
            self.run_router(
                "relation-approve",
                "--vault", str(self.vault),
                "--candidate-id", candidate_id,
                "--confirmed-approval",
            ).stdout
        )

    def test_primary_router_executor_completes_full_03_relation_loop(self) -> None:
        a = self.identities["A.md"]
        b = self.identities["B.md"]

        self.assertEqual(0, self.candidate_count())
        self.assertEqual([], self.relation_rows())

        # Ordinary wikilink/tag/full-text similarity does not auto-create governance state.
        self.run_router(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "SharedRelationToken",
        )
        self.assertEqual(0, self.candidate_count())
        self.assertEqual([], self.relation_rows())

        pending = self.propose(
            source=a,
            relation_type="supports",
            target=b,
            provenance="pending-basis",
        )
        self.assertEqual("pending", pending["status"])

        pending_traversal = json.loads(
            self.run_router(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "pending must not be consumed",
                "--relation-seed", a,
                "--relation-direction", "outgoing",
            ).stdout
        )
        self.assertEqual([], pending_traversal["results"])
        pending_graph = json.loads(
            self.run_router(
                "relation-graph-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(0, pending_graph["relation_count"])

        rejected = json.loads(
            self.run_router(
                "relation-reject",
                "--vault", str(self.vault),
                "--candidate-id", pending["candidate_id"],
                "--confirmed-rejection",
            ).stdout
        )
        self.assertEqual("rejected", rejected["status"])
        self.assertEqual([], self.relation_rows())

        candidate = self.propose(
            source=a,
            relation_type="supports",
            target=b,
            provenance="approved-basis",
        )
        approved = self.approve(candidate["candidate_id"])
        relation_id = approved["relation_identity"]
        self.assertEqual("accepted", approved["status"])
        self.assertEqual(1, approved["relation_revision"])

        traversal = json.loads(
            self.run_router(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "follow approved relation",
                "--relation-seed", a,
                "--relation-direction", "outgoing",
                "--relation-type", "supports",
            ).stdout
        )
        self.assertEqual([b], [item["stable_identity"] for item in traversal["results"]])
        relation_meta = traversal["results"][0]["matches"][0]["relation"]
        self.assertEqual(relation_id, relation_meta["identity"])
        self.assertEqual(["approved-basis"], relation_meta["provenance_entries"])

        graph = json.loads(
            self.run_router(
                "relation-graph-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(1, graph["relation_count"])
        node = self.graph_dir / f"relation-{relation_id}.md"
        node_text = node.read_text(encoding="utf-8")
        self.assertIn("[[Knowledge/A]]", node_text)
        self.assertIn("[[Knowledge/B]]", node_text)
        self.assertIn("approved-basis", node_text)

        revoked = json.loads(
            self.run_router(
                "relation-revoke",
                "--vault", str(self.vault),
                "--relation-id", relation_id,
                "--expected-revision", "1",
                "--confirmed-revoke",
            ).stdout
        )
        self.assertEqual("revoked", revoked["status"])
        self.assertEqual(2, revoked["revision"])

        after_revoke = json.loads(
            self.run_router(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "revoked relation must disappear",
                "--relation-seed", a,
                "--relation-direction", "outgoing",
            ).stdout
        )
        self.assertEqual([], after_revoke["results"])

        graph_after_revoke = json.loads(
            self.run_router(
                "relation-graph-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(0, graph_after_revoke["relation_count"])
        self.assertFalse(node.exists())

    def test_stale_external_and_no_automatic_relation_semantics(self) -> None:
        a = self.identities["A.md"]
        b = self.identities["B.md"]
        c = self.identities["C.md"]

        stale_candidate = self.propose(
            source=b,
            relation_type="supports",
            target=c,
            provenance="stale-basis",
        )
        current = self.paths["B.md"].read_text(encoding="utf-8")
        self.paths["B.md"].write_text(
            current.replace("B Authority body.", "B changed after candidate."),
            encoding="utf-8",
        )
        stale = json.loads(
            self.run_router(
                "relation-inspect",
                "--vault", str(self.vault),
                "--candidate-id", stale_candidate["candidate_id"],
            ).stdout
        )
        self.assertEqual("stale", stale["status"])

        external_candidate = self.propose(
            source=a,
            relation_type="references",
            target_external="doi:10.1000/example",
            provenance="external-basis",
        )
        external_relation = self.approve(external_candidate["candidate_id"])
        external_id = external_relation["relation_identity"]

        traversal = json.loads(
            self.run_router(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "external endpoint is not a local object",
                "--relation-seed", a,
                "--relation-direction", "outgoing",
                "--relation-type", "references",
            ).stdout
        )
        self.assertEqual([], traversal["results"])

        graph = json.loads(
            self.run_router(
                "relation-graph-rebuild",
                "--vault", str(self.vault),
            ).stdout
        )
        self.assertEqual(1, graph["relation_count"])
        external_node = self.graph_dir / f"relation-{external_id}.md"
        text = external_node.read_text(encoding="utf-8")
        self.assertIn("external: `doi:10.1000/example`", text)
        self.assertNotIn("[[doi:10.1000/example]]", text)

        rows = self.relation_rows()
        self.assertEqual(1, len(rows))
        self.assertEqual(
            (a, "references", "doi:10.1000/example"),
            (rows[0][1], rows[0][2], rows[0][3]),
        )

        # No automatic inverse/symmetric/transitive relation is manufactured.
        reverse = json.loads(
            self.run_router(
                "retrieve-task",
                "--vault", str(self.vault),
                "--task", "no automatic reverse",
                "--relation-seed", b,
                "--relation-direction", "outgoing",
                "--relation-type", "supports",
            ).stdout
        )
        self.assertEqual([], reverse["results"])
        with sqlite3.connect(self.database) as conn:
            stale_status = conn.execute(
                "SELECT status FROM relation_candidates WHERE candidate_id = ?",
                (stale_candidate["candidate_id"],),
            ).fetchone()[0]
        self.assertEqual("stale", stale_status)

    def test_router_still_uses_only_four_domain_skills(self) -> None:
        router_text = (ROUTER_ROOT / "SKILL.md").read_text(encoding="utf-8")
        expected = {
            "knowledge-capture",
            "knowledge-curate",
            "knowledge-retrieve",
            "knowledge-maintain",
        }
        for name in expected:
            self.assertTrue((SKILLS_ROOT / name / "SKILL.md").is_file())
            self.assertIn(name, router_text)

        for forbidden in (
            "knowledge-network",
            "knowledge-graph",
            "knowledge-relation",
        ):
            self.assertFalse((SKILLS_ROOT / forbidden).exists())


if __name__ == "__main__":
    unittest.main()
