"""smart_schema.py - revideo 智能工作流数据契约与防篡改验证器 (M0)"""

import copy
import hashlib
import json
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
