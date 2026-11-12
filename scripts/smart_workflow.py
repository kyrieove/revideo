"""smart_workflow.py - 智能工作流 CLI、状态审批与决策管理 (M3)"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.smart_schema import (
    fingerprint_render_plan,
    validate_smart_workflow,
    validate_decisions,
    validate_source_events,
)


def build_proposed_plan(events: Dict[str, Any], candidates: Dict[str, Any]) -> Dict[str, Any]:
    """将候选表中的最高分素材注入，生成待审核事件表 events.proposed.json。"""
    proposed = copy.deepcopy(events)
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


def approve(
    proposed_events: Dict[str, Any],
    decisions: Dict[str, Any],
    candidates: Dict[str, Any],
    source_events: Dict[str, Any],
    index: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """对已完成审查的方案打上审批签名，输出 events.approved.json。
    必须传入 decisions、candidates、source_events，逐镜核对决策有效性，杜绝未经人工审核放行。
    """
    if decisions is None:
        raise ValueError("SMART_WORKFLOW_DECISIONS_REQUIRED: decisions cannot be None")
    if candidates is None:
        raise ValueError("SMART_WORKFLOW_CANDIDATES_REQUIRED: candidates cannot be None")
    if source_events is None:
        raise ValueError("SMART_WORKFLOW_SOURCE_EVENTS_REQUIRED: source_events cannot be None")

    # 复刻模式下，严格核对源事件表与批准方案的切点与帧参数，禁止切点漂移
    sw = proposed_events.get("smart_workflow") or {}
    mode = sw.get("mode") or proposed_events.get("mode", "reference")
    if mode == "reference":
        for attr in ("fps", "fps_str", "frames"):
            if proposed_events.get(attr) != source_events.get(attr):
                raise ValueError(f"SMART_WORKFLOW_REFERENCE_TIMELINE_ALTERED: {attr} changed")
        
        p_shots = proposed_events.get("shots", [])
        s_shots = source_events.get("shots", [])
        if len(p_shots) != len(s_shots):
            raise ValueError("SMART_WORKFLOW_REFERENCE_TIMELINE_ALTERED: shot count mismatch")
        for ps, ss in zip(p_shots, s_shots):
            if ps.get("id") != ss.get("id") or ps.get("start") != ss.get("start") or ps.get("end") != ss.get("end"):
                raise ValueError(f"SMART_WORKFLOW_REFERENCE_TIMELINE_ALTERED: shot boundary changed for shot {ps.get('id')}")

    # 严格校验人工决策契约
    validate_decisions(decisions, candidates, source_events, index)

    # 校验每个镜头的实际素材与决策一致
    dec_map = {d["shot_id"]: d for d in decisions.get("decisions", [])}
    slot_cands_map = {
        s["shot_id"]: {c["candidate_id"]: c for c in s.get("candidates", [])}
        for s in candidates.get("slots", [])
    }

    approved = copy.deepcopy(proposed_events)
    for shot in approved.get("shots", []):
        sid = shot.get("id")
        dec = dec_map[sid]
        chosen_cand_id = dec["selected_candidate_id"]
        cand_meta = slot_cands_map[sid][chosen_cand_id]

        # 确保镜头素材路径与入点已应用所选决策
        shot["material"] = cand_meta.get("path")
        shot["material_in"] = cand_meta.get("in_sec")
        shot["selection"] = {
            "candidate_id": chosen_cand_id,
            "score": cand_meta.get("score"),
            "confirmed": True
        }

    fp = fingerprint_render_plan(approved)
    src_fp = fingerprint_render_plan(source_events)
    approved["smart_workflow"] = {
        "schema_version": 1,
        "status": "approved",
        "source_events_sha256": src_fp,
        "approval_sha256": fp
    }
    return approved
