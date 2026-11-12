import copy
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from scripts.remake import validate_timeline
from scripts.smart_schema import fingerprint_render_plan


class TestRemakeApprovalGate(unittest.TestCase):
    def setUp(self):
        self.valid_legacy = {
            "fps": 30.0,
            "fps_str": "30/1",
            "frames": 30,
            "shots": [
                {"id": 1, "start": 0, "end": 30, "material": "dummy.mp4", "material_in": 0.0}
            ]
        }

    def test_accepts_legacy_manual_events(self):
        # 原有不带 smart_workflow 的人工事件表必须 100% 正常通过
        validate_timeline(self.valid_legacy)

    def test_rejects_unapproved_render(self):
        # 带有 smart_workflow 但未审批的拒绝正式渲染
        ev = copy.deepcopy(self.valid_legacy)
        ev["smart_workflow"] = {
            "schema_version": 1,
            "status": "proposed"
        }
        with self.assertRaises(ValueError) as ctx:
            validate_timeline(ev)
        self.assertIn("SMART_WORKFLOW_NOT_APPROVED", str(ctx.exception))

    def test_rejects_tampered_approval(self):
        # 审批后如果篡改了镜头参数，指纹不符拒绝渲染
        ev = copy.deepcopy(self.valid_legacy)
        ev["smart_workflow"] = {
            "schema_version": 1,
            "status": "approved",
            "approval_sha256": fingerprint_render_plan(ev)
        }
        # 模拟篡改素材入点
        ev["shots"][0]["material_in"] = 99.9
        with self.assertRaises(ValueError) as ctx:
            validate_timeline(ev)
        self.assertIn("SMART_WORKFLOW_APPROVAL_STALE", str(ctx.exception))

    def test_cli_rejects_forged_approval_without_pythonpath(self):
        # 从根目录执行 python scripts/remake.py，清空 PYTHONPATH，验证不会因为导入问题静默跳过指纹校验
        ev = copy.deepcopy(self.valid_legacy)
        ev["smart_workflow"] = {
            "schema_version": 1,
            "status": "approved",
            "approval_sha256": "fake_forged_sha"
        }
        with tempfile.TemporaryDirectory() as td:
            ev_file = os.path.join(td, "events.json")
            out_file = os.path.join(td, "out.mp4")
            with open(ev_file, "w", encoding="utf-8") as f:
                json.dump(ev, f)

            env = os.environ.copy()
            env.pop("PYTHONPATH", None)

            remake_py = str(Path(__file__).resolve().parent.parent / "scripts" / "remake.py")
            cmd = [sys.executable, "-X", "utf8", remake_py, ev_file, out_file]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=env)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("SMART_WORKFLOW_APPROVAL_STALE", proc.stderr + proc.stdout)
            self.assertFalse(os.path.exists(out_file), "Forged approval must not generate output video")


if __name__ == "__main__":
    unittest.main()
