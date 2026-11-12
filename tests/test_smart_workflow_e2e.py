"""test_smart_workflow_e2e.py - 智能双模剪辑工作流端到端全流程集成验收测试 (M4)"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from scripts.material_index import build_index, load_index
from scripts.smart_match import propose
from scripts.smart_timeline import generate_original_timeline
from scripts.smart_compose import compose
from scripts.smart_workflow import build_proposed_plan, approve
from scripts.smart_preview import generate_preview
from scripts.smart_schema import fingerprint_render_plan


def ffprobe_meta(path: str) -> dict:
    cmd = [
        "ffprobe", "-v", "error", "-count_frames",
        "-show_streams", "-show_format", "-of", "json", path
    ]
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
    return json.loads(res.stdout)


class TestSmartWorkflowE2E(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp_dir = tempfile.mkdtemp(prefix="revideo_e2e_")
        cls.clips_dir = os.path.join(cls.tmp_dir, "clips")
        os.makedirs(cls.clips_dir, exist_ok=True)

        cls.clip_a = os.path.join(cls.clips_dir, "clip_a.mp4")
        cls.clip_b = os.path.join(cls.clips_dir, "clip_b.mp4")
        cls.ref_video = os.path.join(cls.tmp_dir, "ref.mp4")

        # 合成含动态图像与音轨的参考视频: 2.0秒 (60帧 @ 30fps)
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "testsrc=s=320x180:d=2:r=30",
            "-f", "lavfi", "-i", "sine=f=440:d=2",
            "-c:v", "libx264", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "128k",
            cls.ref_video
        ], check=True)

        # 合成两段候选素材 (各 2.5 秒)
        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=red:s=320x180:d=2.5:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.clip_a
        ], check=True)

        subprocess.run([
            "ffmpeg", "-v", "error", "-y",
            "-f", "lavfi", "-i", "color=c=green:s=320x180:d=2.5:r=30",
            "-c:v", "libx264", "-pix_fmt", "yuv420p", cls.clip_b
        ], check=True)

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp_dir, ignore_errors=True)

    def test_reference_mode_end_to_end(self):
        """测试复刻模式端到端全流程：
        索引 -> 候选建议 -> 审查决策 -> 审批门禁 -> 草稿预览 -> 正式渲染 (带音轨校验)。
        """
        # 1. 素材索引
        index_file = os.path.join(self.tmp_dir, "ref_index.json")
        index = build_index([self.clips_dir], index_file)
        self.assertGreaterEqual(len(index["assets"]), 2)

        # 2. 源参考事件表
        source_events = {
            "mode": "reference",
            "fps": 30.0,
            "fps_str": "30/1",
            "frames": 60,
            "size": [320, 180],
            "ref": self.ref_video,
            "shots": [
                {"id": 1, "start": 0, "end": 30, "material": None, "target_energy": 0.5},
                {"id": 2, "start": 30, "end": 60, "material": None, "target_energy": 0.7}
            ]
        }

        # 3. 候选推荐
        candidates = propose(source_events, index, top_k=2)
        proposed = build_proposed_plan(source_events, candidates)

        # 4. 人工确认决策
        decisions = {
            "schema_version": 1,
            "candidates_sha256": fingerprint_render_plan(candidates),
            "source_events_sha256": fingerprint_render_plan(source_events),
            "decisions": [
                {
                    "shot_id": 1,
                    "selected_candidate_id": candidates["slots"][0]["candidates"][0]["candidate_id"],
                    "confirmed": True
                },
                {
                    "shot_id": 2,
                    "selected_candidate_id": candidates["slots"][1]["candidates"][0]["candidate_id"],
                    "confirmed": True
                }
            ]
        }

        # 5. 审批门禁
        approved = approve(proposed, decisions, candidates, source_events, index)
        self.assertEqual(approved["smart_workflow"]["status"], "approved")

        approved_file = os.path.join(self.tmp_dir, "ref_events.approved.json")
        with open(approved_file, "w", encoding="utf-8") as f:
            json.dump(approved, f, indent=2, ensure_ascii=False)

        # 6. 生成可播放预览
        preview_html = os.path.join(self.tmp_dir, "ref_preview.html")
        generate_preview(approved, preview_html)
        self.assertTrue(os.path.isfile(preview_html))

        # 7. 正式渲染
        out_mp4 = os.path.join(self.tmp_dir, "ref_rendered.mp4")
        remake_script = str(Path(__file__).resolve().parent.parent / "scripts" / "remake.py")
        cmd = [sys.executable, "-X", "utf8", remake_script, approved_file, out_mp4]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Remake failed: {res.stderr}")

        # 8. ffprobe 验证产物音画指标
        meta = ffprobe_meta(out_mp4)
        video = next(s for s in meta["streams"] if s["codec_type"] == "video")
        audio = next(s for s in meta["streams"] if s["codec_type"] == "audio")

        self.assertEqual(int(video["nb_read_frames"]), 60)
        self.assertAlmostEqual(float(video["duration"]), 2.0, delta=0.05)
        self.assertIsNotNone(audio)
        self.assertAlmostEqual(float(audio["duration"]), 2.0, delta=0.05)

    def test_original_mode_end_to_end(self):
        """测试自主创作模式端到端全流程 (无参考片、无 BGM)：
        原创时间轴生成 -> 波束搜索组接 -> 审批 -> 预览 -> 无声渲染。
        """
        # 1. 索引
        index_file = os.path.join(self.tmp_dir, "orig_index.json")
        index = build_index([self.clips_dir], index_file)

        # 2. 原创时间轴生成
        timeline = generate_original_timeline(target_frames=60, fps_str="30/1")
        timeline["size"] = [320, 180]
        self.assertEqual(timeline["audio"]["mode"], "none")

        # 3. 波束搜索组接
        composed = compose(timeline, index, beam_width=4, top_k=2)
        candidates = {
            "schema_version": 1,
            "slots": [
                {
                    "shot_id": s["id"],
                    "candidates": s.get("candidates", [])
                }
                for s in composed["shots"]
            ]
        }

        # 4. 决策与审批
        decisions = {
            "schema_version": 1,
            "candidates_sha256": fingerprint_render_plan(candidates),
            "source_events_sha256": fingerprint_render_plan(composed),
            "decisions": [
                {
                    "shot_id": s["id"],
                    "selected_candidate_id": s["selection"]["candidate_id"],
                    "confirmed": True
                }
                for s in composed["shots"]
            ]
        }

        approved = approve(composed, decisions, candidates, composed, index)
        self.assertEqual(approved["smart_workflow"]["status"], "approved")

        approved_file = os.path.join(self.tmp_dir, "orig_events.approved.json")
        with open(approved_file, "w", encoding="utf-8") as f:
            json.dump(approved, f, indent=2, ensure_ascii=False)

        # 5. 正式无声渲染 (-an)
        out_mp4 = os.path.join(self.tmp_dir, "orig_rendered.mp4")
        remake_script = str(Path(__file__).resolve().parent.parent / "scripts" / "remake.py")
        cmd = [sys.executable, "-X", "utf8", remake_script, approved_file, out_mp4]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(res.returncode, 0, f"Remake original failed: {res.stderr}")

        # 6. ffprobe 验证
        meta = ffprobe_meta(out_mp4)
        video = next(s for s in meta["streams"] if s["codec_type"] == "video")
        audio = next((s for s in meta["streams"] if s["codec_type"] == "audio"), None)

        self.assertEqual(int(video["nb_read_frames"]), 60)
        self.assertIsNone(audio, "Original mode without BGM should not contain an audio stream")


if __name__ == "__main__":
    unittest.main()
