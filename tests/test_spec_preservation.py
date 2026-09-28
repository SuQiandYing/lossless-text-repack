"""Content-preservation regression: real source-to-reference reconstruction."""
import ast
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
FENCE = chr(96) * 3


def blocks(text):
    return re.findall(r"^(" + FENCE + r"[^\n]*)\n(.*?)^" + FENCE + r"[ \t]*$", text, re.M | re.S)


class SpecificationPreservationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mapping = json.loads((ROOT / "references/preservation-map.json").read_text("utf-8"))
        cls.source = (ROOT / cls.mapping["source_fixture"]).read_bytes()
        cls.lines = cls.source.decode("utf-8-sig").replace("\r\n", "\n").splitlines(keepends=True)

    def test_pristine_reference_bytes_bound_to_original(self):
        self.assertEqual(hashlib.sha256(self.source).hexdigest(),
                         "4105e2c4c7512baea49cebd21a5cf12adb5c249a22e69b2d6efbe9fb0d2a1bfe")
        self.assertEqual(self.mapping["source_sha256"], hashlib.sha256(self.source).hexdigest())

    def test_all_original_body_lines_have_exactly_one_destination(self):
        sections = self.mapping["sections"]
        self.assertEqual(len(sections), 14)
        covered = [i for s in sections for i in range(s["start_line"], s["end_line"] + 1)]
        self.assertEqual(covered, list(range(6, len(self.lines) + 1)))

    def test_replay_only_declared_corrections_reproduces_each_live_reference(self):
        for s in self.mapping["sections"]:
            with self.subTest(section=s["name"]):
                start = s["start_line"] - 1
                body = "".join(self.lines[start:s["end_line"]])
                corrections = sorted(s["corrections"], key=lambda e: e["start_line"])
                for a, b in zip(corrections, corrections[1:]):
                    self.assertLess(a["end_line"], b["start_line"])
                for e in reversed(corrections):
                    self.assertTrue(e["reason"].strip())
                    self.assertGreaterEqual(e["start_line"], s["start_line"])
                    self.assertLessEqual(e["end_line"], s["end_line"])
                    a = sum(len(x) for x in self.lines[start:e["start_line"]-1])
                    b = sum(len(x) for x in self.lines[start:e["end_line"]])
                    self.assertEqual(body[a:b], e["before"])
                    body = body[:a] + e["after"] + body[b:]
                actual = (ROOT / s["path"]).read_text("utf-8")
                self.assertEqual(actual, s["prefix"] + body)
                self.assertEqual(hashlib.sha256(actual.encode()).hexdigest(), s["result_sha256"])

    def test_all_65_original_fenced_examples_have_current_counterparts(self):
        total = 0
        for s in self.mapping["sections"]:
            before = blocks("".join(self.lines[s["start_line"]-1:s["end_line"]]))
            after = blocks((ROOT / s["path"]).read_text("utf-8"))
            self.assertEqual(len(before), len(after), s["name"])
            self.assertEqual(len(s["blocks"]), len(before), s["name"])
            total += len(before)
            for a, b, record in zip(before, after, s["blocks"]):
                self.assertEqual(a[0], b[0])
                self.assertEqual(hashlib.sha256(a[1].encode()).hexdigest(), record["source_sha256"])
                self.assertEqual(hashlib.sha256(b[1].encode()).hexdigest(), record["result_sha256"])
                self.assertEqual(record["status"], "verbatim" if a == b else "corrected")
        self.assertEqual(total, 65)

    def test_gui_layout_path_preview_details_and_options_are_verbatim(self):
        s = next(s for s in self.mapping["sections"] if s["name"] == "gui")
        before = blocks("".join(self.lines[s["start_line"]-1:s["end_line"]]))
        after = blocks((ROOT / s["path"]).read_text("utf-8"))
        self.assertEqual(before, after)
        for term in ["游戏脚本文件夹", "将回封 264 个文件", "理解深度", "[✓] 双行文本", "拖入 D:"]:
            self.assertTrue(any(term in block[1] for block in after), term)

    def test_gui_ten_sections_and_acceptance_groups_retained(self):
        text = (ROOT / "references/details/gui.md").read_text("utf-8")
        self.assertEqual(re.findall(r"^### (11\.\d+) ", text, re.M),
                         ["11." + str(i) for i in range(1, 11)])
        for group in ["路径与懒人默认", "输出选项", "回封", "文本变长", "其他"]:
            self.assertIn("**" + group + "**", text)

    def test_every_complete_reference_is_routed_from_entrypoint(self):
        entry = (ROOT / "SKILL.md").read_text("utf-8")
        for section in self.mapping["sections"]:
            self.assertIn("](" + section["path"] + ")", entry)

    def test_read_every_requirement_before_planning(self):
        entry = (ROOT / "SKILL.md").read_text("utf-8")
        gate = entry.index("## 使用前强制通读门禁")
        self.assertLess(gate, entry.index("## 先确定范围"))
        instruction = entry[gate:entry.index("## 先确定范围")]
        for requirement in ["未读完不得开始计划", "完整读取", "21 份规范文档",
                            "不以目录、摘要、搜索命中或脚本的读取结果代替模型阅读",
                            "工具返回截断", "续接任务"]:
            self.assertIn(requirement, instruction)
        required = {s["path"] for s in self.mapping["sections"]}
        required.update("references/" + name for name in [
            "parsing-evidence.md", "projections.md", "rebuilding.md",
            "validation.md", "delivery-performance.md", "PRESERVATION.md"])
        self.assertEqual(len(required), 20)
        for path in required:
            with self.subTest(path=path):
                self.assertTrue((ROOT / path).is_file())
                self.assertIn("](" + path + ")", entry)
        self.assertIn("| 通读后重点复核 |", entry)
        self.assertNotIn("| 按需读取 |", entry)

    def test_recursive_local_document_links_resolve(self):
        for file in (ROOT / "references").rglob("*.md"):
            for link in re.findall(r"\]\(([^)]+)\)", file.read_text("utf-8")):
                if "://" in link or link.startswith("#"):
                    continue
                path = (file.parent / link.split("#", 1)[0]).resolve()
                self.assertTrue(path.is_relative_to(ROOT), (file, link))
                self.assertTrue(path.is_file(), (file, link))

    def test_changed_python_examples_still_parse(self):
        for s in self.mapping["sections"]:
            after = blocks((ROOT / s["path"]).read_text("utf-8"))
            for (_, code), record in zip(after, s["blocks"]):
                if record["language"] == "python" and record["status"] == "corrected":
                    with self.subTest(section=s["name"], block=record["ordinal"]):
                        ast.parse(code)


if __name__ == "__main__":
    unittest.main()
