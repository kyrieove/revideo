import unittest
import copy
from scripts.remake import validate_timeline


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
        from scripts.smart_workflow import approve
        ev = copy.deepcopy(self.valid_legacy)
        approved = approve(ev)
        # 模拟篡改切点
        approved["shots"][0]["material_in"] = 99.9
        with self.assertRaises(ValueError) as ctx:
            validate_timeline(approved)
        self.assertIn("SMART_WORKFLOW_APPROVAL_STALE", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
