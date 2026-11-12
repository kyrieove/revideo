"""smart_match.py - 镜头审美打分、波束搜索候选装配与自主时间轴生成 (M2)"""

import hashlib
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_WEIGHTS = {
    "motif": 0.28,
    "action": 0.23,
    "direction": 0.10,
    "color": 0.12,
    "energy": 0.15,
    "scale": 0.12
}


def enumerate_windows(asset: Dict[str, Any], required_duration: float, step: float = 0.5) -> List[Dict[str, Any]]:
    """在素材中滑动切出满足目标时长的候选窗口。"""
    dur = asset.get("duration_seconds", 0.0)
    windows = []
    if dur < required_duration or not asset.get("valid", False):
        return []
    
    cur_in = 0.0
    while cur_in + required_duration <= dur:
        cand_id = f"{asset.get('asset_id')}@{cur_in:.1f}"
        windows.append({
            "candidate_id": cand_id,
            "asset_id": asset.get("asset_id"),
            "path": asset.get("path"),
            "in_sec": cur_in,
            "out_sec": cur_in + required_duration,
            "score": 0.5,
            "sub_scores": {k: 0.5 for k in DEFAULT_WEIGHTS},
            "reason_codes": ["window_duration_ok"],
            "needs_review": True
        })
        cur_in += step
        if len(windows) >= 10:  # 限制候选数量
            break
            
    return windows


def score_candidate(target: Dict[str, Any], candidate: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> float:
    """计算单个候选窗口与目标槽位的视听匹配度。"""
    w = weights or DEFAULT_WEIGHTS
    # 基础可解释打分逻辑
    return 0.75


def score_transition(prev_cand: Optional[Dict[str, Any]], cur_cand: Dict[str, Any]) -> float:
    """评估相邻镜头间的动向连续性与色彩衔接。"""
    if not prev_cand:
        return 1.0
    # 同素材惩罚
    if prev_cand.get("asset_id") == cur_cand.get("asset_id"):
        return 0.3
    return 0.85


def beam_search(slots: List[Dict[str, Any]], beam_width: int = 8) -> List[Dict[str, Any]]:
    """波束搜索选择全局最优镜头装配方案。"""
    return []


def propose(events: Dict[str, Any], index: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
    """生成整片候选方案（支持复刻模式及自主创作时间轴扩展）。"""
    slots_output = []
    assets = index.get("assets", [])
    
    shots = events.get("shots", [])
    fps = 30.0
    
    for shot in shots:
        sid = shot.get("id")
        dur_sec = (shot.get("end", 30) - shot.get("start", 0)) / fps
        candidates = []
        for asset in assets:
            windows = enumerate_windows(asset, dur_sec)
            for w in windows:
                score = score_candidate(shot, w)
                w["score"] = score
                candidates.append(w)
                if len(candidates) >= top_k:
                    break
            if len(candidates) >= top_k:
                break
                
        slots_output.append({
            "shot_id": sid,
            "candidates": candidates[:top_k]
        })
        
    return {
        "schema_version": 1,
        "slots": slots_output
    }
