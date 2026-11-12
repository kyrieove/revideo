"""test_shot_contract.py - 镜头叙事契约、缺口扫描阻断与补录单生成单测"""

import tempfile
import unittest
from pathlib import Path
from scripts.gap_analyzer import MaterialDeficitError, analyze_material_gaps, generate_capture_task_sheet
from scripts.shot_contract import ShotContract, load_contracts, save_contracts, validate_contracts
from scripts.smart_compose import compose


class TestShotContractArchitecture(unittest.TestCase):
    def setUp(self):
        self.contracts = [
            ShotContract(
                id=1,
                start_frame=0,
                end_frame=30,
                duration_frames=30,
                duration_seconds=1.0,
                subject="player_character",
                action="sheathing_sword",
                camera_motion="pan_right",
                scene_type="snow_mountain"
            ),
            ShotContract(
                id=2,
                start_frame=30,
                end_frame=60,
                duration_frames=30,
                duration_seconds=1.0,
                subject="player_character",
                action="pose_drinking",
                camera_motion="pan_right",
                scene_type="sea_cloud"
            )
        ]

    def test_contract_validation_and_io(self):
        self.assertTrue(validate_contracts(self.contracts))

        # 测试时间不连续异常
        bad_contracts = [
            ShotContract(id=1, start_frame=0, end_frame=30, duration_frames=30, duration_seconds=1.0),
            ShotContract(id=2, start_frame=40, end_frame=60, duration_frames=20, duration_seconds=0.667)
        ]
        with self.assertRaises(ValueError):
            validate_contracts(bad_contracts)

        with tempfile.TemporaryDirectory() as tmp_dir:
            fpath = Path(tmp_dir) / "contracts.json"
            save_contracts(self.contracts, fpath)
            loaded = load_contracts(fpath)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0].action, "sheathing_sword")
            self.assertEqual(loaded[1].action, "pose_drinking")

    def test_gap_analyzer_blocks_and_generates_task_sheet(self):
        # 仅提供不匹配的纯风景/切菜素材 (缺人物核心动作)
        index = {
            "assets": [
                {
                    "asset_id": "raw_scenery",
                    "path": "/media/scenery.mp4",
                    "valid": True,
                    "duration_seconds": 10.0,
                    "features": {
                        "subject": "scenery_empty",
                        "action": "none",
                        "dominant_scene": "snow_mountain",
                        "scene_tags": ["snow_mountain"]
                    }
                }
            ]
        }

        res = analyze_material_gaps(self.contracts, index, threshold=0.60)
        self.assertEqual(res["status"], "BLOCKED")
        self.assertEqual(res["gap_count"], 2)

        with tempfile.TemporaryDirectory() as tmp_dir:
            sheet_file = Path(tmp_dir) / "capture_task_sheet.md"
            generate_capture_task_sheet(res, sheet_file)
            self.assertTrue(sheet_file.is_file())
            content = sheet_file.read_text(encoding="utf-8")
            self.assertIn("《游戏内补录需求任务单》", content)
            self.assertIn("sheathing_sword", content)
            self.assertIn("pose_drinking", content)

    def test_smart_compose_refuses_forced_cut_without_authorization(self):
        index = {
            "assets": [
                {
                    "asset_id": "raw_scenery",
                    "path": "/media/scenery.mp4",
                    "valid": True,
                    "duration_seconds": 10.0,
                    "features": {
                        "subject": "scenery_empty",
                        "action": "none",
                        "dominant_scene": "snow_mountain",
                        "scene_tags": ["snow_mountain"]
                    }
                }
            ]
        }
        timeline = {
            "fps": 30.0,
            "shots": [
                {"id": 1, "start": 0, "end": 30},
                {"id": 2, "start": 30, "end": 60}
            ],
            "contracts": self.contracts
        }

        # 1. 默认情况下 (allow_forced_fill=False)：硬性阻断并抛出异常
        with self.assertRaises(MaterialDeficitError):
            compose(timeline, index, allow_forced_fill=False)

        # 2. 只有在用户显式授权 allow_forced_fill=True 时才允许强行降级组接
        composed = compose(timeline, index, allow_forced_fill=True)
        self.assertEqual(len(composed["shots"]), 2)


if __name__ == "__main__":
    unittest.main()
