"""CLI regressions for trusted text imports and byte-site attribution (stdlib)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
DIGEST = hashlib.sha256(b"fixture-A").hexdigest()
DIGEST_B = hashlib.sha256(b"fixture-B").hexdigest()


class GateCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="edit-gates-")
        self.base = Path(self.tmp.name)
        self.ir = self.base / "ir"
        self.ir.mkdir()
        self.addCleanup(self.tmp.cleanup)

    def jsonl(self, name, rows):
        path = self.base / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
        return path

    def entries(self, rows=None, manifest=True):
        if rows is None:
            rows = [self.entry(1)]
        self.jsonl("ir/text_entries.jsonl", rows)
        if manifest:
            ids = {row.get("src_id", "*") for row in rows if isinstance(row, dict)}
            self.jsonl("ir/manifest.jsonl", [{"src_id": src, "sha256": DIGEST_B if src == "B" else DIGEST} for src in ids])

    @staticmethod
    def entry(idx, **extra):
        return {"idx": idx, "source": "old", "tag": "msg", "translate_policy": "translatable", **extra}

    def text(self, name="input.txt", entries=None, scope="kind=all range=ALL part=1/1", digest=DIGEST, target="utf-8", src_id=None):
        entries = entries or [(1, "old", "new", "msg", "")]
        lines = [f"# TEXT/2 ir=1 tool=test src_sha256={digest}" + (f" src_id={src_id}" if src_id else ""),
                 f"# encoding source=utf-8 target={target} file=utf-8",
                 f"# scope {scope}", "# tags name msg choice label ui system ruby misc"]
        for idx, src, dst, tag, meta in entries:
            lines += [f"# idx={idx:08d} tag={tag}" + (" " + meta if meta else ""),
                      f"○{idx:08d}○{tag}○{src}", f"●{idx:08d}●{tag}●{dst}", ""]
        path = self.base / name
        path.write_text("\n".join(lines), encoding="utf-8")
        return path

    def invoke(self, script, *args, expected=0, code=None):
        completed = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
                                   capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(completed.returncode, expected, completed.stdout + completed.stderr)
        self.assertEqual(completed.stderr, "", completed.stderr)
        report = json.loads(completed.stdout)
        self.assertEqual(report["status"], {0: "pass", 1: "fail", 2: "not_verified"}[expected])
        self.assertEqual(report["ok"], expected == 0)
        if code:
            self.assertIn(code, {row["code"] for row in report["errors"] + report.get("not_verified", [])}, report)
        return report

    def dsat(self, *files, **expect):
        return self.invoke("check_dsat.py", self.ir, *files, **expect)

    def sites(self, src=b"abcdefgh", dst=b"ABCDEFGH", rows=None, reloc=None, layout=None, reparsed=None, expected=0, code=None, strict=False):
        original, rebuilt = self.base / "original.bin", self.base / "rebuilt.bin"
        original.write_bytes(src)
        rebuilt.write_bytes(dst)
        site_path = self.jsonl("sites.jsonl", [] if rows is None else rows)
        args = [original, rebuilt, site_path]
        if reloc is not None:
            args += ["--relocation-log", self.jsonl("relocations.jsonl", reloc)]
        if layout is not None:
            args += ["--layout-map", self.jsonl("layout.jsonl", layout)]
        if reparsed is not None:
            args += ["--rebuilt-sites", self.jsonl("reparsed.jsonl", reparsed)]
        if strict:
            args += ["--strict-diff"]
        return self.invoke("check_sites.py", *args, expected=expected, code=code)

    @staticmethod
    def span(old, old_len, new, new_len, kind="preserve"):
        return dict(old_offset=old, old_length=old_len, new_offset=new, new_length=new_len,
                    kind=kind, **({"reason": "fixture edit"} if kind == "changed" else {}))


class TextImportTests(GateCase):
    def test_invalid_cli_is_failure_not_unverified(self):
        self.invoke("check_dsat.py", expected=1, code="CLI_ARGUMENTS")

    def test_legacy_text1_subset_tags_and_implicit_all_range(self):
        self.entries()
        path = self.text()
        text = path.read_text(encoding="utf-8").replace("TEXT/2", "TEXT/1").replace(" range=ALL", "").replace("# tags name msg choice label ui system ruby misc", "# tags msg ui")
        path.write_text(text, encoding="utf-8")
        self.assertTrue(self.dsat(path)["files"][0]["legacy_format"])

    def test_ordinary_edit(self):
        self.entries()
        self.assertEqual(self.dsat(self.text())["files"][0]["changed"], 1)

    def test_frozen_cannot_be_overridden_by_editable_comment(self):
        self.entries([self.entry(1, translate_policy="frozen")])
        self.dsat(self.text(entries=[(1, "old", "new", "msg", "policy=translatable")]), expected=1, code="POLICY_MISMATCH")

    def test_frozen_change_without_comment_rejected(self):
        self.entries([self.entry(1, translate_policy="frozen")])
        self.dsat(self.text(), expected=1, code="FROZEN_MODIFIED")

    def test_frozen_unchanged_passes(self):
        self.entries([self.entry(1, translate_policy="frozen")])
        self.dsat(self.text(entries=[(1, "old", "old", "msg", "policy=frozen")]))

    def test_all_three_tags_changed_still_rejected(self):
        self.entries()
        self.dsat(self.text(entries=[(1, "old", "new", "name", "")]), expected=1, code="TAG_MISMATCH")

    def test_source_anchor_changed(self):
        self.entries()
        self.dsat(self.text(entries=[(1, "wrong", "new", "msg", "")]), expected=1, code="SOURCE_ANCHOR")

    def test_two_complete_shards(self):
        self.entries([self.entry(1), self.entry(2)])
        a = self.text("a.txt", scope="kind=all range=ALL part=1/2")
        b = self.text("b.txt", entries=[(2, "old", "new", "msg", "")], scope="kind=all range=ALL part=2/2")
        self.dsat(a, b)

    def test_complete_part_numbers_do_not_hide_duplicate_and_missing_idx(self):
        self.entries([self.entry(1), self.entry(2)])
        a = self.text("a.txt", scope="kind=all range=ALL part=1/2")
        b = self.text("b.txt", scope="kind=all range=ALL part=2/2")
        self.dsat(a, b, expected=1, code="SHARD_IDX_DUPLICATE")

    def test_shards_with_missing_content(self):
        self.entries([self.entry(1), self.entry(2), self.entry(3)])
        a = self.text("a.txt", scope="kind=all range=ALL part=1/2")
        b = self.text("b.txt", entries=[(2, "old", "new", "msg", "")], scope="kind=all range=ALL part=2/2")
        self.dsat(a, b, expected=1, code="INCOMPLETE")

    def test_missing_shard(self):
        self.entries([self.entry(1), self.entry(2)])
        self.dsat(self.text(scope="kind=all range=ALL part=1/2"), expected=1, code="SHARD_INCOMPLETE")

    def test_explicit_partial_range(self):
        self.entries([self.entry(1), self.entry(2)])
        scope = self.jsonl("expected-scope.json", [{"*": [1]}])
        self.dsat(self.text(scope="kind=idx-range range=1-1 part=1/1"), "--expected-scope", scope)

    def test_editable_header_cannot_authorize_partial_import(self):
        self.entries([self.entry(1), self.entry(2)])
        self.dsat(self.text(scope="kind=idx-range range=1-1 part=1/1"), expected=1, code="SCOPE_NOT_AUTHORIZED")

    def test_authorized_scope_cannot_be_shrunk_by_editable_header(self):
        self.entries([self.entry(1), self.entry(2)])
        scope = self.jsonl("expected-scope.json", [{"*": [1, 2]}])
        self.dsat(self.text(scope="kind=idx-range range=1-1 part=1/1"), "--expected-scope", scope, expected=1, code="INCOMPLETE")

    def test_declared_range_must_equal_authorized_scope(self):
        self.entries([self.entry(1), self.entry(2)])
        scope = self.jsonl("expected-scope.json", [{"*": [1]}])
        self.dsat(self.text(scope="kind=idx-range range=1-2 part=1/1"), "--expected-scope", scope, expected=1, code="SCOPE_MISMATCH")

    def test_scope_schema_rejects_unknown_and_duplicate_indices(self):
        self.entries()
        for values in ([1, 1], [2], [], [True]):
            scope = self.jsonl("expected-scope.json", [{"*": values}])
            self.dsat(self.text(scope="kind=idx-range range=1-1 part=1/1"), "--expected-scope", scope, expected=1)

    def test_range_does_not_allow_outside_idx(self):
        self.entries([self.entry(1), self.entry(2)])
        scope = self.jsonl("expected-scope.json", [{"*": [2]}])
        self.dsat(self.text(scope="kind=idx-range range=2-2 part=1/1"), "--expected-scope", scope, expected=1, code="SCOPE_RANGE")

    def test_cross_source_same_idx_is_legal(self):
        self.entries([self.entry(1, src_id="A"), self.entry(1, src_id="B", source="other")])
        a = self.text("a.txt")
        b = self.text("b.txt", digest=DIGEST_B, entries=[(1, "other", "translated", "msg", "")])
        self.dsat(a, b)

    def test_cross_source_wrong_hash_does_not_route_arbitrarily(self):
        self.entries([self.entry(1, src_id="A"), self.entry(1, src_id="B", source="other")])
        self.dsat(self.text(digest=DIGEST_B), expected=1, code="SOURCE_ANCHOR")

    def test_identical_hashes_need_explicit_src_id(self):
        self.entries([self.entry(1, src_id="A"), self.entry(1, src_id="C")])
        self.dsat(self.text(), expected=1, code="SRC_HASH_MISMATCH")
        self.dsat(self.text(src_id="A"))

    def test_missing_manifest_is_unverified_not_pass(self):
        self.entries(manifest=False)
        self.dsat(self.text(), expected=2, code="SOURCE_HASH_UNVERIFIED")

    def test_unknown_codec_rejected_even_without_edit(self):
        self.entries()
        self.dsat(self.text(target="nonexistent", entries=[(1, "old", "old", "msg", "")]), expected=1, code="ENCODING_UNKNOWN")

    def test_expected_codec_accepts_canonical_alias(self):
        self.entries()
        report = self.dsat(self.text(target="utf8"), "--target-encoding", "utf-8")
        self.assertEqual(report["encoding_binding"], "verified")
        self.assertEqual(report["files"][0]["encoding_binding"], "verified")
        self.assertEqual(report["files"][0]["canonical_target_encoding"], "utf-8")

    def test_editable_header_cannot_override_expected_codec(self):
        self.entries()
        self.dsat(self.text(target="utf-8"), "--target-encoding", "cp932", expected=1, code="TARGET_ENCODING_MISMATCH")

    def test_expected_codec_unknown_is_schema_failure(self):
        self.entries()
        self.dsat(self.text(), "--target-encoding", "not-a-codec", expected=1, code="ENCODING_UNKNOWN")

    def test_legacy_unbound_encoding_pass_has_explicit_limited_scope(self):
        self.entries()
        report = self.dsat(self.text())
        self.assertEqual(report["encoding_binding"], "not_verified")
        self.assertEqual(report["files"][0]["encoding_binding"], "not_verified")
        self.assertEqual(report["encoding_verification_scope"], "header-declared-codec-representability")

    def test_unchanged_original_empty_string_passes(self):
        self.entries([self.entry(1, source="")])
        self.dsat(self.text(entries=[(1, "", "", "msg", "")]), "--target-encoding", "utf8")

    def test_unrepresentable_translation(self):
        self.entries()
        self.dsat(self.text(target="ascii", entries=[(1, "old", "中文", "msg", "")]), expected=1, code="ENCODING_UNREPRESENTABLE")

    def test_length_locked_counts_raw_placeholder_bytes(self):
        self.entries([self.entry(1, source="a{{00:FF}}", translate_policy="length-locked", raw_len=3)])
        self.dsat(self.text(entries=[(1, "a{{00:FF}}", "b{{00:FF}}", "msg", "")]))

    def test_length_locked_requires_ir_length(self):
        self.entries([self.entry(1, translate_policy="length-locked")])
        self.dsat(self.text(), expected=1, code="SCHEMA")

    def test_multibyte_length_lock_and_capacity(self):
        self.entries([self.entry(1, source="a", translate_policy="length-locked", raw_len=1)])
        self.dsat(self.text(entries=[(1, "a", "中", "msg", "")]), expected=1, code="LENGTH_LOCKED")

    def test_variable_length_allowed_without_fixed_slot(self):
        self.entries()
        self.dsat(self.text(entries=[(1, "old", "a much longer translation", "msg", "")]))

    def test_fixed_slot_rejects_overflow(self):
        self.entries([self.entry(1, slot_capacity=3)])
        self.dsat(self.text(entries=[(1, "old", "long", "msg", "")]), expected=1, code="LENGTH_OVERFLOW")

    def test_placeholder_split_cannot_hide_equal_flattened_bytes(self):
        self.entries([self.entry(1, source="a{{00:FF}}")])
        self.dsat(self.text(entries=[(1, "a{{00:FF}}", "b{{00}}{{FF}}", "msg", "")]), expected=1, code="PLACEHOLDER_BROKEN")

    def test_unclosed_placeholder_rejected(self):
        self.entries()
        self.dsat(self.text(entries=[(1, "old", "new{{00", "msg", "")]), expected=1, code="PLACEHOLDER_BROKEN")

    def test_review_marker_required_only_for_changed_review_entry(self):
        self.entries([self.entry(1, translate_policy="review-required")])
        self.dsat(self.text(), expected=1, code="REVIEW_REQUIRED")
        self.dsat(self.text(entries=[(1, "old", "new", "msg", "reviewed=true")]))

    def test_empty_ir_and_empty_input_directory_rejected(self):
        self.entries([])
        self.dsat(self.text(), expected=1, code="EMPTY_IR")
        empty = self.base / "empty"
        empty.mkdir()
        self.dsat(empty, expected=1, code="NO_INPUT")

    def test_schema_invalid_and_nonobject_rows_report_json(self):
        for row in ([], 3, {"idx": True}, self.entry(1, slot_capacity=-1), self.entry(1, source=[]), self.entry(1, tag=[]), self.entry(1, translate_policy={})):
            with self.subTest(row=row):
                self.jsonl("ir/text_entries.jsonl", [row])
                self.dsat(self.text(), expected=1, code="SCHEMA")

    def test_duplicate_path_and_corrupt_metadata_rejected(self):
        self.entries()
        path = self.text()
        self.dsat(path, path, expected=1, code="DUPLICATE_INPUT")
        self.dsat(self.text(entries=[(1, "old", "new", "msg", "idx=oops")]), expected=1, code="DUPLICATE_FIELD")

    def test_report_cannot_overwrite_text_input(self):
        self.entries()
        path = self.text()
        before = path.read_bytes()
        self.dsat(path, "--report", path, expected=1, code="INPUT_REPORT_COLLISION")
        self.assertEqual(path.read_bytes(), before)

    def test_duplicate_json_key_or_nan_is_invalid(self):
        self.entries()
        ir_path = self.ir / "text_entries.jsonl"
        for raw in ('{"idx":1,"idx":2}', '{"idx":NaN}'):
            with self.subTest(raw=raw):
                ir_path.write_text(raw + "\n", encoding="utf-8")
                self.dsat(self.text(), expected=1, code="IR_CORRUPT")


class SiteTests(GateCase):
    def test_unknown_engine_shortcut_flag_is_explicit_failure(self):
        self.invoke("check_sites.py", "old", "new", "sites", "--aosv2", expected=1, code="CLI_ARGUMENTS")

    def test_report_cannot_overwrite_original_binary(self):
        original, rebuilt = self.base / "original.bin", self.base / "rebuilt.bin"
        original.write_bytes(b"source")
        rebuilt.write_bytes(b"source")
        sites = self.jsonl("sites.jsonl", [])
        self.invoke("check_sites.py", original, rebuilt, sites, "--report", original, expected=1, code="INPUT_REPORT_COLLISION")
        self.assertEqual(original.read_bytes(), b"source")

    def test_duplicate_json_field_is_invalid(self):
        original, rebuilt = self.base / "original.bin", self.base / "rebuilt.bin"
        original.write_bytes(b"source")
        rebuilt.write_bytes(b"source")
        sites = self.base / "sites.jsonl"
        sites.write_text('{"site_offset":0,"site_offset":1}\n', encoding="utf-8")
        self.invoke("check_sites.py", original, rebuilt, sites, expected=1, code="JSON_CORRUPT")

    def test_partial_overlap_does_not_cover_entire_diff(self):
        self.sites(reloc=[{"offset": 0, "length": 4}], expected=1, code="UNATTRIBUTED_DIFF")

    def test_adjacent_union_fully_covers_diff(self):
        self.sites(reloc=[{"offset": 0, "length": 4}, {"offset": 4, "length": 4}])

    def test_one_byte_gap_is_rejected(self):
        self.sites(reloc=[{"offset": 0, "length": 3}, {"offset": 4, "length": 4}], expected=1, code="UNATTRIBUTED_DIFF")

    def test_unchanged_no_sites_is_valid_byte_identity(self):
        self.sites(dst=b"abcdefgh")

    def test_actual_site_mapping_and_non_site_collision_preserved(self):
        self.sites(src=b"\x01\x00\x01\x00", dst=b"\x02\x00\x01\x00",
                   rows=[dict(site_offset=0, site_width=2, key_value=1, new_key_value=2)])

    def test_value_match_rewrite_rejected(self):
        self.sites(src=b"\x01\x00\x01\x00", dst=b"\x02\x00\x02\x00",
                   rows=[dict(site_offset=0, site_width=2, key_value=1, new_key_value=2)], expected=1, code="VALUE_MATCH_REWRITE")

    def test_same_old_key_can_have_different_site_specific_new_values(self):
        self.sites(src=b"\x01\x01", dst=b"\x02\x03",
                   rows=[dict(site_offset=0, site_width=1, key_value=1, new_key_value=2),
                         dict(site_offset=1, site_width=1, key_value=1, new_key_value=3)])

    def test_mixed_width_and_endianness(self):
        self.sites(src=b"\x01\x00\x01", dst=b"\x02\x00\x03",
                   rows=[dict(site_offset=0, site_width=1, key_value=1, new_key_value=2),
                         dict(site_offset=1, site_width=2, site_endianness="big", key_value=1, new_key_value=3)])

    def test_preserve_policy_cannot_be_rewritten(self):
        self.sites(src=b"\x01", dst=b"\x02", rows=[dict(site_offset=0, site_width=1, key_value=1, rewrite_policy="preserve")], expected=1, code="PRESERVE_VIOLATED")

    def test_changed_length_without_layout_is_not_verified(self):
        self.sites(src=b"abc", dst=b"aXYZbc", expected=2, code="LAYOUT_UNVERIFIED")

    def test_strict_diff_cannot_make_missing_layout_verified(self):
        self.sites(src=b"abc", dst=b"aXYZbc", reloc=[dict(offset=0, length=6)], strict=True, expected=2, code="LAYOUT_UNVERIFIED")

    def test_variable_length_with_explicit_preserved_span_mapping(self):
        self.sites(src=b"abc", dst=b"aXYZbc", layout=[self.span(0, 1, 0, 1), self.span(1, 0, 1, 3, "changed"), self.span(1, 2, 4, 2)])

    def test_variable_length_preserved_content_tampering_rejected(self):
        self.sites(src=b"abc", dst=b"aXYZbD", layout=[self.span(0, 1, 0, 1), self.span(1, 0, 1, 3, "changed"), self.span(1, 2, 4, 2)], expected=1, code="PRESERVE_SPAN_CHANGED")

    def test_layout_hole_and_overlap_rejected(self):
        for spans in ([self.span(0, 2, 0, 2)], [self.span(0, 3, 0, 3), self.span(1, 1, 1, 1)]):
            with self.subTest(spans=spans):
                self.sites(src=b"abc", dst=b"abc", layout=spans, expected=1, code="LAYOUT_COVERAGE")

    def test_moved_site_with_same_width_mapping(self):
        self.sites(src=b"A\x01B", dst=b"XYZ A\x02B",
                   rows=[dict(site_offset=1, site_width=1, key_value=1, new_key_value=2)],
                   layout=[self.span(0, 0, 0, 4, "changed"), self.span(0, 1, 4, 1), self.span(1, 1, 5, 1, "changed"), self.span(2, 1, 6, 1)])

    def test_reparsed_site_set_added_or_missing_rejected(self):
        row = dict(site_offset=0, site_width=1, key_value=1, new_key_value=2, key_kind="entry_id")
        self.sites(src=b"\x01A", dst=b"\x02A", rows=[row], reparsed=[], expected=1, code="SITE_SET_MISMATCH")
        self.sites(src=b"\x01A", dst=b"\x02A", rows=[row], reparsed=[dict(site_offset=0, site_width=1, key_value=2, key_kind="entry_id")])

    def test_schema_bad_offsets_types_and_unknown_policy_fail(self):
        rows = [dict(site_offset=-1, key_value=0), dict(site_offset=True, key_value=0),
                dict(site_offset=0, site_width=3, key_value=0), dict(site_offset=0, key_value=0, rewrite_policy="guess"),
                dict(site_offset=0, key_value=0, site_endianness="middle"), []]
        for row in rows:
            with self.subTest(row=row):
                self.sites(rows=[row], expected=1)

    def test_empty_or_malformed_layout_and_relocation_fail(self):
        self.sites(layout=[], expected=1, code="EMPTY_LAYOUT")
        self.sites(reloc=[dict(offset=0, length=9)], expected=1, code="RELOCATION_BOUNDS")
        self.sites(layout=[dict(old_offset=0, old_length=8, new_offset=0, new_length=8, kind="changed")], expected=1, code="SCHEMA")

    def test_no_implicit_aos_layout_exemption(self):
        # A signature matching an engine must not silently exempt changed bytes.
        src = bytearray(0x200)
        src[4:8] = (0x139).to_bytes(4, "little")
        src[8:12] = (0x28).to_bytes(4, "little")
        src[0x135:0x139] = (0xC7).to_bytes(4, "little")
        dst = bytearray(src)
        dst[0x150] = 1
        self.sites(src=bytes(src), dst=bytes(dst), expected=1, code="UNATTRIBUTED_DIFF")


if __name__ == "__main__":
    unittest.main()
