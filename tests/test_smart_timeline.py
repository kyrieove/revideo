import unittest
from scripts.smart_timeline import generate_original_timeline


class TestSmartTimeline(unittest.TestCase):
    def test_original_without_reference(self):
        # 无参考片自主创作时间轴
        tl = generate_original_timeline(
            highlights=[{"duration": 2.0}, {"duration": 2.5}],
            fps_str="30/1"
        )
        self.assertEqual(tl["mode"], "original")
        self.assertEqual(tl["fps"], 30.0)
        self.assertGreater(tl["frames"], 0)
        self.assertTrue(len(tl["shots"]) >= 2)

    def test_no_audio_mode_is_none(self):
        # 未提供 beat_frames / 音频时，audio.mode 必须为 "none"，杜绝误标为 "bgm"
        tl = generate_original_timeline(highlights=[{"duration": 1.0}])
        self.assertEqual(tl["audio"]["mode"], "none")

    def test_with_audio_beats_is_bgm(self):
        # 提供外部节拍时，audio.mode 为 "bgm"
        tl = generate_original_timeline(beat_frames=[30, 60, 90])
        self.assertEqual(tl["audio"]["mode"], "bgm")

    def test_exact_target_frames_continuity(self):
        # 严格覆盖 target_frames，无间隙无超出
        target = 100
        tl = generate_original_timeline(target_frames=target, fps_str="25/1")
        self.assertEqual(tl["frames"], target)
        
        # 检验连续性
        curr = 0
        for s in tl["shots"]:
            self.assertEqual(s["start"], curr)
            self.assertGreater(s["end"], s["start"])
            curr = s["end"]
        self.assertEqual(curr, target)


if __name__ == "__main__":
    unittest.main()
