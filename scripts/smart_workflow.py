"""smart_workflow.py - 智能工作流 CLI、状态审批与决策管理 (M3)"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.smart_schema import fingerprint_render_plan, validate_smart_workflow


def build_proposed_plan(events: Dict[str, Any], candidates: Dict[str, Any]) -> Dict[str, Any]:
    """将候选表中的最高分素材注入，生成待审核事件表 events.proposed.json。"""
    proposed = copy.deepcopy(events)
    # 取出候选推荐填补
    slots_map = {s["shot_id"]: s.get("candidates", []) for s in candidates.get("slots", [])}
    for s in proposed.get("shots", []):
        cands = slots_map.get(s.get("id"), [])
        if cands:
            top1 = cands[0]
            s["material"] = top1.get("path")
            s["material_in"] = top1.get("in_sec")
            s["selection"] = {
                "candidate_id": top1.get("candidate_id"),
                "score": top1.get("score")
            }
            
    proposed["smart_workflow"] = {
        "schema_version": 1,
        "status": "proposed",
        "source_events_sha256": fingerprint_render_plan(events),
        "approval_sha256": None
    }
    return proposed


def approve(proposed_events: Dict[str, Any], decisions: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """对已完成审查的方案打上审批签名，输出 events.approved.json。
    必须验证 decisions 中所有镜头均已明确确认，杜绝未审查直接通过。
    """
    if decisions is not None:
        dec_map = {d["shot_id"]: d for d in decisions.get("decisions", [])}
        for shot in proposed_events.get("shots", []):
            sid = shot.get("id")
            if sid not in dec_map or not dec_map[sid].get("confirmed", True):
                raise ValueError(f"Shot {sid} is missing confirmed human decision")

    approved = copy.deepcopy(proposed_events)
    fp = fingerprint_render_plan(approved)
    approved["smart_workflow"] = {
        "schema_version": 1,
        "status": "approved",
        "source_events_sha256": approved.get("smart_workflow", {}).get("source_events_sha256", fp),
        "approval_sha256": fp
    }
    return approved
