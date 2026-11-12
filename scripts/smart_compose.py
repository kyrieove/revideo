"""smart_compose.py - 双模全片全局组接与真正波束搜索引擎 (M2)"""

import copy
import math
from pathlib import Path
from fractions import Fraction
from typing import Any, Dict, List, Optional, Tuple
from scripts.smart_match import enumerate_windows, score_candidate, score_transition
from scripts.gap_analyzer import MaterialDeficitError, analyze_material_gaps, generate_capture_task_sheet, evaluate_contract_match
from scripts.shot_contract import ShotContract, validate_contracts, evaluate_match_cut_transition


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

    # 0. 统一时间轴/契约门禁。旧人工 API 没有 contracts 时仍允许使用；
    # 显式声明需要契约，或传入空 contracts，不允许静默绕过。
    options = constraints or {}
    has_contract_key = "contracts" in timeline or "contracts" in options
    raw_contracts = timeline.get("contracts") if "contracts" in timeline else options.get("contracts")
    if not raw_contracts and (
        has_contract_key or options.get("require_contracts") or timeline.get("contract_required")
        or timeline.get("smart_workflow") is not None
    ):
        raise MaterialDeficitError("CONTRACTS_REQUIRED: 智能叙事组接必须提供非空 contracts")
    parsed_contracts = []
    threshold = float(options.get("contract_threshold", 0.60))
    if raw_contracts:
        parsed_contracts = [
            c if isinstance(c, ShotContract) else ShotContract.from_dict(c)
            for c in raw_contracts
        ]
        validate_contracts(parsed_contracts, fps=fps, shots=shots)
        gap_res = analyze_material_gaps(parsed_contracts, index, threshold=threshold)
        if gap_res["status"] != "PASSED" and not allow_forced_fill:
            sheet = Path(task_sheet_out or "capture_task_sheet.md")
            generate_capture_task_sheet(gap_res, sheet)
            raise MaterialDeficitError(
                f"素材契约未满足：缺口 {gap_res['gap_count']} 镜、"
                f"待复核 {gap_res['review_count']} 镜。补录/复核任务单：{sheet}",
                report=gap_res,
            )

    if not shots:
        return copy.deepcopy(timeline)

    # 1. 先执行每个窗口的语义准入，再用节奏、转场和能量进行排序。
    # 扫描整段素材时存在一个合格动作，并不等于所有入点都合格。
    shot_candidates: List[List[Dict[str, Any]]] = []
    window_deficits = []
    for idx, shot in enumerate(shots):
        dur_sec = (shot.get("end", 30) - shot.get("start", 0)) / fps
        c = parsed_contracts[idx] if parsed_contracts else None
        cands = []
        best_rejected = None
        for asset in assets:
            for w in enumerate_windows(asset, dur_sec):
                if c:
                    assessment = evaluate_contract_match(
                        w, c, threshold=threshold, require_window_evidence=True
                    )
                    w["contract_status"] = assessment["status"]
                    w["contract_score"] = assessment["score"]
                    w["contract_reason"] = assessment["reason"]
                    if assessment["status"] != "PASS":
                        if (best_rejected is None or assessment["score"] > best_rejected["best_score"]):
                            best_rejected = {
                                "shot_id": c.id, "contract": c,
                                "best_score": assessment["score"],
                                "best_candidate": w.get("path"),
                                "reason": "、".join(
                                    assessment["mismatches"] or assessment["missing"]
                                ) or assessment["reason"],
                            }
                        if not allow_forced_fill:
                            continue
                score = score_candidate(shot, w, preset=preset)
                if not math.isfinite(score):
                    continue
                w["score"] = round(
                    score * 0.45 + w["contract_score"] * 0.55, 3
                ) if c and w["contract_status"] == "PASS" else score
                cands.append(w)
        cands.sort(key=lambda candidate: candidate["score"], reverse=True)
        # 素材间保留多样性，单素材仅取前 3 个窗口。
        asset_windows: Dict[str, List[Dict[str, Any]]] = {}
        for w in cands:
            aid = str(w.get("asset_id") or w.get("path") or "")
            asset_windows.setdefault(aid, [])
            if len(asset_windows[aid]) < 3:
                asset_windows[aid].append(w)
        diverse_cands = [w for group in asset_windows.values() for w in group]
        diverse_cands.sort(key=lambda w: w["score"], reverse=True)
        if not diverse_cands:
            if c:
                window_deficits.append(best_rejected or {
                    "shot_id": c.id, "contract": c,
                    "best_score": 0.0, "best_candidate": None,
                    "reason": "没有足够长度或满足动作语义的候选时间窗口",
                })
            else:
                raise MaterialDeficitError(
                    f"NO_VALID_WINDOWS: 镜头 #{shot.get('id')} 没有可用素材窗口"
                )
        shot_candidates.append(diverse_cands)
    if window_deficits:
        report = {
            "status": "BLOCKED", "gaps": window_deficits,
            "review_required": [], "total_shots": len(shots),
            "gap_count": len(window_deficits),
            "matched_count": len(shots) - len(window_deficits),
            "review_count": 0, "threshold": threshold,
        }
        sheet = Path(task_sheet_out or "capture_task_sheet.md")
        generate_capture_task_sheet(report, sheet)
        raise MaterialDeficitError(
            f"NO_COMPLIANT_WINDOWS: {len(window_deficits)} 镜没有契约合规的时间窗口；任务单：{sheet}",
            report=report,
        )

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
                if prev and not allow_forced_fill and (prev.get("path") == c.get("path") or prev.get("asset_id") == c.get("asset_id")):
                    continue

                # 1. 全局素材使用频次硬门禁：单素材全片复用绝对不超过 2 次
                used_paths = [p.get("path") for p in path if p is not None]
                cur_path = c.get("path")
                use_count = sum(1 for p in used_paths if p == cur_path)
                if use_count >= 2 and not allow_forced_fill:
                    continue  # 未授权禁止超限复用

                # Match Cut 属于跨镜头硬约束，不能用高运动能量或场景分数补足。
                transition = (
                    evaluate_match_cut_transition(prev, c, parsed_contracts[t])
                    if parsed_contracts else {"status": "PASS", "reason": "not_required"}
                )
                if transition["status"] != "PASS" and not allow_forced_fill:
                    continue
                candidate_for_path = dict(c)
                candidate_for_path["transition_status"] = transition["status"]
                candidate_for_path["transition_reason"] = transition["reason"]

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

                next_beam_pool.append((round(cum_score + step_score, 4), path + [candidate_for_path]))

        if not next_beam_pool:
            raise MaterialDeficitError(
                f"NO_FEASIBLE_COMPOSITION: 第 {t + 1}/{len(shots)} 镜未找到满足"
                "复用限制、Match Cut 连续性及素材约束的完整路径"
            )
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
                "beam_rank": 1,
                "contract_status": chosen.get("contract_status", "NOT_APPLICABLE"),
                "contract_score": chosen.get("contract_score"),
                "contract_reason": chosen.get("contract_reason"),
                "transition_status": chosen.get("transition_status"),
                "transition_reason": chosen.get("transition_reason"),
                "forced_fill": bool(parsed_contracts and (
                    chosen.get("contract_status") != "PASS"
                    or chosen.get("transition_status") != "PASS"
                )),
                "semantic_evidence": chosen.get("semantic_evidence"),
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
    if parsed_contracts:
        # 即使 contracts 来自 constraints，也必须随方案固化；
        # 否则后续审批/渲染将无法识别存在过的契约门禁。
        out_timeline["contracts"] = [c.to_dict() for c in parsed_contracts]
        out_timeline["contract_audit"] = {
            "status": "FORCED" if any(s.get("selection", {}).get("forced_fill") for s in composed_shots) else "PASSED",
            "shots": [
                {
                    "shot_id": s["id"],
                    "path": s.get("material"),
                    "in_sec": s.get("material_in"),
                    "status": "FORCED" if s["selection"].get("forced_fill") else "PASS",
                    "semantic_status": s["selection"].get("contract_status"),
                    "transition_status": s["selection"].get("transition_status"),
                    "reason": (
                        s["selection"].get("transition_reason")
                        if s["selection"].get("transition_status") != "PASS"
                        else s["selection"].get("contract_reason")
                    ),
                }
                for s in composed_shots
            ],
        }
    out_timeline["beam_search_meta"] = {
        "beam_width": beam_width,
        "best_cumulative_score": beam[0][0] if beam else 0.0,
        "num_alternatives": len(alternative_compositions),
        "forced_fill_authorized": bool(allow_forced_fill)
    }
    
    # 状态保证为 proposed，杜绝组接自动放行为 approved
    if "smart_workflow" in out_timeline:
        out_timeline["smart_workflow"]["status"] = "proposed"
        out_timeline["smart_workflow"]["approval_sha256"] = None

    return out_timeline
