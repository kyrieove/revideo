import os
import re
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from scripts.smart_inspect import (
    extract_audio_envelope,
    extract_motion_curve,
    generate_rhythm_inspector
)


class TestSmartInspect(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="revideo_test_inspect_")
        cls.video_path = os.path.join(cls.tmp_dir, "test_clip.mp4")
        # 生成带音频和视频的测试素材 (2 秒，10fps，有音频正弦波)
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=size=320x180:rate=10:duration=2",
            "-f", "lavfi", "-i", "sine=frequency=440:duration=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac",
            cls.video_path
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_extract_audio_envelope_and_motion(self):
        env = extract_audio_envelope(self.video_path, 100)
        self.assertIsInstance(env, list)
        self.assertGreater(len(env), 0)

        motion = extract_motion_curve(self.video_path, 10.0)
        self.assertIsInstance(motion, list)
        self.assertGreater(len(motion), 0)

    def test_generate_inspector_creates_valid_single_file_html(self):
        events = {
            "fps": 10.0,
            "frames": 20,
            "shots": [
                {"id": 1, "start": 0, "end": 10},
                {"id": 2, "start": 10, "end": 20}
            ],
            "music": {
                "drums": [
                    {"f": 0, "t": 0.0, "s": 0.8},
                    {"f": 10, "t": 1.0, "s": 0.9}
                ]
            }
        }
        out_html = os.path.join(self.tmp_dir, "inspector.html")
        res_path = generate_rhythm_inspector(self.video_path, events, out_html)
        self.assertTrue(os.path.isfile(res_path))
        self.assertLess(os.path.getsize(res_path), 150 * 1024)

        with open(res_path, "r", encoding="utf-8") as f:
            content = f.read()

        # 验证核心元素和控件
        self.assertIn("canvas id=\"flowCanvas\"", content)
        self.assertIn("class=\"center-playhead\"", content)
        self.assertIn("pixelsPerSecond", content)
        self.assertIn("KeyJ", content)
        self.assertIn("KeyK", content)
        self.assertIn("KeyL", content)

    def test_inspector_has_zero_external_cdn_links(self):
        events = {
            "fps": 10.0,
            "frames": 20,
            "shots": [{"id": 1, "start": 0, "end": 20}]
        }
        out_html = os.path.join(self.tmp_dir, "inspector_isolated.html")
        generate_rhythm_inspector(self.video_path, events, out_html)

        with open(out_html, "r", encoding="utf-8") as f:
            content = f.read()

        # 严禁任何外部 script 或 link 引用
        external_scripts = re.findall(r'<script[^>]+src=["\'](https?://[^"\']+)["\']', content)
        external_styles = re.findall(r'<link[^>]+href=["\'](https?://[^"\']+)["\']', content)
        self.assertEqual(len(external_scripts), 0, f"Found external scripts: {external_scripts}")
        self.assertEqual(len(external_styles), 0, f"Found external styles: {external_styles}")


if __name__ == "__main__":
    unittest.main()
