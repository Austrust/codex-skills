import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).parent))
import init_report_package as init
from validate_report_package import Validation
from report_core import validate_report


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
    def tearDown(self):
        self.temp.cleanup()
    def create(self, *extra):
        args = init.build_parser().parse_args(["--root", str(self.root), "--task", "test", *extra])
        return init.create_package(args)
    def test_lean_no_side_effects(self):
        (self.root / "00_project").mkdir()
        run = self.create()
        self.assertEqual({x.name for x in run.iterdir()}, {"REPORT.md"})
        self.assertFalse((self.root / init.CONFIG_RELATIVE_PATH).exists())
        v = Validation(True)
        validate_report(v, run, {})
        self.assertFalse(v.errors, v.errors)
        v = Validation()
        validate_report(v, run, {})
        self.assertTrue(v.errors)  # unfinished template is not a completed report
    def test_custom_placement_and_config(self):
        cfg = self.root / "settings.json"
        cfg.write_text('{"default_language":"en"}')
        run = self.create("--config", "settings.json", "--package-dir", "analysis/baseline")
        self.assertEqual(run, self.root / "analysis/baseline")
        self.assertEqual({p.name for p in run.iterdir()}, {"REPORT.md"})
        self.assertIn("Result and context", (run / "REPORT.md").read_text())
        with self.assertRaises(SystemExit):
            self.create("--package-dir", "analysis/baseline")
        run = self.create("--task-package", "analysis/flow", "--run-dir-name", "experiments")
        self.assertEqual(run.parent, self.root / "analysis/flow/experiments")
        self.assertFalse((self.root / "00_project").exists())

    def test_audited_scaffold(self):
        run = self.create("--profile", "audited")
        self.assertEqual({x.name for x in run.iterdir()}, {"REPORT.md", "AUDIT_MANIFEST.json"})
        v = Validation(True)
        validate_report(v, run, json.loads((run / "AUDIT_MANIFEST.json").read_text()))
        self.assertFalse(v.errors, v.errors)
    def test_legacy_config_and_override(self):
        cfg = self.root / init.CONFIG_RELATIVE_PATH
        cfg.parent.mkdir()
        cfg.write_text(json.dumps({"default_language":"en", "report_package":{"required_files":["QC_CHECKLIST.md"],"required_dirs":["logs"],"profile":"audited"}}))
        before = cfg.read_bytes()
        run = self.create("--profile", "lean")
        self.assertEqual({x.name for x in run.iterdir()}, {"REPORT.md"})
        self.assertEqual(cfg.read_bytes(), before)
    def test_collision_preserves_existing(self):
        one = self.create("--timestamp", "fixed")
        old = (one / "REPORT.md").read_bytes()
        two = self.create("--timestamp", "fixed")
        self.assertNotEqual(one, two)
        self.assertEqual((one / "REPORT.md").read_bytes(), old)
    def test_valid_audit_and_bad_lineage(self):
        run = self.create("--profile", "audited")
        (run / "result.txt").write_text("2")
        (run / "REPORT.md").write_text("Audit status: complete\nReproducibility: reproducible\n\nMean is 2 mm. [Result](result.txt)\n")
        m = json.loads((run / "AUDIT_MANIFEST.json").read_text())
        m.update(draft=False,audit_status="complete",reproducibility="reproducible",
                 inputs=[{"id":"i","path":"input.csv","identity":"dataset version 1"}],
                 steps=[{"id":"s","inputs":["i"],"method":"mean","parameters":{},"method_basis":"user request","evidence_type":"executed_this_session"}],
                 outputs=[{"id":"o","path":"result.txt","derived_from_inputs":["i"],"derived_from_steps":["s"],"evidence_type":"executed_this_session"}],
                 checks=[{"check":"count","result":"3 rows, no missing values"}],
                 reproduction={"working_directory":".","procedure":"python mean.py","code_identity":"git commit abc","environment":"Python 3.12"})
        v=Validation()
        validate_report(v,run,m)
        self.assertFalse(v.errors,v.errors)
        m["outputs"][0]["derived_from_steps"]=["absent"]
        v=Validation()
        validate_report(v,run,m)
        self.assertTrue(any("lineage" in e for e in v.errors))
    def test_missing_manifest_and_broken_link(self):
        run=self.create("--profile","audited")
        (run/"REPORT.md").write_text("<!-- profile=audited -->\nAudit status: partial\nReproducibility: not_assessed\n[Missing](missing.png)\n")
        v=Validation()
        validate_report(v,run,{})
        self.assertTrue(any("AUDIT_MANIFEST" in e for e in v.errors))
        self.assertTrue(any("broken" in e for e in v.errors))
    def test_explicit_config_init(self):
        init.init_project_config(self.root)
        cfg=json.loads((self.root/init.CONFIG_RELATIVE_PATH).read_text())
        self.assertEqual(cfg["report_package"]["profile"],"lean")
        self.assertFalse(cfg["workflow"]["formal_requires_plan_confirmation"])


    def test_schema_one_still_uses_legacy_validation(self):
        import subprocess
        run = self.create()
        (run / "AUDIT_MANIFEST.json").write_text(json.dumps({"schema_version":"1.0"}))
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("validate_report_package.py")), str(run)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("PROCESSING_PLAN.md", result.stdout)

    def test_malformed_json_is_not_treated_as_lean(self):
        import subprocess
        run = self.create()
        (run / "AUDIT_MANIFEST.json").write_text("{broken")
        result = subprocess.run([sys.executable, str(Path(__file__).with_name("validate_report_package.py")), str(run), "--allow-draft"], capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("invalid JSON", result.stdout)


if __name__ == "__main__":
    unittest.main()
