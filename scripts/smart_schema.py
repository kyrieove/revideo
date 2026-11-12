"""smart_schema.py - revideo 智能工作流数据契约与防篡改验证器 (M0)"""

import copy
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


CURRENT_SCHEMA_VERSION = 1


def fingerprint_render_plan(doc: Dict[str, Any]) -> str:
    """计算渲染计划的标准 SHA-256 指纹。
    剔除 smart_workflow 自身元数据，对渲染关键参数进行确定性规范序列化。
    """
    clean_doc = copy.deepcopy(doc)
    if "smart_workflow" in clean_doc:
        del clean_doc["smart_workflow"]
    
    canonical_bytes = json.dumps(
        clean_doc,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False
    ).encode("utf-8")
    
    return hashlib.sha256(canonical_bytes).hexdigest()


def validate_smart_workflow(sw: Dict[str, Any]) -> None:
    """验证 smart_workflow 对象契约及版本。"""
    if not isinstance(sw, dict):
        raise ValueError("smart_workflow must be a dictionary")
    
    ver = sw.get("schema_version")
    if ver != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported schema_version: {ver}, expected: {CURRENT_SCHEMA_VERSION}")
    
    status = sw.get("status")
    allowed_statuses = {"proposed", "in_review", "approved"}
    if status not in allowed_statuses:
        raise ValueError(f"Invalid smart_workflow status: {status}, must be one of {allowed_statuses}")


def validate_source_events(events: Dict[str, Any]) -> None:
    """验证源事件表结构与参考切点合法性。原事件表不可原地突变。"""
    if not isinstance(events, dict):
        raise ValueError("Events must be a dictionary")
    
    if "shots" not in events or not isinstance(events["shots"], list):
        raise ValueError("Events must contain a 'shots' list")
    
    shots = events["shots"]
    if not shots:
        raise ValueError("'shots' cannot be empty")
    
    expected_start = 0
    total_frames = events.get("frames")
    
    for idx, shot in enumerate(shots):
        if not isinstance(shot, dict):
            raise ValueError(f"Shot at index {idx} must be a dictionary")
        
        start = shot.get("start")
        end = shot.get("end")
        
        if start is None or end is None:
            raise ValueError(f"Shot {idx} must define 'start' and 'end'")
        
        if start < 0 or end <= start:
            raise ValueError(f"Shot {idx} has invalid boundaries: start={start}, end={end}")
        
        # 必须连续无缝且不得篡改
        if start != expected_start:
            raise ValueError(
                f"Shot {idx} boundary mismatch: expected start {expected_start}, got {start}"
            )
        expected_start = end
        
    if total_frames is not None and expected_start != total_frames:
        raise ValueError(f"Total shots boundary ({expected_start}) does not match declared frames ({total_frames})")
    
    if "smart_workflow" in events:
        validate_smart_workflow(events["smart_workflow"])


def validate_index(index_doc: Dict[str, Any]) -> None:
    """验证素材特征索引 index.json 契约。"""
    if not isinstance(index_doc, dict):
        raise ValueError("Index document must be a dictionary")
    if index_doc.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Invalid index schema_version: {index_doc.get('schema_version')}")
    if "assets" not in index_doc:
        raise ValueError("Index document must contain 'assets'")


def validate_proposal(proposal_doc: Dict[str, Any]) -> None:
    """验证候选方案 proposal / candidates 契约。"""
    if not isinstance(proposal_doc, dict):
        raise ValueError("Proposal document must be a dictionary")
    if proposal_doc.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Invalid proposal schema_version: {proposal_doc.get('schema_version')}")
    if "slots" not in proposal_doc:
        raise ValueError("Proposal document must contain 'slots'")


def validate_decisions(
    decisions: Dict[str, Any],
    candidates: Dict[str, Any],
    source_events: Dict[str, Any],
    index: Optional[Dict[str, Any]] = None
) -> None:
    """严格验证人工审核决策 decisions.json。
    确保每个镜头均被显式 confirmed=True 确认，强制要求关联摘要并校验素材真实指纹。
    """
    if not isinstance(decisions, dict):
        raise ValueError("Decisions must be a dictionary")
    if decisions.get("schema_version") != CURRENT_SCHEMA_VERSION:
        raise ValueError(f"Unsupported decisions schema_version: {decisions.get('schema_version')}")

    # 强制校验关联摘要，不得省略
    if "candidates_sha256" not in decisions:
        raise ValueError("Decisions missing mandatory candidates_sha256")
    expected_cand_sha = fingerprint_render_plan(candidates)
    if decisions["candidates_sha256"] != expected_cand_sha:
        raise ValueError("Decisions candidates_sha256 mismatch with candidates document")

    if "source_events_sha256" not in decisions:
        raise ValueError("Decisions missing mandatory source_events_sha256")
    expected_src_sha = fingerprint_render_plan(source_events)
    if decisions["source_events_sha256"] != expected_src_sha:
        raise ValueError("Decisions source_events_sha256 mismatch with source_events document")

    shots = source_events.get("shots", [])
    shot_ids = {s["id"] for s in shots}
    dec_list = decisions.get("decisions", [])
    
    seen_shots = set()
    slot_cands_map = {
        s["shot_id"]: {c["candidate_id"]: c for c in s.get("candidates", [])}
        for s in candidates.get("slots", [])
    }

    # 索引素材哈希映射
    asset_fp_map = {}
    if index and "assets" in index:
        for a in index["assets"]:
            asset_fp_map[a.get("path")] = a.get("source_fingerprint")

    for d in dec_list:
        sid = d.get("shot_id")
        if sid is None:
            raise ValueError("Decision entry missing shot_id")
        if sid in seen_shots:
            raise ValueError(f"Duplicate decision for shot_id {sid}")
        seen_shots.add(sid)

        # 必须显式为 True，不能为 None、False 或省略
        if d.get("confirmed") is not True:
            raise ValueError(f"Decision for shot {sid} is not explicitly confirmed (confirmed must be True)")

        cand_id = d.get("selected_candidate_id")
        if not cand_id:
            raise ValueError(f"Decision for shot {sid} missing selected_candidate_id")

        shot_cands = slot_cands_map.get(sid, {})
        if cand_id not in shot_cands:
            raise ValueError(f"Selected candidate {cand_id} does not exist in candidates for shot {sid}")

        # 检查素材指纹与真实磁盘文件
        chosen_cand = shot_cands[cand_id]
        cand_path = chosen_cand.get("path")
        cand_fp = chosen_cand.get("source_fingerprint")
        
        # 1. 检查候选指纹与索引一致性
        if cand_path in asset_fp_map and cand_fp:
            if asset_fp_map[cand_path] != cand_fp:
                raise ValueError(f"Source asset {cand_path} fingerprint mismatch with index")
                
        # 2. 若物理文件存在，计算当前实际指纹严格比对
        if cand_path and Path(cand_path).exists():
            from scripts.material_index import compute_source_fingerprint
            real_fp = compute_source_fingerprint(cand_path)
            if cand_fp and real_fp and real_fp != cand_fp:
                raise ValueError(f"Source asset {cand_path} was modified on disk after indexing")

    if seen_shots != shot_ids:
        missing = shot_ids - seen_shots
        raise ValueError(f"Decisions missing confirmation for shots: {sorted(list(missing))}")
