"""B244621 regression: semantic admissibility, localized windows and render audit."""
import math
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import json

from scripts.gap_analyzer import (
    MaterialDeficitError,
    analyze_material_gaps,
    evaluate_asset_against_contract,
    evaluate_contract_match,
    generate_capture_task_sheet,
)
from scripts.shot_contract import ShotContract, validate_contracts
from scripts.smart_match import enumerate_windows, propose
from scripts.smart_compose import compose
from scripts.smart_schema import fingerprint_render_plan
from scripts.smart_workflow import build_proposed_plan, approve
from scripts.material_index import build_index
from scripts.remake import validate_timeline


def contract():
    return ShotContract(
        id=1, start_frame=0, end_frame=30, duration_frames=30,
        duration_seconds=1.0, beat_peak_frame=0, subject="player_character",
        action="sheathing_sword", camera_motion="pan_right",
        scene_type="snow_mountain",
    )


def verified_asset():
    return {
        "asset_id": "verified",
        "path": "/media/verified.mp4",
        "valid": True,
        "duration_seconds": 60.0,
        "features": {
            "motion_intensity": 0.2,
            "motion_direction": "left_to_right",
            "brightness": 0.5,
        },
        "semantic_segments": [{
            "start": 40.0, "end": 43.0,
            "confidence": 1.0, "source": "manual",
            "features": {
                "subject": "player_character",
                "action": "sheathing_sword",
                "camera_motion": "pan_right",
                "dominant_scene": "snow_mountain",
            }
        }],
    }


class ContractSafetyRegression(unittest.TestCase):
    def test_wrong_action_cannot_be_offset_by_other_scores(self):
        asset = {
            "valid": True, "duration_seconds": 10.0,
            "features": {
                "subject": "player_character", "action": "running",
                "camera_motion": "pan_right",
                "dominant_scene": "snow_mountain",
            },
        }
        self.assertLess(evaluate_asset_against_contract(asset, contract()), 0.60)
        self.assertEqual(evaluate_contract_match(asset, contract())["status"], "GAP")

    def test_missing_semantics_is_review_not_pass_or_definite_gap(self):
        asset = {"valid": True, "duration_seconds": 10, "features": {"motion_intensity": 0.5}}
        assessment = evaluate_contract_match(asset, contract())
        self.assertEqual(assessment["status"], "REVIEW_REQUIRED")
        report = analyze_material_gaps([contract()], {"assets": [asset]})
        self.assertEqual(report["status"], "REVIEW_REQUIRED")
        self.assertEqual(report["review_count"], 1)
        self.assertEqual(report["gap_count"], 0)

    def test_empty_library_blocks_and_sheet_is_generated(self):
        report = analyze_material_gaps([contract()], {"assets": []})
        self.assertEqual(report["status"], "BLOCKED")
        self.assertEqual(report["gap_count"], 1)
        with tempfile.TemporaryDirectory() as directory:
            dest = Path(directory) / "reports" / "capture_task_sheet.md"
            generate_capture_task_sheet(report, dest)
            self.assertTrue(dest.exists())
            result = dest.read_text(encoding="utf-8")
            self.assertIn("建议录制", result)
            self.assertIn("第 0 帧", result)
            self.assertIn("sheathing_sword", result)

    def test_invalid_threshold_and_empty_contracts_fail_closed(self):
        with self.assertRaises(ValueError):
            analyze_material_gaps([contract()], {"assets": []}, threshold=float("nan"))
        with self.assertRaises(ValueError):
            analyze_material_gaps([], {"assets": []})
        with self.assertRaises(ValueError):
            validate_contracts([ShotContract(
                id=1, start_frame=0, end_frame=30, duration_frames=29,
                duration_seconds=1.0
            )])

    def test_full_duration_window_search_finds_late_action(self):
        asset = verified_asset()
        windows = enumerate_windows(asset, 1.0)
        evidence_windows = [
            w for w in windows
            if 40 <= w["in_sec"] <= 42
            and w.get("semantic_evidence")
            and evaluate_contract_match(
                w, contract(), require_window_evidence=True
            )["status"] == "PASS"
        ]
        self.assertTrue(evidence_windows, "A late semantic event must be discoverable")
        report = analyze_material_gaps([contract()], {"assets": [asset]})
        self.assertEqual(report["status"], "PASSED")

    def test_compose_only_selects_compliant_window(self):
        bad = {
            "asset_id": "bad", "path": "/media/bad.mp4", "valid": True,
            "duration_seconds": 60.0,
            "features": {
                "motion_intensity": 0.9, "subject": "player_character",
                "action": "running", "camera_motion": "pan_right",
                "dominant_scene": "snow_mountain",
            },
        }
        source = {
            "fps": 30.0, "fps_str": "30/1", "frames": 30,
            "shots": [{"id": 1, "start": 0, "end": 30, "target_energy": 0.9}],
            "contracts": [contract().to_dict()],
        }
        result = compose(source, {"assets": [bad, verified_asset()]})
        self.assertEqual(result["shots"][0]["material"], verified_asset()["path"])
        self.assertGreaterEqual(result["shots"][0]["material_in"], 40)
        self.assertEqual(result["shots"][0]["selection"]["contract_status"], "PASS")
        self.assertEqual(result["contract_audit"]["status"], "PASSED")

    def test_explicit_empty_contract_is_not_bypass(self):
        source = {
            "fps": 30, "shots": [{"id": 1, "start": 0, "end": 30}],
            "contracts": [],
        }
        with self.assertRaises(MaterialDeficitError):
            compose(source, {"assets": []})

    def test_infeasible_beam_raises_instead_of_partial_output(self):
        source = {
            "fps": 30.0,
            "shots": [
                {"id": 1, "start": 0, "end": 30},
                {"id": 2, "start": 30, "end": 60},
            ],
        }
        asset = {
            "asset_id": "single", "path": "/media/single.mp4",
            "valid": True, "duration_seconds": 2.0,
            "features": {"motion_intensity": 0.5},
        }
        with self.assertRaisesRegex(MaterialDeficitError, "NO_FEASIBLE_COMPOSITION"):
            compose(source, {"assets": [asset]})

    def test_render_requires_per_shot_audit_with_contracts(self):
        ev = {
            "fps": 30.0, "fps_str": "30/1", "frames": 30,
            "shots": [{
                "id": 1, "start": 0, "end": 30,
                "material": "/media/verified.mp4", "material_in": 40.0,
            }],
            "contracts": [contract().to_dict()],
        }
        ev["smart_workflow"] = {
            "schema_version": 1, "status": "approved",
            "approval_sha256": fingerprint_render_plan(ev),
        }
        with self.assertRaisesRegex(ValueError, "CONTRACT_AUDIT_MISSING"):
            validate_timeline(ev)


    def test_approved_composition_rechecks_contract_and_renders(self):
        asset = verified_asset()
        c = contract()
        source = {
            "fps": 30.0, "fps_str": "30/1", "frames": 30,
            "shots": [{"id": 1, "start": 0, "end": 30}],
            "contracts": [c.to_dict()],
        }
        index = {"assets": [asset]}
        result = compose(source, index)
        selected = result["shots"][0]
        meta = {
            "candidate_id": selected["selection"]["candidate_id"],
            "path": selected["material"],
            "in_sec": selected["material_in"],
        }
        candidates = {
            "schema_version": 1,
            "slots": [{"shot_id": 1, "candidates": [meta]}],
        }
        decisions = {
            "schema_version": 1,
            "source_events_sha256": fingerprint_render_plan(source),
            "candidates_sha256": fingerprint_render_plan(candidates),
            "decisions": [{
                "shot_id": 1, "confirmed": True,
                "selected_candidate_id": meta["candidate_id"],
            }],
        }
        proposed = build_proposed_plan(source, candidates)
        approved = approve(proposed, decisions, candidates, source, index=index)
        self.assertEqual(approved["contract_audit"]["status"], "PASSED")
        validate_timeline(approved)
        approved["shots"][0]["material_in"] += 0.5
        approved["smart_workflow"]["approval_sha256"] = fingerprint_render_plan(approved)
        with self.assertRaisesRegex(ValueError, "CONTRACT_AUDIT_MISMATCH"):
            validate_timeline(approved)

    def test_reindex_preserves_semantics_only_when_fingerprint_unchanged(self):
        fake_path = "/media/gameplay.mp4"
        info = {
            "valid": True, "duration_seconds": 60.0,
            "fps_str": "30/1", "codec": "h264",
        }
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "index.json"
            previous = {
                "schema_version": 1,
                "assets": [{
                    "path": fake_path, "source_fingerprint": "version-a",
                    "valid": True, "semantic_verified": True,
                    "semantic_scope": "full_asset",
                    "semantic_segments": [{"start": 40, "end": 43, "features": {"action": "sheathing_sword"}}],
                    "features": {"subject": "player_character", "action": "sheathing_sword"},
                }],
            }
            output.write_text(json.dumps(previous), encoding="utf-8")
            with patch("scripts.material_index.discover_assets", return_value=[fake_path]), \
                 patch("scripts.material_index.probe_asset", return_value=info), \
                 patch("scripts.material_index.sample_asset", return_value=[]), \
                 patch("scripts.material_index.compute_source_fingerprint", return_value="version-a"):
                same = build_index(["/media"], str(output))
            self.assertTrue(same["assets"][0]["semantic_verified"])
            self.assertEqual(same["assets"][0]["features"]["action"], "sheathing_sword")
            with patch("scripts.material_index.discover_assets", return_value=[fake_path]), \
                 patch("scripts.material_index.probe_asset", return_value=info), \
                 patch("scripts.material_index.sample_asset", return_value=[]), \
                 patch("scripts.material_index.compute_source_fingerprint", return_value="version-b"):
                changed = build_index(["/media"], str(output))
            self.assertFalse(changed["assets"][0]["semantic_verified"])
            self.assertNotIn("action", changed["assets"][0]["features"])


    def test_unverified_full_asset_semantics_requires_review(self):
        c = contract()
        raw = {
            "asset_id": "unverified", "valid": True, "duration_seconds": 12.0,
            "features": {
                "subject": c.subject, "action": c.action,
                "camera_motion": c.camera_motion, "dominant_scene": c.scene_type,
            },
        }
        result = analyze_material_gaps([c], {"assets": [raw]})
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["gap_count"], 0)
        self.assertEqual(result["review_count"], 1)
        for window in enumerate_windows(raw, 1.0):
            self.assertNotEqual(
                evaluate_contract_match(
                    window, c, require_window_evidence=True
                )["status"], "PASS",
            )

    def test_partial_semantic_segment_cannot_inherit_unverified_global_labels(self):
        c = contract()
        raw = {
            "asset_id": "partial", "valid": True, "duration_seconds": 10.0,
            "features": {
                "subject": c.subject, "action": c.action,
                "camera_motion": c.camera_motion,
                "dominant_scene": c.scene_type,
            },
            "semantic_segments": [{
                "start": 3.0, "end": 6.0,
                "features": {"action": c.action}
            }],
        }
        result = analyze_material_gaps([c], {"assets": [raw]})
        self.assertEqual(result["status"], "REVIEW_REQUIRED")
        self.assertEqual(result["matched_count"], 0)
        for window in enumerate_windows(raw, 1.0):
            self.assertNotEqual(
                evaluate_contract_match(window, c, require_window_evidence=True)["status"],
                "PASS",
            )

    def test_contract_aware_propose_filters_wrong_action(self):
        source = {
            "fps": 30.0, "fps_str": "30/1", "frames": 30,
            "shots": [{"id": 1, "start": 0, "end": 30, "target_energy": 0.9}],
            "contracts": [contract().to_dict()],
        }
        bad = {
            "asset_id": "bad", "path": "/media/bad.mp4", "valid": True,
            "duration_seconds": 60.0,
            "features": {"motion_intensity": 0.95},
            "semantic_scope": "full_asset", "semantic_verified": True,
            "semantic_segments": [],
        }
        bad["features"].update({
            "subject": "player_character", "action": "running",
            "camera_motion": "pan_right", "dominant_scene": "snow_mountain",
        })
        plan = propose(source, {"assets": [bad, verified_asset()]}, top_k=2)
        self.assertEqual(len(plan["slots"]), 1)
        self.assertTrue(plan["slots"][0]["candidates"])
        self.assertTrue(all(
            w["path"] == "/media/verified.mp4"
            for w in plan["slots"][0]["candidates"]
        ))

    def test_constraints_contracts_survive_compose_for_audit(self):
        source = {
            "fps": 30.0, "fps_str": "30/1", "frames": 30,
            "shots": [{"id": 1, "start": 0, "end": 30}],
        }
        result = compose(
            source, {"assets": [verified_asset()]},
            constraints={"contracts": [contract().to_dict()]},
        )
        self.assertIn("contracts", result)
        self.assertEqual(len(result["contracts"]), 1)
        self.assertEqual(result["contract_audit"]["status"], "PASSED")

    def test_contract_required_cannot_be_stripped_from_render(self):
        ev = {
            "fps": 30.0, "fps_str": "30/1", "frames": 30,
            "contract_required": True,
            "shots": [{
                "id": 1, "start": 0, "end": 30,
                "material": "/media/verified.mp4", "material_in": 40.0,
            }],
        }
        ev["smart_workflow"] = {
            "schema_version": 1, "status": "approved",
            "approval_sha256": fingerprint_render_plan(ev),
        }
        with self.assertRaisesRegex(ValueError, "CONTRACTS_REQUIRED"):
            validate_timeline(ev)


if __name__ == "__main__":
    unittest.main()
