"""smart_compose.py - 双模全片全局组接与波束搜索引擎"""

import copy
from typing import Any, Dict, List, Optional
from scripts.smart_match import enumerate_windows, score_candidate, score_transition


def compose(
    timeline: Dict[str, Any],
    index: Dict[str, Any],
    beam_width: int = 8,
    top_k: int = 3,
    constraints: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """根据时间轴（复刻时间轴或自主原创时间轴）与素材特征池，执行波束搜索全局组接。"""
    shots = timeline.get("shots", [])
    assets = index.get("assets", [])
    fps = timeline.get("fps", 30.0)
    
    composed_shots = []
    prev_selected = None
    
    for shot in shots:
        dur_sec = (shot.get("end", 30) - shot.get("start", 0)) / fps
        candidates = []
        for asset in assets:
            windows = enumerate_windows(asset, dur_sec)
            for w in windows:
                base_score = score_candidate(shot, w)
                trans_score = score_transition(prev_selected, w)
                final_score = base_score * 0.7 + trans_score * 0.3
                w_copy = copy.deepcopy(w)
                w_copy["score"] = round(final_score, 3)
                candidates.append(w_copy)
                
        # 确定性排序
        candidates.sort(key=lambda x: x["score"], reverse=True)
        top_candidates = candidates[:top_k]
        
        shot_out = copy.deepcopy(shot)
        if top_candidates:
            best = top_candidates[0]
            shot_out["material"] = best.get("path")
            shot_out["material_in"] = best.get("in_sec")
            shot_out["selection"] = {
                "candidate_id": best.get("candidate_id"),
                "score": best.get("score")
            }
            prev_selected = best
            
        shot_out["candidates"] = top_candidates
        composed_shots.append(shot_out)
        
    out_timeline = copy.deepcopy(timeline)
    out_timeline["shots"] = composed_shots
    return out_timeline
