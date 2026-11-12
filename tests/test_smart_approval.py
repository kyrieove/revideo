import copy
import unittest
from scripts.smart_schema import fingerprint_render_plan
from scripts.smart_workflow import approve, build_proposed_plan


class TestSmartApproval(unittest.TestCase):
    def setUp(self):
        self.source_events = {
            "fps": 30.0,
            "fps_str": "30/1",
            "frames": 60,
            "size": [1280, 720],
            "shots": [
                {"id": 1, "start": 0, "end": 30, "material": None},
                {"id": 2, "start": 30, "end": 60, "material": None}
            ]
        }
        self.candidates = {
            "schema_version": 1,
            "slots": [
                {
                    "shot_id": 1,
                    "candidates": [
                        {
                            "candidate_id": "asset1@0.0",
                            "asset_id": "asset1",
                            "path": "clips/1.mp4",
                            "source_fingerprint": "fp_asset1",
                            "in_sec": 0.0,
                            "score": 0.85
                        }
                    ]
                },
                {
                    "shot_id": 2,
                    "candidates": [
                        {
                            "candidate_id": "asset2@1.0",
                            "asset_id": "asset2",
                            "path": "clips/2.mp4",
                            "source_fingerprint": "fp_asset2",
                            "in_sec": 1.0,
                            "score": 0.88
                        }
                    ]
                }
            ]
        }
        self.proposed = build_proposed_plan(self.source_events, self.candidates)
        self.valid_decisions = {
            "schema_version": 1,
            "candidates_sha256": fingerprint_render_plan(self.candidates),
            "source_events_sha256": fingerprint_render_plan(self.source_events),
            "decisions": [
                {"shot_id": 1, "selected_candidate_id": "asset1@0.0", "confirmed": True},
                {"shot_id": 2, "selected_candidate_id": "asset2@1.0", "confirmed": True}
            ]
        }
        self.index = {
            "schema_version": 1,
            "assets": [
                {"path": "clips/1.mp4", "source_fingerprint": "fp_asset1"},
                {"path": "clips/2.mp4", "source_fingerprint": "fp_asset2"}
            ]
        }

    def test_approve_requires_review_decisions(self):
        # 无 decisions 时必须抛出 ValueError
        with self.assertRaises(ValueError):
            approve(self.proposed, None, self.candidates, self.source_events, self.index)

    def test_rejects_missing_decisions(self):
        # 缺少镜头 2 的决策
        incomplete = copy.deepcopy(self.valid_decisions)
        incomplete["decisions"] = [incomplete["decisions"][0]]
        with self.assertRaises(ValueError):
            approve(self.proposed, incomplete, self.candidates, self.source_events, self.index)

    def test_rejects_implicit_confirmation(self):
        # confirmed 未显式指定为 True (None 或 False)
        implicit = copy.deepcopy(self.valid_decisions)
        implicit["decisions"][0]["confirmed"] = False
        with self.assertRaises(ValueError):
            approve(self.proposed, implicit, self.candidates, self.source_events, self.index)

    def test_rejects_candidate_mismatch(self):
        # 伪造不存在的候选 ID
        mismatch = copy.deepcopy(self.valid_decisions)
        mismatch["decisions"][0]["selected_candidate_id"] = "forged@999.0"
        with self.assertRaises(ValueError):
            approve(self.proposed, mismatch, self.candidates, self.source_events, self.index)

    def test_rejects_stale_asset(self):
        # 素材发生篡改/指纹不一致
        tampered_index = copy.deepcopy(self.index)
        tampered_index["assets"][0]["source_fingerprint"] = "tampered_hash"
        with self.assertRaises(ValueError):
            approve(self.proposed, self.valid_decisions, self.candidates, self.source_events, tampered_index)

    def test_rejects_changed_reference_timeline(self):
        # 复刻模式下切点或帧数被修改
        tampered_prop = copy.deepcopy(self.proposed)
        tampered_prop["shots"][0]["end"] = 35
        tampered_prop["shots"][1]["start"] = 35
        with self.assertRaises(ValueError):
            approve(tampered_prop, self.valid_decisions, self.candidates, self.source_events, self.index)

    def test_accepts_valid_decisions(self):
        # 完整合法输入必须顺利通过审批并生成 approval_sha256
        approved = approve(self.proposed, self.valid_decisions, self.candidates, self.source_events, self.index)
        self.assertEqual(approved["smart_workflow"]["status"], "approved")
        self.assertIsNotNone(approved["smart_workflow"]["approval_sha256"])


if __name__ == "__main__":
    unittest.main()
