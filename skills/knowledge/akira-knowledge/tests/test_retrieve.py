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


class RetrievalBlackBoxTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.vault = Path(self.tempdir.name) / "Vault"
        self.knowledge = self.vault / "Knowledge"
        self.knowledge.mkdir(parents=True)
        self.seed = self.knowledge / "Existing.md"
        self.seed.write_text(
            "---\n"
            "topic: statistics\n"
            "audience: advanced\n"
            "---\n"
            "# Existing Knowledge\n\n"
            "BayesianEvidence is the searchable body token.\n",
            encoding="utf-8",
        )
        registered = self.run_cli(
            "register",
            "--vault", str(self.vault),
            "--scope", "Knowledge",
            "--note", "Knowledge/Existing.md",
            "--default-write-root", "Knowledge",
        )
        self.identity = json.loads(registered.stdout)["registered"][0]["identity"]

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

    @property
    def database(self) -> Path:
        return self.vault / ".akira-knowledge" / "knowledge.sqlite"

    def capture(self, note: str) -> dict[str, object]:
        result = self.run_cli(
            "capture",
            "--vault", str(self.vault),
            "--confirmed-intent",
            "--note", note,
        )
        return json.loads(result.stdout)

    def test_exact_resolves_current_locator_after_rename_without_writing_registry(self) -> None:
        renamed = self.knowledge / "Renamed.md"
        self.seed.rename(renamed)

        result = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", self.identity,
        )
        payload = json.loads(result.stdout)
        item = payload["result"]

        self.assertEqual(self.identity, item["stable_identity"])
        self.assertEqual("knowledge_asset", item["object_kind"])
        self.assertEqual("Knowledge/Renamed.md", item["canonical_locator"])
        self.assertIn("stable-identity", item["retrieval_reason"])
        self.assertIn("BayesianEvidence", item["authority_text"])

        with sqlite3.connect(self.database) as conn:
            locator, revision = conn.execute(
                "SELECT locator, revision FROM objects WHERE identity = ?",
                (self.identity,),
            ).fetchone()
        self.assertEqual("Knowledge/Existing.md", locator)
        self.assertEqual(1, revision)

    def test_filter_supports_kind_material_status_and_user_authority_property(self) -> None:
        material = self.capture("FilterMaterialToken")

        property_result = self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--kind", "knowledge_asset",
            "--property", "topic=statistics",
            "--property", "audience=advanced",
        )
        property_payload = json.loads(property_result.stdout)
        self.assertEqual(1, len(property_payload["results"]))
        item = property_payload["results"][0]
        self.assertEqual(self.identity, item["stable_identity"])
        self.assertEqual("Knowledge/Existing.md", item["canonical_locator"])
        self.assertIn("topic=statistics", item["matched_evidence"])
        self.assertIn("authoritative property filter", item["retrieval_reason"])

        status_result = self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--scope", "material",
            "--kind", "material_record",
            "--status", "待处理",
        )
        status_payload = json.loads(status_result.stdout)
        self.assertEqual(1, len(status_payload["results"]))
        material_item = status_payload["results"][0]
        self.assertEqual(material["identity"], material_item["stable_identity"])
        self.assertEqual("material_record", material_item["object_kind"])
        self.assertIn("material status=待处理", material_item["matched_evidence"])

    def test_scope_defaults_to_current_and_explicit_material_scope_is_shared(self) -> None:
        material = self.capture("ScopeMaterialToken")

        with sqlite3.connect(self.database) as conn:
            before_revisions = dict(conn.execute("SELECT identity, revision FROM objects").fetchall())

        exact_default = self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--identity", material["identity"],
            expect=2,
        )
        self.assertIn("outside requested retrieval scope", exact_default.stderr)
        exact_material = json.loads(self.run_cli(
            "retrieve-exact",
            "--vault", str(self.vault),
            "--scope", "material",
            "--identity", material["identity"],
        ).stdout)
        self.assertEqual(["material"], exact_material["scope"])
        self.assertEqual(material["identity"], exact_material["result"]["stable_identity"])

        filter_default = json.loads(self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--kind", "material_record",
            "--status", "待处理",
        ).stdout)
        self.assertEqual(["current"], filter_default["scope"])
        self.assertEqual([], filter_default["results"])
        filter_material = json.loads(self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--scope", "material",
            "--kind", "material_record",
            "--status", "待处理",
        ).stdout)
        self.assertEqual(["material"], filter_material["scope"])
        self.assertEqual(material["identity"], filter_material["results"][0]["stable_identity"])

        full_text_default = json.loads(self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "ScopeMaterialToken",
        ).stdout)
        self.assertEqual(["current"], full_text_default["scope"])
        self.assertEqual([], full_text_default["results"])
        full_text_material = json.loads(self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--scope", "material",
            "--query", "ScopeMaterialToken",
        ).stdout)
        self.assertEqual(["material"], full_text_material["scope"])
        self.assertEqual(material["identity"], full_text_material["results"][0]["stable_identity"])

        combined = json.loads(self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--scope", "current",
            "--scope", "material",
        ).stdout)
        self.assertEqual(["current", "material"], combined["scope"])
        self.assertEqual({self.identity, material["identity"]}, {
            item["stable_identity"] for item in combined["results"]
        })

        with sqlite3.connect(self.database) as conn:
            after_revisions = dict(conn.execute("SELECT identity, revision FROM objects").fetchall())
        self.assertEqual(before_revisions, after_revisions, "retrieval scope must not advance revisions")

    def test_unsupported_future_lifecycle_scope_fails_without_inventing_state(self) -> None:
        before = self.seed.read_bytes()
        with sqlite3.connect(self.database) as conn:
            before_rows = conn.execute(
                "SELECT identity, kind, locator, revision, authority_fingerprint FROM objects ORDER BY identity"
            ).fetchall()

        result = self.run_cli(
            "retrieve-filter",
            "--vault", str(self.vault),
            "--scope", "superseded",
            expect=2,
        )
        self.assertIn("Unsupported retrieval scope: superseded", result.stderr)
        self.assertEqual(before, self.seed.read_bytes())
        with sqlite3.connect(self.database) as conn:
            after_rows = conn.execute(
                "SELECT identity, kind, locator, revision, authority_fingerprint FROM objects ORDER BY identity"
            ).fetchall()
        self.assertEqual(before_rows, after_rows)

    def test_full_text_uses_current_authority_and_rebuilds_when_content_changes(self) -> None:
        original = self.seed.read_text(encoding="utf-8")
        first = self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "BayesianEvidence",
        )
        first_payload = json.loads(first.stdout)
        self.assertEqual("sqlite-fts5", first_payload["projection_mode"])
        self.assertEqual(1, len(first_payload["results"]))
        self.assertEqual(self.identity, first_payload["results"][0]["stable_identity"])
        self.assertIn("BayesianEvidence", first_payload["results"][0]["matched_evidence"])
        self.assertEqual(original, self.seed.read_text(encoding="utf-8"))

        changed = original.replace("BayesianEvidence", "FreshAuthorityToken")
        self.seed.write_text(changed, encoding="utf-8")
        second = self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "FreshAuthorityToken",
        )
        second_payload = json.loads(second.stdout)
        self.assertEqual("sqlite-fts5", second_payload["projection_mode"])
        self.assertEqual(1, len(second_payload["results"]))
        self.assertEqual(self.identity, second_payload["results"][0]["stable_identity"])
        self.assertIn("FreshAuthorityToken", second_payload["results"][0]["authority_text"])
        self.assertEqual(changed, self.seed.read_text(encoding="utf-8"))

        with sqlite3.connect(self.database) as conn:
            revision = conn.execute(
                "SELECT revision FROM objects WHERE identity = ?",
                (self.identity,),
            ).fetchone()[0]
        self.assertEqual(1, revision, "retrieval must not advance Authority revision")

    def test_corrupt_full_text_projection_falls_back_and_explicit_rebuild_repairs_it(self) -> None:
        first = self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "BayesianEvidence",
        )
        self.assertEqual("sqlite-fts5", json.loads(first.stdout)["projection_mode"])

        with sqlite3.connect(self.database) as conn:
            conn.execute("DROP TABLE search_fts")
            conn.execute("CREATE TABLE search_fts(broken TEXT)")
            conn.commit()

        fallback = self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "BayesianEvidence",
        )
        fallback_payload = json.loads(fallback.stdout)
        self.assertEqual("authority-scan-fallback", fallback_payload["projection_mode"])
        self.assertEqual(1, len(fallback_payload["results"]))
        self.assertEqual(self.identity, fallback_payload["results"][0]["stable_identity"])
        self.assertIn("direct Authority scan", fallback_payload["results"][0]["retrieval_reason"])

        rebuilt = self.run_cli(
            "retrieve-rebuild-index",
            "--vault", str(self.vault),
        )
        self.assertEqual(1, json.loads(rebuilt.stdout)["indexed_objects"])

        repaired = self.run_cli(
            "retrieve-full-text",
            "--vault", str(self.vault),
            "--query", "BayesianEvidence",
        )
        repaired_payload = json.loads(repaired.stdout)
        self.assertEqual("sqlite-fts5", repaired_payload["projection_mode"])
        self.assertEqual(self.identity, repaired_payload["results"][0]["stable_identity"])


if __name__ == "__main__":
    unittest.main()
