import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from python.core.model import Change, ChangeSet, Document, Entry, Locator, ModelError, apply_changes
from python.detectors.candidates import AmbiguousCandidate, Candidate, detect_path, resolve
from python.projections.json_projection import ProjectionError, export_bundle, import_bundle


def document() -> Document:
    value = Document(
        source_path="scene.bin",
        source_sha256=hashlib.sha256(b"source").hexdigest(),
        engine_id="example",
        dialect="v1",
        entries=[
            Entry(
                id="scene:0",
                kind="dialogue",
                name="A",
                name_policy="writable",
                message="Hello",
                source_text="Hello",
                locator=Locator("scene.bin", 10, 5),
            ),
            Entry(
                id="scene:1",
                kind="narration",
                message="Narration",
                source_text="Narration",
                name_policy="absent",
                locator=Locator("scene.bin", 15, 9),
            ),
            Entry(
                id="scene:2",
                kind="command",
                message="",
                source_text="",
                message_policy="readonly",
                locator=Locator("scene.bin", 24, 1),
            ),
        ],
    )
    value.validate()
    return value


class ModelTests(unittest.TestCase):
    def test_change_requires_source_and_policy(self):
        doc = document()
        changes = ChangeSet(doc.source_sha256, "doc", (Change("scene:0", "Hello", message="你好", name="乙"),))
        updated = apply_changes(doc, changes)
        self.assertEqual(updated.entries[0].message, "你好")
        self.assertEqual(updated.entries[0].name, "乙")
        self.assertEqual(doc.entries[0].message, "Hello")
        with self.assertRaises(ModelError):
            apply_changes(doc, ChangeSet(doc.source_sha256, "doc", (Change("scene:0", "stale", message="x"),)))

    def test_duplicate_ids_and_readonly_are_rejected(self):
        doc = document()
        duplicate = Entry(id="scene:0", kind="dialogue", message="x", source_text="x")
        doc.entries.append(duplicate)
        with self.assertRaises(ModelError):
            doc.validate()
        with self.assertRaises(ModelError):
            apply_changes(doc.__class__.from_dict(document().to_dict()), ChangeSet(document().source_sha256, "doc", (Change("scene:2", "", message="x"),)))


class ProjectionTests(unittest.TestCase):
    def test_export_import_keeps_identity_and_omits_empty_command(self):
        doc = document()
        rows, manifest = export_bundle(doc)
        self.assertEqual(rows, [{"name": "A", "message": "Hello"}, {"message": "Narration"}])
        rows[0]["message"] = "你好"
        rows[0]["name"] = "乙"
        changes = import_bundle(doc, rows, manifest)
        self.assertEqual(changes.changes[0].entry_id, "scene:0")
        self.assertEqual(changes.changes[0].message, "你好")

    def test_stale_manifest_and_name_policy_fail(self):
        doc = document()
        rows, manifest = export_bundle(doc)
        manifest["source_sha256"] = "0" * 64
        with self.assertRaises(ProjectionError):
            import_bundle(doc, rows, manifest)
        rows, manifest = export_bundle(doc)
        rows[0]["name"] = "非法"
        manifest["rows"][0]["name_policy"] = "readonly"
        with self.assertRaises(ProjectionError):
            import_bundle(doc, rows, manifest)

    def test_projection_and_identity_anchors_are_bound(self):
        doc = document()
        rows, manifest = export_bundle(doc)
        manifest["projection"] = "other"
        with self.assertRaises(ProjectionError):
            import_bundle(doc, rows, manifest)
        rows, manifest = export_bundle(doc)
        manifest["rows"][0]["name"] = "陈旧"
        with self.assertRaises(ProjectionError):
            import_bundle(doc, rows, manifest)

    def test_duplicate_manifest_identity_is_rejected(self):
        doc = document()
        rows, manifest = export_bundle(doc)
        manifest["rows"][1]["entry_id"] = manifest["rows"][0]["entry_id"]
        with self.assertRaises(ProjectionError):
            import_bundle(doc, rows, manifest)

    def test_manifest_row_order_is_bound_to_fresh_projection(self):
        doc = document()
        rows, manifest = export_bundle(doc)
        rows.reverse()
        manifest["rows"].reverse()
        with self.assertRaises(ProjectionError):
            import_bundle(doc, rows, manifest)


class DetectorTests(unittest.TestCase):
    def test_magic_detection_is_candidate_only(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "data.bin"
            path.write_bytes(b"XP3\x00" + b"x" * 32)
            items = detect_path(path, head_limit=8)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].profile, "kirikiri-xp3")
        self.assertEqual(items[0].status, "candidate")

    def test_equal_candidates_require_explicit_resolution(self):
        items = [Candidate("a", "one", 0.8, ("x",)), Candidate("a", "two", 0.8, ("y",))]
        with self.assertRaises(AmbiguousCandidate):
            resolve(items)
        self.assertEqual(resolve(items, profile="two").profile, "two")

    def test_catalog_is_95_entry_inventory(self):
        root = Path(__file__).resolve().parents[1]
        catalog = json.loads((root / "catalog/engines.json").read_text(encoding="utf-8"))
        self.assertEqual(catalog["count"], 95)
        self.assertEqual(len(catalog["engines"]), 95)
        self.assertTrue(all(item["capabilities"]["repack"] == "not_verified" for item in catalog["engines"]))


if __name__ == "__main__":
    unittest.main()
