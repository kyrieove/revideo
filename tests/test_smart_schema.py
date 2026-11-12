import json
import unittest
import copy
from pathlib import Path

# 在实现前导入会触发 ModuleNotFoundError (RED 阶段)
try:
    from scripts.smart_schema import (
        validate_source_events,
        validate_index,
        validate_proposal,
        fingerprint_render_plan,
        validate_smart_workflow
    )
except ImportError:
    validate_source_events = None


class TestSmartSchemaRed(unittest.TestCase):
    def setUp(self):
        self.sample_events = {
            "fps_str": "30",
            "frames": 60,
            "reference": "ref.mp4",
            "shots": [
                {
                    "id": 1,
                    "start": 0,
                    "end": 30,
                    "material": "mat1.mp4",
                    "material_in": 1.0,
                    "role": "intro",
                    "scale_ref": 1.0
                },
                {
                    "id": 2,
                    "start": 30,
                    "end": 60,
                    "material": "mat2.mp4",
                    "material_in": 0.5,
                    "role": "climax",
                    "scale_ref": 1.0
                }
            ]
        }

    def test_imports_exist(self):
        self.assertIsNotNone(validate_source_events, "smart_schema module and functions must exist")

    def test_rejects_changed_reference_boundaries(self):
        tampered = copy.deepcopy(self.sample_events)
        tampered["shots"][0]["end"] = 25  # 改变了参考片时间线
        with self.assertRaises(ValueError):
            validate_source_events(tampered)

    def test_rejects_unknown_schema(self):
        doc = {
            "schema_version": 999,
            "status": "proposed"
        }
        with self.assertRaises(ValueError):
            validate_smart_workflow(doc)

    def test_does_not_mutate_source(self):
        original_json = json.dumps(self.sample_events, sort_keys=True)
        clone = copy.deepcopy(self.sample_events)
        validate_source_events(clone)
        self.assertEqual(json.dumps(clone, sort_keys=True), original_json)

    def test_fingerprint_deterministic(self):
        ev = copy.deepcopy(self.sample_events)
        fp1 = fingerprint_render_plan(ev)
        ev["smart_workflow"] = {"status": "proposed", "extra": 123}
        fp2 = fingerprint_render_plan(ev)
        # smart_workflow 字段不参与渲染计划指纹计算
        self.assertEqual(fp1, fp2)


if __name__ == "__main__":
    unittest.main()
