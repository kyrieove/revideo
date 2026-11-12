"""smart_workflow.py - 智能工作流 CLI、状态审批与决策管理 (M3)"""

import copy
import json
from pathlib import Path
from typing import Any, Dict, Optional

from scripts.shot_contract import ShotContract, validate_contracts
from scripts.gap_analyzer import MaterialDeficitError, evaluate_contract_match
from scripts.smart_match import enumerate_windows

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
    # 显式指定但为空的契约属于无效智能计划，不得被当作旧手工计划。
    if (
        ("contracts" in proposed_events and not proposed_events["contracts"])
        or ("contracts" in source_events and not source_events["contracts"])
    ):
        raise MaterialDeficitError("CONTRACTS_REQUIRED: 审批计划包含空契约")
    if (proposed_events.get("contract_required") or source_events.get("contract_required")) and not (
        proposed_events.get("contracts") or source_events.get("contracts")
    ):
        raise MaterialDeficitError("CONTRACTS_REQUIRED: 智能审批缺少镜头契约")
    raw_contracts = proposed_events.get("contracts") or source_events.get("contracts")
    contracts_by_id = {}
    if raw_contracts:
        parsed = [
            c if isinstance(c, ShotContract) else ShotContract.from_dict(c)
            for c in raw_contracts
        ]
        from fractions import Fraction
        fps = float(Fraction(str(proposed_events.get("fps_str") or proposed_events.get("fps") or 30)))
        validate_contracts(parsed, fps=fps, shots=approved["shots"])
        contracts_by_id = {c.id: c for c in parsed}
        if index is None or not isinstance(index.get("assets"), list):
            raise MaterialDeficitError("CONTRACT_INDEX_REQUIRED: 审批含镜头契约的方案必须提供最新素材索引")
        asset_by_path = {
            asset.get("path"): asset
            for asset in index["assets"]
            if isinstance(asset, dict) and asset.get("valid") is True
        }
    contract_audit = []
    for shot in approved.get("shots", []):
        sid = shot.get("id")
        dec = dec_map[sid]
        chosen_cand_id = dec["selected_candidate_id"]
        cand_meta = slot_cands_map[sid][chosen_cand_id]

        # 审批时重新按素材索引计算窗口准入，不信任候选表里的旧分数。
        if contracts_by_id:
            c = contracts_by_id[sid]
            asset = asset_by_path.get(cand_meta.get("path"))
            if asset is None:
                raise MaterialDeficitError(f"CONTRACT_ASSET_MISSING: 镜头 #{sid} 选中素材不在有效索引内")
            duration = c.duration_seconds
            windows = enumerate_windows(asset, duration)
            selected = next(
                (w for w in windows
                 if abs(w.get("in_sec", -999) - float(cand_meta.get("in_sec", -999))) < 0.002),
                None
            )
            if selected is None:
                raise MaterialDeficitError(f"CONTRACT_WINDOW_MISSING: 镜头 #{sid} 的候选时间窗口不存在")
            assessment = evaluate_contract_match(
                selected, c, require_window_evidence=True
            )
            override = dec_map[sid].get("force_contract_override") is True
            reason = str(dec_map[sid].get("override_reason") or "").strip()
            if assessment["status"] != "PASS" and not (override and reason):
                raise MaterialDeficitError(
                    f"CONTRACT_NOT_VERIFIED: 镜头 #{sid} 状态 {assessment['status']}；"
                    "若要人工强剪，需在该镜头 decisions 中写 force_contract_override=true 和 override_reason"
                )
            contract_audit.append({
                "shot_id": sid,
                "path": selected.get("path"),
                "in_sec": selected.get("in_sec"),
                "status": "FORCED" if override and assessment["status"] != "PASS" else "PASS",
                "reason": reason if override else assessment["reason"],
            })
        # 确保镜头素材路径与入点已应用所选决策
        shot["material"] = cand_meta.get("path")
        shot["material_in"] = cand_meta.get("in_sec")
        shot["selection"] = {
            "candidate_id": chosen_cand_id,
            "score": cand_meta.get("score"),
            "confirmed": True
        }

    if contracts_by_id:
        approved["contracts"] = [contracts_by_id[s["id"]].to_dict() for s in approved["shots"]]
        approved["contract_audit"] = {
            "status": "FORCED" if any(x["status"] == "FORCED" for x in contract_audit) else "PASSED",
            "shots": contract_audit,
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
