import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts.smart_preview import generate_preview, render_draft_video


class TestSmartPreview(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="revideo_test_preview_")
        cls.clip1 = os.path.join(cls.tmp_dir, "test1.mp4")
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=1:r=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.clip1
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_preview_html_escapes_xss_and_paths(self):
        # 验证对素材文件名中包含的特殊字符进行转义
        xss_mat = "clips/<script>alert(1)</script>&path.mp4"
        events = {
            "fps": 30.0,
            "fps_str": "30/1",
            "frames": 30,
            "shots": [
                {"id": "1<>&\"", "start": 0, "end": 30, "material": xss_mat}
            ]
        }
        out_html = os.path.join(self.tmp_dir, "test_xss.html")
        generate_preview(events, out_html, generate_draft_if_missing=False)
        
        with open(out_html, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertNotIn("<script>alert(1)</script>", content)
        self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;&amp;path.mp4", content)

    def test_preview_contains_playable_video(self):
        # 验证包含可播放视频
        events = {
            "fps": 10.0,
            "fps_str": "10/1",
            "frames": 10,
            "shots": [
                {"id": 1, "start": 0, "end": 10, "material": self.clip1}
            ]
        }
        draft_mp4 = os.path.join(self.tmp_dir, "draft.mp4")
        render_draft_video(events, draft_mp4)
        self.assertTrue(os.path.isfile(draft_mp4))

        out_html = os.path.join(self.tmp_dir, "preview_with_video.html")
        generate_preview(events, out_html, draft_video_path=draft_mp4)
        with open(out_html, "r", encoding="utf-8") as f:
            content = f.read()

        self.assertIn("<video", content)
        self.assertIn("data:video/mp4;base64,", content)


if __name__ == "__main__":
    unittest.main()
