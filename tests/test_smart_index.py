import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from scripts.material_index import (
    discover_assets,
    probe_asset,
    sample_asset,
    extract_features,
    build_index,
    load_index,
    compute_source_fingerprint,
)


class TestSmartIndex(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="revideo_test_index_")
        cls.black_clip = os.path.join(cls.tmp_dir, "black.mp4")
        cls.white_clip = os.path.join(cls.tmp_dir, "white.mp4")
        cls.moving_clip = os.path.join(cls.tmp_dir, "moving.mp4")

        # 1. 纯黑视频 1秒
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=black:s=160x90:d=1:r=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.black_clip
        ], check=True)

        # 2. 纯白视频 1秒
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=white:s=160x90:d=1:r=10",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.white_clip
        ], check=True)

        # 3. 动态移动测试视频 (彩条水平滚动产生真实且显著的运动与动向) 1秒
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "smptebars=s=160x90:d=1:r=10",
            "-vf", "scroll=horizontal=0.1",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.moving_clip
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_probe_asset(self):
        meta = probe_asset(self.black_clip)
        self.assertTrue(meta["valid"])
        self.assertEqual(meta["width"], 160)
        self.assertEqual(meta["height"], 90)
        self.assertAlmostEqual(meta["duration_seconds"], 1.0, places=1)

    def test_extracts_real_luminance(self):
        # 验证真实亮度区分能力：白片亮度应远大于黑片
        black_frames = sample_asset(self.black_clip, sample_fps=5)
        white_frames = sample_asset(self.white_clip, sample_fps=5)
        self.assertTrue(len(black_frames) > 0)
        self.assertTrue(len(white_frames) > 0)

        black_lum = sum(f["luminance"] for f in black_frames) / len(black_frames)
        white_lum = sum(f["luminance"] for f in white_frames) / len(white_frames)
        self.assertLess(black_lum, 0.15)
        self.assertGreater(white_lum, 0.85)

    def test_extracts_real_motion_features(self):
        # 验证真实运动区分能力：静态片 motion 极低，动态测试源 motion 显著
        static_frames = sample_asset(self.black_clip, sample_fps=5)
        moving_frames = sample_asset(self.moving_clip, sample_fps=5)
        
        static_motion = sum(f["motion"] for f in static_frames) / len(static_frames)
        moving_motion = sum(f["motion"] for f in moving_frames) / len(moving_frames)
        self.assertLess(static_motion, 0.02)
        self.assertGreater(moving_motion, 0.05)

    def test_invalidates_modified_source(self):
        # 验证素材修改后指纹发生改变
        test_file = os.path.join(self.tmp_dir, "temp_mod.mp4")
        shutil.copyfile(self.black_clip, test_file)
        fp1 = compute_source_fingerprint(test_file)

        # 篡改文件内容
        with open(test_file, "ab") as f:
            f.write(b"tamper_bytes_append")
        fp2 = compute_source_fingerprint(test_file)
        self.assertNotEqual(fp1, fp2, "Fingerprint must change when source file is modified")

    def test_build_and_load_index(self):
        index_file = os.path.join(self.tmp_dir, "index.json")
        doc = build_index([self.tmp_dir], index_file)
        self.assertEqual(doc["schema_version"], 1)
        self.assertGreaterEqual(len(doc["assets"]), 3)
        loaded = load_index(index_file)
        self.assertEqual(len(loaded["assets"]), len(doc["assets"]))


if __name__ == "__main__":
    unittest.main()
