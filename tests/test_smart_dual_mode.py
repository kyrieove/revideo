import unittest
from scripts.smart_timeline import generate_original_timeline
from scripts.smart_compose import compose


class TestSmartDualMode(unittest.TestCase):
    def test_original_timeline_without_reference(self):
        # 无参考片，基于高光和目标时长自动生成原创时间轴
        highlights = [{"id": "h1"}, {"id": "h2"}, {"id": "h3"}]
        tl = generate_original_timeline(highlights, fps_str="30/1", target_frames=180)
        self.assertEqual(tl["mode"], "original")
        self.assertEqual(tl["fps_str"], "30/1")
        self.assertEqual(len(tl["shots"]), 3)
        self.assertEqual(tl["shots"][0]["start"], 0)
        self.assertEqual(tl["shots"][-1]["end"], 180)

    def test_compose_deterministic(self):
        # 组接引擎的输出必须确定性可复现
        tl = generate_original_timeline([{"id": "h1"}], fps_str="30/1")
        mock_index = {
            "assets": [
                {
                    "asset_id": "a1",
                    "path": "test.mp4",
                    "valid": True,
                    "duration_seconds": 10.0
                }
            ]
        }
        res1 = compose(tl, mock_index)
        res2 = compose(tl, mock_index)
        self.assertEqual(res1["shots"][0]["material"], res2["shots"][0]["material"])
        self.assertEqual(res1["shots"][0]["selection"]["candidate_id"], res2["shots"][0]["selection"]["candidate_id"])


if __name__ == "__main__":
    unittest.main()
