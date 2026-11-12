import copy
import unittest
from scripts.smart_compose import compose
from scripts.smart_timeline import generate_original_timeline


class TestSmartCompose(unittest.TestCase):
    def setUp(self):
        self.timeline = {
            "mode": "original",
            "fps": 30.0,
            "fps_str": "30/1",
            "frames": 90,
            "shots": [
                {"id": 1, "start": 0, "end": 30, "target_energy": 0.8},
                {"id": 2, "start": 30, "end": 60, "target_energy": 0.3},
                {"id": 3, "start": 60, "end": 90, "target_energy": 0.9}
            ]
        }
        self.index = {
            "assets": [
                {
                    "asset_id": "a1",
                    "path": "clip1.mp4",
                    "valid": True,
                    "duration_seconds": 10.0,
                    "features": {"motion_intensity": 0.8, "motion_direction": "left_to_right", "brightness": 0.6}
                },
                {
                    "asset_id": "a2",
                    "path": "clip2.mp4",
                    "valid": True,
                    "duration_seconds": 10.0,
                    "features": {"motion_intensity": 0.2, "motion_direction": "static", "brightness": 0.4}
                }
            ]
        }

    def test_compose_uses_beam_search_and_is_deterministic(self):
        # 验证波束搜索的确定性
        res1 = compose(self.timeline, self.index, beam_width=4, top_k=2)
        res2 = compose(self.timeline, self.index, beam_width=4, top_k=2)

        shots1 = res1["shots"]
        shots2 = res2["shots"]
        self.assertEqual(len(shots1), 3)
        self.assertEqual(len(shots2), 3)

        for s1, s2 in zip(shots1, shots2):
            self.assertEqual(s1["selection"]["candidate_id"], s2["selection"]["candidate_id"])
            self.assertEqual(s1["material"], s2["material"])

        # 验证包含 beam_search_meta
        self.assertIn("beam_search_meta", res1)
        self.assertEqual(res1["beam_search_meta"]["beam_width"], 4)

    def test_compose_avoids_consecutive_same_asset_when_alternative_exists(self):
        # 验证相邻镜头惩罚使高能量与低能量交替时选择不同素材
        res = compose(self.timeline, self.index, beam_width=8, top_k=2)
        mats = [s["material"] for s in res["shots"]]
        # 镜头 1 (0.8) 和镜头 2 (0.3) 应当选取不同素材
        self.assertNotEqual(mats[0], mats[1], "Consecutive shots should not use the same asset when distinct options exist")


if __name__ == "__main__":
    unittest.main()
