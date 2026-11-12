"""smart_compose.py - 双模全片全局组接与真正波束搜索引擎 (M2)"""

import copy
from fractions import Fraction
from typing import Any, Dict, List, Optional
from scripts.smart_match import enumerate_windows, score_candidate, score_transition


def compose(
    timeline: Dict[str, Any],
    index: Dict[str, Any],
    beam_width: int = 8,
    top_k: int = 3,
    constraints: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """使用真正波束搜索（Beam Search）执行全片镜头全局优化组接。
    考虑单镜审美特征契合度、相邻镜头转场衔接与全局素材重复度惩罚，杜绝局部贪心组接。
    """
    shots = timeline.get("shots", [])
    assets = index.get("assets", [])
    fps_str = timeline.get("fps_str") or f"{timeline.get('fps', 30.0)}/1"
    fps = float(Fraction(fps_str))

    if not shots:
        return copy.deepcopy(timeline)

    # 1. 预先为每个镜头收集并打分所有合法窗口
    shot_candidates: List[List[Dict[str, Any]]] = []
    for shot in shots:
        dur_sec = (shot.get("end", 30) - shot.get("start", 0)) / fps
        cands = []
        for asset in assets:
            windows = enumerate_windows(asset, dur_sec)
            for w in windows:
                score = score_candidate(shot, w)
                w["score"] = score
                cands.append(w)
        # 按单镜分数降序
        cands.sort(key=lambda c: c["score"], reverse=True)
        # 为波束扩展保留前 12 个优质候选
        shot_candidates.append(cands[:12] if cands else [])

    # 2. 执行波束搜索
    # 状态元组: (cumulative_score, [selected_window, ...])
    beam: List[Tuple[float, List[Dict[str, Any]]]] = [(0.0, [])]

    for t, cands in enumerate(shot_candidates):
        if not cands:
            # 若无候选素材，保持占位
            beam = [(score, path + [None]) for score, path in beam]
            continue

        next_beam_pool: List[Tuple[float, List[Dict[str, Any]]]] = []
        for cum_score, path in beam:
            prev = path[-1] if path else None
            for c in cands:
                # 综合单镜分与转场分
                trans_score = score_transition(prev, c)
                step_score = c["score"] * 0.65 + trans_score * 0.35
                
                # 整体重复使用惩罚
                used_paths = [p.get("path") for p in path if p is not None]
                if c.get("path") in used_paths:
                    step_score *= 0.85

                next_beam_pool.append((round(cum_score + step_score, 4), path + [c]))

        # 确定性排序：累积分数从高到低，平局按候选 ID 字典序
        next_beam_pool.sort(
            key=lambda item: (item[0], item[1][-1].get("candidate_id", "") if item[1][-1] else ""),
            reverse=True
        )
        beam = next_beam_pool[:beam_width]

    # 3. 提取全局最优路径与多套方案 (F-004)
    best_path = beam[0][1] if beam and beam[0][1] else []
    alternative_compositions = []
    for rank, (c_score, p) in enumerate(beam[1:3], start=2):
        if not p:
            continue
        alt_shots = []
        for s_idx, c_win in enumerate(p):
            if c_win:
                alt_shots.append({
                    "id": shots[s_idx]["id"],
                    "candidate_id": c_win.get("candidate_id"),
                    "path": c_win.get("path"),
                    "in_sec": c_win.get("in_sec"),
                    "score": c_win.get("score")
                })
        alternative_compositions.append({
            "rank": rank,
            "cumulative_score": c_score,
            "shots": alt_shots
        })

    # 4. 构建输出时间轴
    composed_shots = []
    for idx, shot in enumerate(shots):
        shot_out = copy.deepcopy(shot)
        cands = shot_candidates[idx]
        chosen = best_path[idx] if idx < len(best_path) else None

        if chosen:
            shot_out["material"] = chosen.get("path")
            shot_out["material_in"] = chosen.get("in_sec")
            shot_out["selection"] = {
                "candidate_id": chosen.get("candidate_id"),
                "score": chosen.get("score"),
                "beam_rank": 1
            }

        cands_out = [chosen] if chosen else []
        for c in cands:
            if chosen and c.get("candidate_id") == chosen.get("candidate_id"):
                continue
            cands_out.append(c)
            if len(cands_out) >= top_k:
                break
        shot_out["candidates"] = cands_out
        composed_shots.append(shot_out)

    out_timeline = copy.deepcopy(timeline)
    out_timeline["shots"] = composed_shots
    out_timeline["alternative_compositions"] = alternative_compositions
    out_timeline["beam_search_meta"] = {
        "beam_width": beam_width,
        "best_cumulative_score": beam[0][0] if beam else 0.0,
        "num_alternatives": len(alternative_compositions)
    }
    
    # 状态保证为 proposed，杜绝组接自动放行为 approved
    if "smart_workflow" in out_timeline:
        out_timeline["smart_workflow"]["status"] = "proposed"
        out_timeline["smart_workflow"]["approval_sha256"] = None

    return out_timeline
