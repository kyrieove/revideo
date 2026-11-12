"""test_semantic_alignment.py - 语音对白转写、叙事三阶段切分与 travelogue 语义打分单测"""

import unittest
import numpy as np
from scripts.semantic_extract import extract_speech_and_phases
from scripts.smart_match import score_candidate
from scripts.viewfinder_fx import generate_viewfinder_overlay, apply_viewfinder_to_frame


class TestSemanticAlignment(unittest.TestCase):
    def test_extract_speech_and_phases_contract(self):
        # 边界与空音频契约测试
        res = extract_speech_and_phases("non_existent_audio.mp3", video_duration=52.0)
        self.assertIn("dialogue", res)
        self.assertIn("phases", res)
        self.assertIn("keywords", res)
        self.assertEqual(len(res["phases"]), 3)
        self.assertEqual(res["phases"][0]["phase"], "setup")
        self.assertEqual(res["phases"][1]["phase"], "montage")
        self.assertEqual(res["phases"][2]["phase"], "resolution")

    def test_travelogue_preset_prioritizes_scene_match(self):
        target_snow = {
            "target_energy": 0.8,
            "target_scene": "snow_lake",
            "role": "ambient"
        }
        # 候选 1：高动作能量但场景不匹配 (战斗/切菜)
        cand_combat = {
            "features": {
                "motion_intensity": 0.8,
                "motion_direction": "pan",
                "dominant_scene": "combat",
                "scene_tags": ["combat"]
            }
        }
        # 候选 2：动作能量低但场景精准匹配 (雪山冰湖风光)
        cand_snow = {
            "features": {
                "motion_intensity": 0.2,
                "motion_direction": "pan",
                "dominant_scene": "snow_lake",
                "scene_tags": ["snow_lake"]
            }
        }

        # 默认模式下：过度看重动作能量，可能误选 combat
        score_default_combat = score_candidate(target_snow, cand_combat, preset="default")
        score_default_snow = score_candidate(target_snow, cand_snow, preset="default")
        self.assertGreater(score_default_combat, score_default_snow)

        # travelogue 风光打卡模式下：场景契合度第一核心，必然选 snow_lake
        score_travel_combat = score_candidate(target_snow, cand_combat, preset="travelogue")
        score_travel_snow = score_candidate(target_snow, cand_snow, preset="travelogue")
        self.assertGreater(score_travel_snow, score_travel_combat)
        self.assertIn("scene_match", cand_snow.get("reason_codes", []))

    def test_viewfinder_overlay_generation_and_blending(self):
        overlay = generate_viewfinder_overlay(1920, 1080, rec_red=True)
        self.assertEqual(overlay.shape, (1080, 1920, 4))
        self.assertEqual(overlay.dtype, np.uint8)
        self.assertTrue(np.any(overlay[:, :, 3] > 0))  # 存在非透明内容

        frame = np.full((1080, 1920, 3), 100, dtype=np.uint8)
        blended = apply_viewfinder_to_frame(frame, overlay)
        self.assertEqual(blended.shape, (1080, 1920, 3))
        # 确保叠加了非背景色的像素
        self.assertFalse(np.array_equal(frame, blended))


if __name__ == "__main__":
    unittest.main()
