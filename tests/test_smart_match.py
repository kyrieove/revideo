import unittest
from scripts.smart_match import (
    enumerate_windows,
    score_candidate,
    score_transition,
    propose,
)


class TestSmartMatch(unittest.TestCase):
    def test_score_candidate_distinguishes_energy(self):
        target_high_energy = {"role": "highlight", "target_energy": 0.9}
        target_low_energy = {"role": "ambient", "target_energy": 0.1}

        cand_active = {
            "features": {"motion_intensity": 0.85, "motion_direction": "left_to_right", "brightness": 0.6}
        }
        cand_calm = {
            "features": {"motion_intensity": 0.05, "motion_direction": "static", "brightness": 0.4}
        }

        # 高能量目标应给活跃素材更高分
        score_active_for_high = score_candidate(target_high_energy, cand_active)
        score_calm_for_high = score_candidate(target_high_energy, cand_calm)
        self.assertGreater(score_active_for_high, score_calm_for_high)

        # 低能量目标应给平稳素材更高分
        score_active_for_low = score_candidate(target_low_energy, cand_active)
        score_calm_for_low = score_candidate(target_low_energy, cand_calm)
        self.assertGreater(score_calm_for_low, score_active_for_low)

    def test_score_transition_penalizes_repeat(self):
        prev = {"asset_id": "assetA", "path": "a.mp4"}
        same = {"asset_id": "assetA", "path": "a.mp4"}
        diff = {"asset_id": "assetB", "path": "b.mp4"}

        # 同素材衔接应显著受惩罚
        repeat_score = score_transition(prev, same)
        diff_score = score_transition(prev, diff)
        self.assertLess(repeat_score, 0.4)
        self.assertGreater(diff_score, 0.7)

    def test_propose_returns_sorted_top_k(self):
        events = {
            "fps": 30.0,
            "fps_str": "30/1",
            "shots": [
                {"id": 1, "start": 0, "end": 30, "target_energy": 0.8}
            ]
        }
        index = {
            "assets": [
                {
                    "asset_id": "a1", "path": "1.mp4", "valid": True, "duration_seconds": 5.0,
                    "features": {"motion_intensity": 0.2, "motion_direction": "static", "brightness": 0.5}
                },
                {
                    "asset_id": "a2", "path": "2.mp4", "valid": True, "duration_seconds": 5.0,
                    "features": {"motion_intensity": 0.75, "motion_direction": "pan", "brightness": 0.6}
                }
            ]
        }
        res = propose(events, index, top_k=2)
        cands = res["slots"][0]["candidates"]
        self.assertEqual(len(cands), 2)
        # 验证降序排列
        self.assertGreaterEqual(cands[0]["score"], cands[1]["score"])


if __name__ == "__main__":
    unittest.main()
