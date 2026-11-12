"""smart_compose.py - 双模全片全局组接与真正波束搜索引擎 (M2)"""

import copy
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple
from scripts.smart_match import enumerate_windows, score_candidate, score_transition
from scripts.gap_analyzer import MaterialDeficitError, analyze_material_gaps, generate_capture_task_sheet
from scripts.shot_contract import ShotContract


def compose(
    timeline: Dict[str, Any],
    index: Dict[str, Any],
    beam_width: int = 8,
    top_k: int = 3,
    constraints: Optional[Dict[str, Any]] = None,
    preset: str = "default",
    allow_forced_fill: bool = False,
    task_sheet_out: Optional[str] = None
) -> Dict[str, Any]:
    """使用真正波束搜索（Beam Search）执行全片镜头全局优化组接。
    考虑单镜审美特征契合度、相邻镜头转场衔接与全局素材重复度惩罚，杜绝局部贪心组接。
    若包含叙事契约且存在未达标缺口，在未显式授权 allow_forced_fill 时严禁强行硬剪。
    """
    shots = timeline.get("shots", [])
    assets = index.get("assets", [])
    raw_fps = timeline.get("fps_str") or timeline.get("fps") or 30.0
    try:
        fps = float(Fraction(str(raw_fps)))
    except Exception:
        fps = float(timeline.get("fps", 30.0))
    
    if constraints and "preset" in constraints:
        preset = constraints["preset"]

    # 0. 契约扫描与缺口阻断前置检查
    raw_contracts = timeline.get("contracts") or (constraints.get("contracts") if constraints else None)
    if raw_contracts:
        parsed_contracts = [
            c if isinstance(c, ShotContract) else ShotContract.from_dict(c)
            for c in raw_contracts
        ]
        threshold = float(constraints.get("contract_threshold", 0.60)) if constraints else 0.60
        gap_res = analyze_material_gaps(parsed_contracts, index, threshold=threshold)
        if gap_res["status"] == "BLOCKED" and not allow_forced_fill:
            if task_sheet_out:
                from pathlib import Path
                generate_capture_task_sheet(gap_res, Path(task_sheet_out))
            raise MaterialDeficitError(
                f"素材库契约缺失：共 {gap_res['gap_count']}/{gap_res['total_shots']} 个镜头未达标，"
                f"已硬性阻断强行硬剪行为。如需补录请参阅任务单，或传 allow_forced_fill=True 强制执行。"
            )

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
                score = score_candidate(shot, w, preset=preset)
                w["score"] = score
                cands.append(w)
        # 按单镜分数降序
        cands.sort(key=lambda c: c["score"], reverse=True)
        # 为波束扩展保留跨素材多样性候选 (每个素材取最高分的 2-3 个窗口，杜绝单素材垄断候选池)
        asset_windows: Dict[str, List[Dict[str, Any]]] = {}
        for w in cands:
            aid = str(w.get("asset_id") or w.get("path") or "")
            if aid not in asset_windows:
                asset_windows[aid] = []
            if len(asset_windows[aid]) < 3:
                asset_windows[aid].append(w)
        diverse_cands = []
        for w_list in asset_windows.values():
            diverse_cands.extend(w_list)
        diverse_cands.sort(key=lambda c: c["score"], reverse=True)
        shot_candidates.append(diverse_cands if diverse_cands else [])

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
                # 0. 相邻镜头绝对防重复硬门禁
                if prev and (prev.get("path") == c.get("path") or prev.get("asset_id") == c.get("asset_id")):
                    continue

                # 1. 全局素材使用频次硬门禁：单素材全片复用绝对不超过 2 次
                used_paths = [p.get("path") for p in path if p is not None]
                cur_path = c.get("path")
                use_count = sum(1 for p in used_paths if p == cur_path)
                if use_count >= 2:
                    continue  # 彻底禁止继续使用该素材

                # 综合单镜分与转场分
                trans_score = score_transition(prev, c)
                step_score = c["score"] * 0.65 + trans_score * 0.35
                
                # 2. 全局复用递增惩罚
                if use_count == 1:
                    step_score *= 0.50

                # 3. 场景多样性奖励与同场景连用惩罚
                if prev:
                    prev_scene = prev.get("features", {}).get("dominant_scene", "")
                    cur_scene = c.get("features", {}).get("dominant_scene", "")
                    if prev_scene and cur_scene and prev_scene != cur_scene:
                        step_score *= 1.10  # 场景切换奖励
                    elif prev_scene and cur_scene and prev_scene == cur_scene:
                        step_score *= 0.70  # 同场景连用惩罚

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
