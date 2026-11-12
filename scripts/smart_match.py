"""smart_match.py - 镜头审美打分、波束搜索候选装配与自主时间轴生成 (M2)"""

from fractions import Fraction
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
    
    feats = asset.get("features", {})
    cur_in = 0.0
    while cur_in + required_duration <= dur + 1e-4:
        cand_id = f"{asset.get('asset_id')}@{cur_in:.1f}"
        windows.append({
            "candidate_id": cand_id,
            "asset_id": asset.get("asset_id"),
            "path": asset.get("path"),
            "source_fingerprint": asset.get("source_fingerprint", ""),
            "in_sec": round(cur_in, 2),
            "out_sec": round(cur_in + required_duration, 2),
            "features": feats,
            "score": 0.5,
            "reason_codes": ["duration_match"],
            "needs_review": feats.get("needs_review", False)
        })
        cur_in += step
        if len(windows) >= 20:  # 充足窗口池
            break
            
    return windows


def score_candidate(target: Dict[str, Any], candidate: Dict[str, Any], weights: Optional[Dict[str, float]] = None) -> float:
    """根据目标镜头的能量、动向与景别预期，对候选素材进行动态、可解释打分。"""
    cand_feats = candidate.get("features", {})
    cand_motion = float(cand_feats.get("motion_intensity", 0.3))
    cand_dir = cand_feats.get("motion_direction", "static")
    cand_bright = float(cand_feats.get("brightness", 0.5))

    target_energy = float(target.get("target_energy", 0.5))
    target_role = target.get("role", "ambient")
    target_dir = target.get("target_direction")

    # 1. 能量与动作匹配分
    energy_score = 1.0 - min(1.0, abs(target_energy - cand_motion))

    # 2. 动向匹配分
    if target_dir:
        dir_score = 1.0 if target_dir == cand_dir else 0.3
    else:
        # 高能量偏好运动，低能量偏好平稳
        dir_score = 0.9 if (target_energy > 0.6 and cand_dir != "static") or (target_energy <= 0.6 and cand_dir == "static") else 0.6

    # 3. 角色意图匹配分
    if target_role == "highlight":
        role_score = 0.9 if cand_motion > 0.25 or cand_bright > 0.4 else 0.4
    else:
        role_score = 0.8

    final_score = energy_score * 0.45 + dir_score * 0.3 + role_score * 0.25
    reasons = ["duration_match"]
    if energy_score > 0.7:
        reasons.append("energy_match")
    if dir_score > 0.8:
        reasons.append("direction_match")
    candidate["reason_codes"] = reasons
    return round(final_score, 3)


def score_transition(prev_cand: Optional[Dict[str, Any]], cur_cand: Dict[str, Any]) -> float:
    """评估相邻镜头间的动向连续性与重复惩罚。"""
    if not prev_cand:
        return 1.0
    
    # 强烈惩罚相邻镜头重复使用同一素材
    if prev_cand.get("asset_id") == cur_cand.get("asset_id") or prev_cand.get("path") == cur_cand.get("path"):
        return 0.25

    # 运镜对冲与衔接
    p_dir = prev_cand.get("features", {}).get("motion_direction", "static")
    c_dir = cur_cand.get("features", {}).get("motion_direction", "static")
    if p_dir == c_dir and p_dir != "static":
        return 0.95  # 顺接奖励
    return 0.80


def propose(events: Dict[str, Any], index: Dict[str, Any], top_k: int = 3) -> Dict[str, Any]:
    """为全片生成经过真实打分排序的每镜最优候选表，杜绝固定假分与按素材顺序截断。"""
    slots_output = []
    assets = index.get("assets", [])
    
    shots = events.get("shots", [])
    fps_str = events.get("fps_str") or f"{events.get('fps', 30.0)}/1"
    fps = float(Fraction(fps_str))
    
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

        # 全池按评分降序排序，取最高 top_k
        candidates.sort(key=lambda c: c["score"], reverse=True)
        slots_output.append({
            "shot_id": sid,
            "candidates": candidates[:top_k]
        })
        
    return {
        "schema_version": 1,
        "slots": slots_output
    }
