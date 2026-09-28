"""Standard-library regression tests for report, coverage and heuristic gates."""
from __future__ import annotations
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class GateTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="repack-report-gates-")
        self.addCleanup(self.tmp.cleanup)
        self.work = Path(self.tmp.name)

    def write(self, name, value):
        path = self.work / name
        if isinstance(value, bytes):
            path.write_bytes(value)
        else:
            path.write_text(value if isinstance(value, str) else json.dumps(value), encoding="utf-8")
        return path

    def run_gate(self, script, args, status):
        result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *map(str, args)],
                                capture_output=True, text=True, encoding="utf-8", timeout=20)
        self.assertEqual(result.returncode, {"pass": 0, "fail": 1, "not_verified": 2}[status], result.stdout + result.stderr)
        self.assertEqual(result.stderr, "", result.stderr)
        output = json.loads(result.stdout)
        self.assertEqual(output["status"], status)
        self.assertEqual(output["ok"], status == "pass")
        self.assertTrue("errors" in output or "issues" in output, output)
        return output

    def sanity(self, report, status="pass", extra=()):
        return self.run_gate("check_output_sanity.py", [self.write("report.json", report), *extra], status)

    def shapes(self, report, status="pass", extra=()):
        return self.run_gate("check_shapes.py", [self.write("shapes.json", report), *extra], status)

    def certificate(self, value, status="pass", source=b"ABCD"):
        return self.run_gate("coverage_certificate.py", [self.write("source.bin", source), self.write("cert.json", value)], status)

    @staticmethod
    def base_certificate():
        return {"source_size": 4, "byte_coverage": 1.0, "structural_coverage": 1,
                "intervals": [{"id": "R", "start": 0, "end": 4, "status": "decoded",
                               "raw_sha256": hashlib.sha256(b"ABCD").hexdigest()}]}

    @classmethod
    def tier_certificate(cls, tier="T1"):
        report = cls.base_certificate()
        report.update({"min_tier": tier, "tier_coverage": {tier: 4},
                       "evidence": {"E": {"kind": "observed", "source": "trace:12"}},
                       "declared_capabilities": ["roundtrip"]})
        item = report["intervals"][0]
        item.update({"decode_tier": tier, "tier_evidence_refs": ["E"],
                     "cell_size": 1, "cell_count": 4, "endianness": "little"})
        if tier >= "T2":
            item["structured_fields"] = ["name"]
        if tier >= "T3":
            item.update({"length_algorithm": "fixed-width opcode table v1", "operand_schema": {}})
            report["instruction_coverage"] = 1
        return report

    def test_sanity_empty_reports_fail(self):
        for report in ([], {"rows": []}, "", "  \n", [42], None, {}):
            with self.subTest(report=report):
                self.sanity(report, "fail")

    def test_sanity_jsonl_and_wrapper(self):
        row = {"sample": "A", "tags": {"ui": 3}}
        self.sanity(json.dumps(row) + "\n" + json.dumps({**row, "sample": "B"}))
        self.sanity({"rows": [row]})

    def test_sanity_duplicate_keys_rejected(self):
        self.sanity('{"sample":"A","tags":{"msg":1,"msg":2}}', "fail")

    def test_sanity_bad_count_types(self):
        for count in (-1, True, 1.5, "1", None, [], {}):
            with self.subTest(count=count):
                self.sanity({"sample": "A", "tags": {"msg": count}}, "fail")
        self.sanity('{"sample":"A","tags":{"msg":NaN}}', "fail")

    def test_sanity_bad_schema_not_silently_dropped(self):
        for patch in ({"tags": []}, {"tags": None}, {"byte_size": -1},
                      {"containers": {"dialog_entries": True}}, {"required_tags": "msg"},
                      {"tags": {"msg": 1}, "tag_counts": {"msg": 2}}, {"waivers": []}):
            with self.subTest(patch=patch):
                self.sanity({"sample": "A", "tags": {"ui": 2}, **patch}, "fail")

    def test_sanity_duplicate_sample_identity(self):
        row = {"sample": "A", "tags": {"msg": 1}}
        self.sanity([row, row], "fail")
        self.sanity([{**row, "sample": "dir1/A"}, {**row, "sample": "dir2/A"}])

    def test_sanity_missing_statistics_not_verified(self):
        self.sanity({"sample": "A"}, "not_verified")

    def test_sanity_zero_counts_equal_omission(self):
        a = self.sanity({"sample": "A", "tags": {"ui": 100}})
        b = self.sanity({"sample": "A", "tags": {"ui": 100, "msg": 0}})
        self.assertEqual(a["advisories"], b["advisories"])
        self.assertEqual(a["issues"], b["issues"])

    def test_sanity_skew_is_advisory(self):
        result = self.sanity({"sample": "A", "tags": {"ui": 100, "msg": 1}})
        self.assertEqual(result["advisories"][0]["code"], "SKEWED_OUTPUT")

    def test_sanity_required_tags_explicit_domain(self):
        row = {"sample": "A", "tags": {"ui": 1}}
        self.sanity(row, "fail", ["--require-tag", "msg"])
        self.sanity(row, "fail", ["--require-tag", "msg", "--domain", "dialogue scene"])
        self.sanity({"domain": "menu", "required_tags": ["ui"], "rows": [row]})
        self.sanity({**row, "required_tags": ["ui"]}, "fail")

    def test_sanity_waiver_needs_reason_and_evidence(self):
        row = {"sample": "A", "domain": "menu", "tags": {"ui": 1}, "required_tags": ["msg"]}
        self.sanity(row, "fail", ["--allow-zero", "msg"])
        row["waivers"] = {"msg": {"reason": "menu-only", "evidence_refs": ["inventory:A"]}}
        result = self.sanity(row, "pass", ["--allow-zero", "msg"])
        self.assertEqual(result["waivers_applied"][0]["reason"], "menu-only")

    def test_sanity_empty_sample_needs_evidence(self):
        self.sanity({"sample": "A", "tags": {}}, "fail")
        self.sanity({"sample": "A", "tags": {}, "allow_empty": {"reason": "metadata-only", "evidence_refs": ["inventory:A"]}})

    def test_sanity_container_mismatch(self):
        self.sanity({"sample": "A", "tags": {"ui": 1}, "containers": {"dialog_entries": 100}}, "fail")

    def test_shapes_valid(self):
        self.shapes({"declared": ["A"], "observed": {"A": {"entries": 1, "texts": 1}}})

    def test_shapes_missing_statistics_not_verified(self):
        for observed in ({}, {"A": 1}, {"A": {"entries": 1}}, {"A": {"entries": 0, "texts": 0}}):
            with self.subTest(observed=observed):
                self.shapes({"declared": ["A"], "observed": observed}, "not_verified")

    def test_shapes_invalid_counts_and_declarations(self):
        for report in ({"declared": "A", "observed": {}}, {"declared": ["A", "A"], "observed": {}},
                       {"declared": ["A"], "observed": {"A": -1}},
                       {"declared": ["A"], "observed": {"A": {"entries": True, "texts": 1}}},
                       {"declared": ["A"], "observed": {"A": {"entries": 0, "texts": 1}}},
                       {"declared": ["A"], "observed": [], "unmatched": {}},
                       {"declared": ["A"], "observed": {}, "unmatched": {"X": "1"}}):
            with self.subTest(report=report):
                self.shapes(report, "fail")
        self.shapes('{"declared":["A"],"observed":{"A":1,"A":2}}', "fail")

    def test_shapes_unknown_barren_and_nontext(self):
        self.shapes({"declared": ["A"], "observed": {"B": {"entries": 1, "texts": 1}}}, "fail")
        row = {"declared": ["A"], "observed": {"A": {"entries": 1, "texts": 0}}}
        self.shapes(row, "fail")
        row["nontext_shapes"] = {"A": {"reason": "control-only node", "evidence_refs": ["node:A"]}}
        self.shapes(row)

    def test_shapes_corpus_flag_is_not_evidence(self):
        self.shapes({"declared": ["A"], "observed": {"A": {"entries": 1, "texts": 1}}}, "not_verified", ["--corpus-wide"])

    def test_shapes_corpus_manifest_exact_match(self):
        manifest = [{"sample": "A", "sha256": hashlib.sha256(b"A").hexdigest()}]
        path = self.write("manifest.json", manifest)
        row = {"declared": ["A"], "observed": {"A": {"entries": 1, "texts": 1}},
               "corpus": {"manifest_sha256": hashlib.sha256(path.read_bytes()).hexdigest(), "scanned": manifest}}
        extra = ["--corpus-wide", "--corpus-manifest", path]
        result = self.shapes(row, "pass", extra)
        self.assertTrue(result["corpus_scope_verified"])
        row["corpus"]["scanned"] = [{"sample": "B", "sha256": manifest[0]["sha256"]}]
        self.shapes(row, "fail", extra)

    def test_shapes_inherited_waiver_requires_evidence(self):
        row = {"declared": ["A", "B"], "observed": {"A": {"entries": 1, "texts": 1}}, "inherited": {"B": "other corpus"}}
        self.shapes(row, "not_verified")
        row["inherited"]["B"] = {"reason": "other corpus", "evidence_refs": ["corpus:B"]}
        self.shapes(row)

    def test_certificate_byte_scope_and_empty(self):
        result = self.certificate(self.base_certificate())
        self.assertFalse(result["tier_claims_checked"])
        self.certificate({"source_size": 0, "intervals": []}, "not_verified", b"")

    def test_certificate_structural_coverage_is_not_byte_coverage(self):
        result = self.certificate({**self.base_certificate(), "structural_coverage": 0})
        self.assertEqual(result["byte_coverage"], 1)
        self.assertEqual(result["structural_coverage"], 0)
        self.assertEqual(result["structural_coverage_verification"], "not_verified")

    def test_certificate_bad_ranges_hashes_and_types(self):
        for patch in ({"start": 1}, {"end": 5}, {"end": 0}, {"start": True}, {"raw_sha256": "0" * 64}, {"status": []}):
            with self.subTest(patch=patch):
                report = self.base_certificate()
                report["intervals"][0].update(patch)
                self.certificate(report, "fail")
        for patch in ({"source_size": True}, {"source_size": -1}, {"byte_coverage": True},
                      {"byte_coverage": "1"}, {"structural_coverage": 2}, {"status_counts": {"decoded": -1}},
                      {"intervals": []}, {"analysis_mode": []}, {"source_sha256": "0" * 64}):
            with self.subTest(patch=patch):
                self.certificate({**self.base_certificate(), **patch}, "fail")

    def test_certificate_duplicate_json_key(self):
        self.certificate('{"source_size":4,"source_size":4,"intervals":[]}', "fail")

    def test_certificate_valid_tiers(self):
        for tier in ("T1", "T2", "T3"):
            with self.subTest(tier=tier):
                result = self.certificate(self.tier_certificate(tier))
                self.assertTrue(result["tier_claims_checked"])
                self.assertEqual(result["capability_semantics"], "not_verified")

    def test_certificate_tier_claims_must_be_consistent(self):
        for patch in ({"min_tier": "T4"}, {"tier_coverage": {"T1": 3}}, {"tier_coverage": {"T1": True}},
                      {"instruction_coverage": 1}, {"declared_capabilities": ["unknown"]}, {"evidence": {}}):
            with self.subTest(patch=patch):
                self.certificate({**self.tier_certificate(), **patch}, "fail")
        for patch in ({"cell_size": 3}, {"decode_tier": "T9"}, {"tier_evidence_refs": ["E", "E"]}, {"id": []}):
            with self.subTest(patch=patch):
                report = self.tier_certificate()
                report["intervals"][0].update(patch)
                self.certificate(report, "fail")

    def test_certificate_t3_needs_length_algorithm(self):
        report = self.tier_certificate("T3")
        del report["intervals"][0]["length_algorithm"]
        self.certificate(report, "fail")

    def test_certificate_capability_requires_scope_to_check_tier(self):
        report = self.tier_certificate()
        report["declared_capabilities"] = ["in_place"]
        result = self.certificate(report)
        self.assertEqual(result["capability_tier_consistency"], "not_verified")
        report["capability_scopes"] = {"in_place": {"scope_region_ids": ["R"]}}
        self.certificate(report, "fail")

    def test_certificate_t0_identity_and_roundtrip_are_legal(self):
        report = self.base_certificate()
        report["intervals"][0].update({"decode_tier": "T0", "status": "opaque-preserved"})
        report.update({"min_tier": "T0", "tier_coverage": {"T0": 4},
                       "declared_capabilities": ["identity", "roundtrip"],
                       "capability_scopes": {name: {"scope_region_ids": ["R"]}
                                             for name in ("identity", "roundtrip")}})
        result = self.certificate(report)
        self.assertEqual(result["capability_tier_consistency"], "checked")
        self.assertEqual(result["capability_semantics"], "not_verified")
        for check in result["capability_scope_checks"].values():
            self.assertEqual(check["required_tier"], "T0")

    def test_certificate_full_layout_distinguishes_data_and_instruction(self):
        for operation_kind in (None, "data", "instruction"):
            with self.subTest(operation_kind=operation_kind):
                report = self.tier_certificate("T2")
                scope = {"scope_region_ids": ["R"]}
                if operation_kind is not None:
                    scope["operation_kind"] = operation_kind
                report.update({"declared_capabilities": ["full-layout"],
                               "capability_scopes": {"full-layout": scope}})
                if operation_kind == "instruction":
                    self.certificate(report, "fail")
                    continue
                result = self.certificate(report)
                check = result["capability_scope_checks"]["full-layout"]
                self.assertEqual(check["scope"], "data_layout_tier_only")
                self.assertEqual(check["operation_kind"], "data")
                self.assertEqual(check["operation_kind_defaulted"], operation_kind is None)
                self.assertEqual(result["capability_semantics"], "not_verified")
        report = self.tier_certificate("T3")
        report.update({"declared_capabilities": ["full-layout"],
                       "capability_scopes": {"full-layout": {"scope_region_ids": ["R"], "operation_kind": "instruction"}}})
        result = self.certificate(report)
        self.assertEqual(result["capability_scope_checks"]["full-layout"]["required_tier"], "T3")
        self.assertEqual(result["capability_scope_checks"]["full-layout"]["scope"], "instruction_layout_tier_only")
        for invalid in ("", "code", 0, False, [], {}):
            with self.subTest(invalid=invalid):
                report["capability_scopes"]["full-layout"]["operation_kind"] = invalid
                self.certificate(report, "fail")

    def test_certificate_mixed_tiers_scoped_capability_and_instruction_ratio(self):
        report = self.tier_certificate("T3")
        code = report["intervals"][0]
        code.update({"end": 2, "cell_count": 2, "raw_sha256": hashlib.sha256(b"AB").hexdigest()})
        report["intervals"].append({"id": "opaque", "start": 2, "end": 4, "decode_tier": "T0",
                                    "status": "opaque-preserved", "raw_sha256": hashlib.sha256(b"CD").hexdigest()})
        report.update({"min_tier": "T0", "tier_coverage": {"T0": 2, "T3": 2}, "instruction_coverage": 0.5,
                       "declared_capabilities": ["full-layout"],
                       "capability_scopes": {"full-layout": {"scope_region_ids": ["R"]}}})
        result = self.certificate(report)
        self.assertEqual(result["computed_instruction_coverage"], 0.5)
        self.assertEqual(result["capability_tier_consistency"], "checked")
        report["instruction_coverage"] = 1
        self.certificate(report, "fail")
        report["instruction_coverage"] = 0.5
        report["capability_scopes"]["full-layout"]["scope_region_ids"].append("opaque")
        self.certificate(report, "fail")

    def test_certificate_structured_and_instruction_boundaries(self):
        for tier, model in (("T2", "structured"), ("T3", "instruction")):
            with self.subTest(tier=tier, model=model):
                report = self.tier_certificate(tier)
                item = report["intervals"][0]
                for key in ("cell_size", "cell_count", "endianness"):
                    del item[key]
                item.update({"boundary_model": model, "boundary_evidence_refs": ["E"]})
                self.certificate(report)
                item["boundary_evidence_refs"] = []
                self.certificate(report, "fail")

    def test_determinism_equal_size_edits_are_visible_not_semantically_proven(self):
        a, b = self.write("a.bin", b"ABCD"), self.write("b.bin", b"AXCD")
        result = self.run_gate("check_determinism.py", ["edit", a, b, "--edited"], "pass")
        self.assertEqual(result["size_delta"], 0)
        self.assertEqual(result["scope"], "byte_edit_visibility_only")
        self.assertEqual(result["semantic_correctness"], "not_verified")
        self.run_gate("check_determinism.py", ["edit", a, b, "--no-edit"], "fail")

    def test_determinism_zero_edit_and_lost_edit(self):
        a, b = self.write("a.bin", b"ABCD"), self.write("b.bin", b"ABCD")
        self.run_gate("check_determinism.py", ["edit", a, b, "--no-edit"], "pass")
        self.run_gate("check_determinism.py", ["edit", a, b, "--edited"], "fail")
        self.run_gate("check_determinism.py", ["rerun", a, b], "pass")
        self.run_gate("check_determinism.py", ["rerun", a, a], "fail")
        self.run_gate("check_determinism.py", ["rerun", a], "fail")

    def test_determinism_empty_api_pairs_not_pass(self):
        spec = importlib.util.spec_from_file_location("det_gate", ROOT / "scripts/check_determinism.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.assertEqual(module.cmd_rerun([])["status"], "not_verified")

    def test_literals_empty_or_excluded_inputs_not_verified(self):
        self.run_gate("check_no_literals.py", [self.work], "not_verified")
        self.write("test_fixture.py", "opcode = 0xDEADBEEF\n")
        self.run_gate("check_no_literals.py", [self.work], "not_verified")
        self.run_gate("check_no_literals.py", [ROOT / "scripts/check_no_literals.py"], "not_verified")

    def test_literals_generic_numbers_and_tests_not_false_positives(self):
        self.write("test_fixture.py", "opcode = 0xDEADBEEF\n")
        self.write("structural.py", "width = 0x10\nmask = 0xFF\npreview = 80\n")
        result = self.run_gate("check_no_literals.py", [self.work], "pass")
        self.assertEqual(result["scanned_files"], 1)

    def test_literals_findings_and_waivers(self):
        path = self.write("structural.py", "opcode = 0xDEADBEEF\n")
        self.run_gate("check_no_literals.py", [path], "fail")
        self.write("structural.py", "opcode = 0xDEADBEEF  # dialect-literal-ok\n")
        self.run_gate("check_no_literals.py", [path], "fail")
        self.write("structural.py", "opcode = 0xDEADBEEF  # dialect-literal-ok: fixture signature for format test\n")
        self.run_gate("check_no_literals.py", [path], "pass")

    def test_literals_string_cannot_waive(self):
        path = self.write("structural.py", 'opcode = 0xDEADBEEF; note = "dialect-literal-ok: fake"\n')
        self.run_gate("check_no_literals.py", [path], "fail")

    def test_literals_regex_imports_and_builtin_compile(self):
        path = self.write("structural.py", 'compiled = compile("名 = 1", "fixture", "exec")\n')
        self.run_gate("check_no_literals.py", [path], "pass")
        self.write("structural.py", 'import re as regex\npattern = regex.compile("[あいう]")\n')
        self.run_gate("check_no_literals.py", [path], "fail")
        self.write("structural.py", 'from re import compile as pattern\nbody = pattern("[あいう]")\n')
        self.run_gate("check_no_literals.py", [path], "fail")

    def test_literals_bad_encoding_syntax_are_structured_failures(self):
        for content in ("def broken(:\n", b"\xff\xfe broken"):
            with self.subTest(content=content):
                path = self.write("structural.py", content)
                self.run_gate("check_no_literals.py", [path], "fail")

    def test_output_paths_never_overwrite_inputs(self):
        source = self.write("source.bin", b"ABCD")
        rebuilt = self.write("rebuilt.bin", b"ABCD")
        cert = self.write("cert.json", self.base_certificate())
        report = self.write("report.json", {"sample": "A", "tags": {"msg": 1}})
        shape = self.write("shape.json", {"declared": ["A"], "observed": {"A": {"entries": 1, "texts": 1}}})
        code = self.write("structural.py", "width = 4\n")
        cases = [("coverage_certificate.py", [source, cert], "--report", [source, cert]),
                 ("check_output_sanity.py", [report], "--report-out", [report]),
                 ("check_shapes.py", [shape], "--report-out", [shape]),
                 ("check_determinism.py", ["edit", source, rebuilt, "--no-edit"], "--report-out", [source, rebuilt]),
                 ("check_no_literals.py", [code], "--report", [code])]
        for script, args, flag, protected in cases:
            for path in protected:
                with self.subTest(script=script, path=path):
                    before = path.read_bytes()
                    self.run_gate(script, [*args, flag, path], "fail")
                    self.assertEqual(path.read_bytes(), before)

    def test_shapes_output_cannot_overwrite_manifest_or_baseline(self):
        report = self.write("shape.json", {"declared": ["A"], "observed": {"A": {"entries": 1, "texts": 1}}})
        baseline = self.write("baseline.json", {"observed": {"A": {"entries": 1, "texts": 1}}})
        manifest = self.write("manifest.json", [])
        for path, extra in ((baseline, ["--baseline", baseline]), (manifest, ["--corpus-wide", "--corpus-manifest", manifest])):
            before = path.read_bytes()
            self.run_gate("check_shapes.py", [report, *extra, "--report-out", path], "fail")
            self.assertEqual(path.read_bytes(), before)

    def test_report_write_errors_are_structured(self):
        report = self.write("report.json", {"sample": "A", "tags": {"msg": 1}})
        self.run_gate("check_output_sanity.py", [report, "--report-out", self.work], "fail")


if __name__ == "__main__":
    unittest.main()
