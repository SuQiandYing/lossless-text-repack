"""Keep short installation instructions aligned with the packaged files."""
import re
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
    def test_installation_commands_and_references_match_package(self):
        readme = (ROOT / "README.md").read_text("utf-8")
        self.assertEqual(re.findall(r"^## (.+)$", readme, re.M),
                         ["安装", "检查脚本", "文件", "许可"])
        scripts = {p.name for p in (ROOT / "scripts").glob("*.py")}
        listed = set(re.findall(r"python scripts/([a-z_]+\.py)", readme))
        self.assertEqual(listed, scripts)
        self.assertEqual(len(list((ROOT / "references/details").glob("*.md"))), 14)
        for link in ("references/validation.md", "references/PRESERVATION.md"):
            self.assertIn("](" + link + ")", readme)
            self.assertTrue((ROOT / link).is_file())
        self.assertIn("21 份规范文档", readme)
        self.assertIn("两按钮界面", readme)


if __name__ == "__main__":
    unittest.main()
