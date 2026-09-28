"""Distribution integrity, not assertions about prose wording."""
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def test_local_document_links_resolve(self):
        for path in [ROOT / "SKILL.md", ROOT / "README.md", *sorted((ROOT / "references").glob("*.md"))]:
            for link in re.findall(r"\]\(([^)]+)\)", path.read_text(encoding="utf-8")):
                if "://" in link or link.startswith("#"):
                    continue
                target = (path.parent / link.split("#", 1)[0]).resolve()
                self.assertTrue(target.is_relative_to(ROOT), (path, link))
                self.assertTrue(target.is_file(), (path, link))

    def test_metadata_aliases_identical(self):
        self.assertEqual((ROOT / "agents/openai.yaml").read_bytes(),
                         (ROOT / "agents/skill.yaml").read_bytes())

    def test_all_script_cli_help(self):
        for script in sorted((ROOT / "scripts").glob("*.py")):
            with self.subTest(script=script.name):
                p = subprocess.run([sys.executable, "-B", str(script), "--help"],
                                   capture_output=True, text=True, encoding="utf-8",
                                   env={**os.environ, "PYTHONIOENCODING": "utf-8"})
                self.assertEqual(p.returncode, 0, p.stderr)
                self.assertIn("usage:", p.stdout.lower())

    def test_python_files_compile_without_cache(self):
        for path in ROOT.rglob("*.py"):
            compile(path.read_text(encoding="utf-8-sig"), str(path), "exec")


if __name__ == "__main__":
    unittest.main()
