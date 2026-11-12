"""test_diversity.py - 全局防垄断波束搜索算法与素材多样性单测"""

import unittest
from scripts.smart_compose import compose


class TestDiversityGate(unittest.TestCase):
    def test_anti_monopoly_hard_limit_and_adjacent_isolation(self):
        # 构造 6 个镜头的模拟时间轴
        timeline = {
            "fps": 30.0,
            "shots": [
                {"id": 1, "start": 0, "end": 30, "target_energy": 0.5},
                {"id": 2, "start": 30, "end": 60, "target_energy": 0.5},
                {"id": 3, "start": 60, "end": 90, "target_energy": 0.5},
                {"id": 4, "start": 90, "end": 120, "target_energy": 0.5},
                {"id": 5, "start": 120, "end": 150, "target_energy": 0.5},
                {"id": 6, "start": 150, "end": 180, "target_energy": 0.5}
            ]
        }
        # 素材池提供 4 个合法素材 (时长均足够切出窗口)
        assets = [
            {
                "asset_id": f"asset_{i}",
                "path": f"/media/rec_{i:02d}.mp4",
                "valid": True,
                "duration_seconds": 10.0,
                "features": {
                    "motion_intensity": 0.5,
                    "dominant_direction": "static",
                    "dominant_scene": f"scene_{i}",
                    "scene_tags": [f"scene_{i}"]
                }
            }
            for i in range(1, 5)
        ]
        index = {"assets": assets}

        # 运行波束搜索组接
        composed = compose(timeline, index, beam_width=8)
        shots = composed.get("shots", [])
        self.assertEqual(len(shots), 6)

        # 1. 验证相邻镜头绝对不出现同一素材
        for i in range(len(shots) - 1):
            cur_p = shots[i].get("material")
            next_p = shots[i + 1].get("material")
            self.assertIsNotNone(cur_p)
            self.assertIsNotNone(next_p)
            self.assertNotEqual(cur_p, next_p, f"镜头 {i+1} 与镜头 {i+2} 出现相邻同素材")

        # 2. 验证全片任何单个素材复用次数绝对 <= 2 次
        paths = [s.get("material") for s in shots if s.get("material")]
        from collections import Counter
        counts = Counter(paths)
        for p, count in counts.items():
            self.assertLessEqual(count, 2, f"素材 {p} 复用次数为 {count}，突破了硬门禁 <= 2 次限制")

    def test_travelogue_scene_diversity_ge_6(self):
        # 构造 12 个镜头的风光巡礼时间轴
        timeline = {
            "fps": 30.0,
            "shots": [
                {"id": i, "start": (i - 1) * 30, "end": i * 30, "target_energy": 0.3}
                for i in range(1, 13)
            ]
        }
        # 素材池提供 7 个不同风光场景的素材
        scenic_tags = ["snow_mountain", "sea_cloud", "sunset_tree", "watermill_night", "red_reeds", "cherry_sword", "pavilion_courtyard"]
        assets = [
            {
                "asset_id": f"scenic_{i}",
                "path": f"/media/scenic_{i:02d}.mp4",
                "valid": True,
                "duration_seconds": 15.0,
                "features": {
                    "motion_intensity": 0.3,
                    "dominant_direction": "static",
                    "dominant_scene": scenic_tags[i],
                    "scene_tags": [scenic_tags[i]]
                }
            }
            for i in range(len(scenic_tags))
        ]
        index = {"assets": assets}

        composed = compose(timeline, index, beam_width=8)
        shots = composed.get("shots", [])
        self.assertEqual(len(shots), 12)

        # 统计成片中涵盖的独立风光场景数
        chosen_scenes = set()
        for s in shots:
            sc = s.get("features", {}).get("dominant_scene")
            if sc:
                chosen_scenes.add(sc)
            else:
                # 依据 material 回查
                m = s.get("material")
                for a in assets:
                    if a["path"] == m:
                        chosen_scenes.add(a["features"]["dominant_scene"])
        self.assertGreaterEqual(len(chosen_scenes), 6, f"独立风光场景数少于 6 (实际: {len(chosen_scenes)})")


if __name__ == "__main__":
    unittest.main()
