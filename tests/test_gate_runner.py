import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_gates.py"
SPEC = importlib.util.spec_from_file_location("gate_runner", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


class RunnerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root / "original.bin").write_bytes(b"same")
        self.plan = {
            "schema_version": 1, "scope": "no-edit identity only",
            "checks": [{"id": "identity", "gate": "check_determinism",
                        "args": ["edit", "original.bin", "original.bin", "--no-edit"]}],
            "not_applicable": {g: "outside this identity-only scope" for g in runner.GATES if g != "check_determinism"},
        }

    def load(self):
        p = self.root / "plan.json"
        p.write_text(json.dumps(self.plan), encoding="utf-8")
        return runner.load_plan(p)

    def test_real_child_and_relative_paths(self):
        report = runner.run(self.load(), self.root)
        self.assertEqual(report["status"], "pass", report)
        self.assertEqual(report["checks"][0]["exit_code"], 0)
        self.assertTrue(report["checks"][0]["stdout"])

    def test_no_silent_gate_omission(self):
        self.plan["not_applicable"] = {}
        with self.assertRaises(ValueError):
            self.load()

    def test_reject_arbitrary_command(self):
        self.plan["checks"][0]["gate"] = "../evil"
        with self.assertRaises(ValueError):
            self.load()

    def test_reject_empty_checks(self):
        self.plan["checks"] = []
        with self.assertRaises(ValueError):
            self.load()

    def test_reject_duplicate_id(self):
        self.plan["checks"] *= 2
        with self.assertRaises(ValueError):
            self.load()

    def test_duplicate_json_key(self):
        p = self.root / "plan.json"
        p.write_text('{"schema_version":1,"schema_version":1}', encoding="utf-8")
        with self.assertRaises(ValueError):
            runner.load_plan(p)

    def test_cli_invalid_is_json_failure(self):
        p = subprocess.run([sys.executable, "-B", str(SCRIPT), "--unknown"],
                           capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(p.returncode, 1)
        self.assertEqual(json.loads(p.stdout)["status"], "fail")

    def test_not_verified_is_not_success(self):
        p = subprocess.CompletedProcess([], 2, '{"status":"not_verified","ok":false}', "")
        with patch.object(runner.subprocess, "run", return_value=p):
            self.assertEqual(runner.run(self.load(), self.root)["status"], "not_verified")

    def test_false_exit_zero_rejected(self):
        p = subprocess.CompletedProcess([], 0, '{"status":"fail","ok":false}', "")
        with patch.object(runner.subprocess, "run", return_value=p):
            self.assertEqual(runner.run(self.load(), self.root)["status"], "fail")

    def test_timeout_not_verified(self):
        with patch.object(runner.subprocess, "run", side_effect=subprocess.TimeoutExpired([], 1)):
            self.assertEqual(runner.run(self.load(), self.root)["status"], "not_verified")

    def test_execution_error_not_verified(self):
        with patch.object(runner.subprocess, "run", side_effect=OSError("fixture denied")):
            self.assertEqual(runner.run(self.load(), self.root)["status"], "not_verified")

    def test_nul_and_bool_timeout_rejected(self):
        self.plan["checks"][0]["args"] = ["\0"]
        with self.assertRaises(ValueError):
            self.load()
        self.plan["checks"][0]["args"] = []
        self.plan["timeout_seconds"] = True
        with self.assertRaises(ValueError):
            self.load()


if __name__ == "__main__":
    unittest.main()
