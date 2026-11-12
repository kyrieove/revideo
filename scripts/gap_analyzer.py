"""gap_analyzer.py - 镜头契约缺口扫描与游戏内补录任务单生成引擎 (Gap Analyzer)

职责：
1. 逐镜比对《叙事契约表》与本地素材库；
2. 依据动作、主体存在性、运镜流向综合评定语义达标率；
3. 低于阈值（默认 0.60）判定为契约缺失（Gap），硬性阻断贪婪拼凑；
4. 自动生成面向操作者的结构化《游戏内补录任务需求单》（capture_task_sheet.md）。
"""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from scripts.shot_contract import ShotContract


class MaterialDeficitError(Exception):
    """当素材库无法满足叙事契约、且未获得显式硬剪授权时抛出。"""
    pass


def evaluate_asset_against_contract(asset: Dict[str, Any], contract: ShotContract) -> float:
    """计算单个素材与镜头契约的语义匹配度 (0.0 ~ 1.0)。"""
    dur = float(asset.get("duration_seconds", 0.0))
    if dur < contract.duration_seconds:
        return 0.0

    feats = asset.get("features", {})
    asset_scene = feats.get("dominant_scene", "")
    asset_tags = feats.get("scene_tags", [])
    asset_action = feats.get("action", "")
    asset_subject = feats.get("subject", "environment")
    asset_motion = feats.get("motion_direction", feats.get("dominant_direction", "static"))

    # 1. 主体匹配度 (权重 0.35)
    if contract.subject == "scenery_empty":
        subj_score = 1.0 if asset_subject in ("scenery_empty", "environment") else 0.4
    else:
        subj_score = 1.0 if asset_subject == contract.subject else (0.2 if asset_subject == "scenery_empty" else 0.5)

    # 2. 动作匹配度 (权重 0.35)
    if contract.action in ("static", "any", "none"):
        act_score = 0.9
    elif contract.action in asset_action or contract.action in asset_tags:
        act_score = 1.0
    else:
        act_score = 0.2

    # 3. 运镜与运动方向匹配度 (权重 0.15)
    if contract.camera_motion in ("static", "any"):
        mot_score = 0.9
    elif contract.camera_motion == asset_motion:
        mot_score = 1.0
    else:
        mot_score = 0.3

    # 4. 场景类型匹配度 (权重 0.15)
    if contract.scene_type in ("scenic", "any"):
        scene_score = 0.9
    elif contract.scene_type == asset_scene or contract.scene_type in asset_tags:
        scene_score = 1.0
    else:
        scene_score = 0.4

    total_score = round(subj_score * 0.35 + act_score * 0.35 + mot_score * 0.15 + scene_score * 0.15, 3)
    return total_score


def analyze_material_gaps(
    contracts: List[ShotContract],
    index: Dict[str, Any],
    threshold: float = 0.60
) -> Dict[str, Any]:
    """扫描全素材库，识别契约缺失镜头。"""
    assets = [a for a in index.get("assets", []) if a.get("valid", True)]
    
    gaps = []
    matched_shots = []

    for c in contracts:
        best_score = 0.0
        best_asset = None
        for a in assets:
            score = evaluate_asset_against_contract(a, c)
            if score > best_score:
                best_score = score
                best_asset = a

        if best_score < threshold:
            gaps.append({
                "shot_id": c.id,
                "contract": c,
                "best_score": best_score,
                "best_candidate": best_asset.get("path") if best_asset else None,
                "reason": f"最高匹配分 {best_score:.2f} 低于门禁阈值 {threshold:.2f} (主体: {c.subject}, 动作: {c.action}, 运镜: {c.camera_motion})"
            })
        else:
            matched_shots.append({
                "shot_id": c.id,
                "contract": c,
                "best_score": best_score,
                "asset": best_asset.get("path")
            })

    status = "BLOCKED" if gaps else "PASSED"
    return {
        "status": status,
        "total_shots": len(contracts),
        "matched_count": len(matched_shots),
        "gap_count": len(gaps),
        "gaps": gaps,
        "matched_shots": matched_shots,
        "threshold": threshold
    }


def generate_capture_task_sheet(gap_result: Dict[str, Any], out_path: Path) -> Path:
    """生成结构化、面向玩家在游戏内录屏补拍的《游戏内补录需求单》Markdown 文件。"""
    gaps = gap_result.get("gaps", [])
    total = gap_result.get("total_shots", 0)
    matched = gap_result.get("matched_count", 0)
    gap_cnt = gap_result.get("gap_count", 0)

    lines = [
        "# 《游戏内补录需求任务单》（revideo 契约缺口阻断报表）",
        "",
        f"> **阻断状态**：已发现 {gap_cnt}/{total} 个镜头素材无法满足影视叙事契约。",
        "> **流水线行为**：波束搜索已暂停，已硬性阻断强行硬剪行为。请按以下清单录制补录素材后放入素材库重新扫描。",
        "",
        "## 一、缺失镜头补录详单",
        "",
        "| 镜号 | 目标时长 | 场景/地点 | 主体与服饰 | 核心动作姿势 | 镜头运镜朝向 | 重音打击时机 |",
        "|---|---|---|---|---|---|---|"
    ]

    for item in gaps:
        c: ShotContract = item["contract"]
        beat_info = f"第 {c.beat_peak_frame - c.start_frame} 帧" if c.beat_peak_frame else "随节奏自然过渡"
        lines.append(
            f"| #{c.id:02d} | {c.duration_seconds:.2f}s ({c.duration_frames}f) | {c.scene_type} | "
            f"{c.subject} ({c.framing}) | {c.action} | {c.camera_motion} | {beat_info} |"
        )

    lines.extend([
        "",
        "## 二、游戏内录制实操指引（3 分钟速录指南）",
        "1. **画面干净度**：在游戏设置中开启拍照模式或按快捷键隐藏全部 HUD、NPC 名字与任务提示；",
        "2. **运镜规范**：若表格标明 `pan_right`，请保持鼠标向右平滑平移，角色保持在画面相对固定位置；",
        "3. **动作连贯性**：若标明 `match_cut`，请让角色在不同场景重复相同动作或保持姿态，以实现高级动作转场；",
        "4. **录制完成交付**：录制生成的 `.mp4` 文件直接复制放入本项目的 `src/raw/` 目录，随后重新运行合成即可。"
    ])

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path
