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



    def test_window_feature_cache_and_direction_schema(self):
        """验证 F-009 窗口特征缓存与 F-010 运动方向契约一致性。"""
        from scripts.smart_match import enumerate_windows, score_candidate, clear_window_feature_cache, _WINDOW_FEATURE_CACHE
        clear_window_feature_cache()

        asset = {
            "asset_id": "test_motion_asset",
            "path": "dummy.mp4",
            "source_fingerprint": "fp_test_123",
            "duration_seconds": 3.0,
            "valid": True,
            "features": {"motion_intensity": 0.5, "motion_direction": "static"},
            "sampled_frames": [
                {"timestamp": 0.2, "luminance": 0.6, "motion": 0.8, "direction": "right"},
                {"timestamp": 0.5, "luminance": 0.6, "motion": 0.8, "direction": "right"},
                {"timestamp": 0.8, "luminance": 0.6, "motion": 0.8, "direction": "right"},
                {"timestamp": 1.2, "luminance": 0.4, "motion": 0.2, "direction": "left"},
                {"timestamp": 1.5, "luminance": 0.4, "motion": 0.2, "direction": "left"},
            ]
        }

        # 1. 首次枚举窗口，应计算局部特征并存入缓存
        windows_1 = enumerate_windows(asset, required_duration=1.0, step=1.0)
        self.assertTrue(len(windows_1) >= 2)
        w0_feats = windows_1[0]["features"]
        self.assertEqual(w0_feats.get("motion_direction"), "right")
        self.assertEqual(w0_feats.get("dominant_direction"), "right")
        self.assertTrue(len(_WINDOW_FEATURE_CACHE) > 0)

        # 2. 二次枚举窗口，应直接命中缓存
        windows_2 = enumerate_windows(asset, required_duration=1.0, step=1.0)
        self.assertEqual(windows_1[0]["features"], windows_2[0]["features"])

        # 3. 验证打分契约：目标为 right 时，right 窗口得分高于 left 窗口
        target_right = {"target_energy": 0.8, "target_direction": "right"}
        score_w0 = score_candidate(target_right, windows_1[0])
        score_w1 = score_candidate(target_right, windows_1[1])
        self.assertGreater(score_w0, score_w1)


    def test_cache_isolation_on_empty_fingerprint_and_resampling(self):
        """验证 F-011：空指纹素材隔离、采样版本失效与真实调用断言。"""
        from unittest.mock import patch
        from scripts.smart_match import enumerate_windows, clear_window_feature_cache
        clear_window_feature_cache()

        # 素材A：空指纹，运动向右
        asset_a = {
            "asset_id": "asset_A",
            "source_fingerprint": "",  # 空指纹
            "duration_seconds": 2.0,
            "valid": True,
            "features": {"motion_intensity": 0.5, "motion_direction": "static"},
            "sampled_frames": [
                {"timestamp": 0.2, "luminance": 0.5, "motion": 0.9, "direction": "right"},
                {"timestamp": 0.5, "luminance": 0.5, "motion": 0.9, "direction": "right"}
            ]
        }
        # 素材B：同样空指纹，但时间相同且运动向左
        asset_b = {
            "asset_id": "asset_B",
            "source_fingerprint": "",  # 空指纹
            "duration_seconds": 2.0,
            "valid": True,
            "features": {"motion_intensity": 0.2, "motion_direction": "static"},
            "sampled_frames": [
                {"timestamp": 0.2, "luminance": 0.2, "motion": 0.1, "direction": "left"},
                {"timestamp": 0.5, "luminance": 0.2, "motion": 0.1, "direction": "left"}
            ]
        }

        # 1. 验证双素材空指纹各自独立，A向右，B向左，绝不发生缓存交叉污染
        win_a = enumerate_windows(asset_a, required_duration=1.0, step=1.0)
        win_b = enumerate_windows(asset_b, required_duration=1.0, step=1.0)
        self.assertEqual(win_a[0]["features"]["motion_direction"], "right")
        self.assertEqual(win_b[0]["features"]["motion_direction"], "left")

        # 2. 验证真实缓存命中：mock extract_features，第二次调用 enumerate_windows 不应再调用 extract_features
        with patch("scripts.material_index.extract_features") as mock_extract:
            win_a_hit = enumerate_windows(asset_a, required_duration=1.0, step=1.0)
            mock_extract.assert_not_called()
            self.assertEqual(win_a_hit[0]["features"]["motion_direction"], "right")

        # 3. 验证采样配置变更：素材A追加了新采样帧，缓存键版本变更，必须使旧缓存失效并重新计算
        asset_a_resampled = dict(asset_a)
        asset_a_resampled["sampled_frames"] = list(asset_a["sampled_frames"]) + [
            {"timestamp": 0.8, "luminance": 0.9, "motion": 0.95, "direction": "up"}
        ]
        with patch("scripts.material_index.extract_features") as mock_extract2:
            mock_extract2.return_value = {"motion_direction": "up", "dominant_direction": "up", "brightness": 0.8, "motion_intensity": 0.9}
            win_a_resampled = enumerate_windows(asset_a_resampled, required_duration=1.0, step=1.0)
            self.assertEqual(mock_extract2.call_count, 1)
            self.assertEqual(win_a_resampled[0]["features"]["motion_direction"], "up")

if __name__ == "__main__":
    unittest.main()
