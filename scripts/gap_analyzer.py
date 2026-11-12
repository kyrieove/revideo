"""叙事契约的三态缺口扫描与面向玩家的补录任务单。

PASS: 已有足够证据且关键条件通过。
REVIEW_REQUIRED: 关键语义标签缺失，不能当作通过，也不能误报为缺素材。
GAP: 素材时长不足、确知关键条件不符合或索引里没有有效素材。
"""
import math
from pathlib import Path
from typing import Any, Dict, List, Optional

from scripts.shot_contract import ShotContract


class MaterialDeficitError(Exception):
    """素材不足、待复核或无完整可行组接路径。"""

    def __init__(self, message: str, report: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.report = report


def _labels(features: Dict[str, Any], field: str, aliases=()) -> List[str]:
    """严格比较规范化标签；禁止用字符串子串命中不同动作。"""
    values = [features.get(field)]
    values.extend(features.get(k) for k in aliases)
    result = []
    for value in values:
        if isinstance(value, str) and value.strip():
            result.append(value.strip().lower())
        elif isinstance(value, (list, tuple, set)):
            result.extend(x.strip().lower() for x in value if isinstance(x, str) and x.strip())
    return result


def evaluate_contract_match(
    asset: Dict[str, Any],
    contract: ShotContract,
    threshold: float = 0.60,
    require_window_evidence: bool = False,
) -> Dict[str, Any]:
    """对单个素材或具体候选窗口执行硬条件 + 软评分 + 缺失证据判定。"""
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("contract_threshold 必须在 [0, 1] 范围内且有限")
    duration = asset.get("duration_seconds")
    if duration is None and asset.get("in_sec") is not None and asset.get("out_sec") is not None:
        duration = float(asset["out_sec"]) - float(asset["in_sec"])
    try:
        duration = float(duration)
    except (TypeError, ValueError, OverflowError):
        duration = float("nan")
    if not math.isfinite(duration) or duration + 1e-6 < contract.duration_seconds or asset.get("valid") is False:
        return {
            "status": "GAP",
            "score": 0.0,
            "missing": [],
            "mismatches": ["素材不可用或可用时长不足"],
            "reason": "duration_or_invalid",
        }

    feats = asset.get("features") or {}
    if not isinstance(feats, dict):
        feats = {}
    tags = _labels(feats, "scene_tags")
    missing, mismatches = [], []
    scores = {}

    subject_labels = _labels(feats, "subject")
    if contract.subject.lower() not in ("any", "unknown"):
        if not subject_labels:
            missing.append("subject")
            scores["subject"] = 0.0
        elif contract.subject.lower() == "scenery_empty" and any(x in ("scenery_empty", "environment") for x in subject_labels):
            scores["subject"] = 1.0
        elif contract.subject.lower() in subject_labels:
            scores["subject"] = 1.0
        else:
            scores["subject"] = 0.0
            mismatches.append("主体不符")
    else:
        scores["subject"] = 1.0

    requested_action = contract.action.strip().lower()
    action_labels = _labels(feats, "action", ("actions", "action_tags"))
    if requested_action in ("any", "static", "none"):
        scores["action"] = 0.9
    elif not action_labels:
        scores["action"] = 0.0
        missing.append("action")
    elif requested_action not in action_labels and requested_action not in tags:
        scores["action"] = 0.0
        mismatches.append("核心动作不符")
    else:
        scores["action"] = 1.0
        if require_window_evidence and not asset.get("semantic_evidence"):
            missing.append("action_window_evidence")

    requested_camera = contract.camera_motion.strip().lower()
    # camera_motion 与主体/屏幕运动方向严格分离。direction 不能冒充相机轨迹。
    camera_labels = _labels(feats, "camera_motion")
    if requested_camera in ("static", "any"):
        scores["camera"] = 0.9
    elif not camera_labels:
        scores["camera"] = 0.0
        missing.append("camera_motion")
    elif requested_camera in camera_labels:
        scores["camera"] = 1.0
    else:
        scores["camera"] = 0.0
        mismatches.append("运镜不符")

    scene_labels = _labels(feats, "dominant_scene") + tags
    requested_scene = contract.scene_type.strip().lower()
    if requested_scene in ("scenic", "any"):
        scores["scene"] = 0.9
    elif not scene_labels:
        scores["scene"] = 0.0
        missing.append("scene_type")
    elif requested_scene in scene_labels:
        scores["scene"] = 1.0
    else:
        scores["scene"] = 0.0
        mismatches.append("场景类型不符")

    score = round(
        scores["subject"] * 0.35
        + scores["action"] * 0.35
        + scores["camera"] * 0.15
        + scores["scene"] * 0.15,
        3,
    )
    if mismatches:
        # 硬条件失败不得靠其他维度凑到 0.60。
        status = "GAP"
        score = min(score, 0.49)
    elif missing:
        status = "REVIEW_REQUIRED"
    else:
        status = "PASS" if score >= threshold else "GAP"
    return {
        "status": status,
        "score": score,
        "missing": missing,
        "mismatches": mismatches,
        "reason": "hard_mismatch" if mismatches else ("unknown_evidence" if missing else "scored"),
    }


def evaluate_asset_against_contract(asset: Dict[str, Any], contract: ShotContract) -> float:
    """旧调用方兼容：返回分数。准入判断应使用 evaluate_contract_match 的状态。"""
    return evaluate_contract_match(asset, contract)["score"]


def analyze_material_gaps(
    contracts: List[ShotContract],
    index: Dict[str, Any],
    threshold: float = 0.60,
) -> Dict[str, Any]:
    if not math.isfinite(threshold) or not 0.0 <= threshold <= 1.0:
        raise ValueError("contract_threshold 必须在 [0, 1] 范围内且有限")
    if not contracts:
        raise ValueError("没有镜头契约，禁止以 0 个缺口代表通过")
    raw_assets = index.get("assets", [])
    if not isinstance(raw_assets, list):
        raise ValueError("素材索引 assets 必须为数组")
    assets = [a for a in raw_assets if isinstance(a, dict) and a.get("valid") is True]
    gaps, matched_shots, review_required = [], [], []
    rank = {"PASS": 2, "REVIEW_REQUIRED": 1, "GAP": 0}

    for c in contracts:
        best = None
        best_asset = None
        for a in assets:
            ev = evaluate_contract_match(a, c, threshold=threshold)
            if best is None or (rank[ev["status"]], ev["score"]) > (rank[best["status"]], best["score"]):
                best, best_asset = ev, a
        if best is None:
            best = {
                "status": "GAP", "score": 0.0, "missing": [],
                "mismatches": ["素材库为空或无有效素材"], "reason": "no_valid_assets",
            }
        entry = {
            "shot_id": c.id,
            "contract": c,
            "best_score": best["score"],
            "best_candidate": best_asset.get("path") if best_asset else None,
            "reason": "、".join(best["mismatches"] or best["missing"]) or best["reason"],
            "missing": best["missing"],
            "mismatches": best["mismatches"],
        }
        if best["status"] == "PASS":
            matched_shots.append({**entry, "asset": best_asset.get("path")})
        elif best["status"] == "REVIEW_REQUIRED":
            review_required.append(entry)
        else:
            gaps.append(entry)

    status = "BLOCKED" if gaps else ("REVIEW_REQUIRED" if review_required else "PASSED")
    return {
        "status": status,
        "total_shots": len(contracts),
        "matched_count": len(matched_shots),
        "gap_count": len(gaps),
        "review_count": len(review_required),
        "gaps": gaps,
        "review_required": review_required,
        "matched_shots": matched_shots,
        "threshold": threshold,
    }


def _cell(value: Any) -> str:
    return str(value).replace("|", "／").replace("\n", " ").strip()


def generate_capture_task_sheet(gap_result: Dict[str, Any], out_path: Path) -> Path:
    """生成可以直接按步骤录制的中文补录/人工复核任务单。"""
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    gaps = gap_result.get("gaps", [])
    reviews = gap_result.get("review_required", [])
    total = gap_result.get("total_shots", 0)
    lines = [
        "# 游戏内补录与素材复核任务单",
        "",
        f"> {total} 镜；确定缺口 {len(gaps)} 镜；信息不足待复核 {len(reviews)} 镜。",
        "> 不要盲目填充。先复核未知项，再补录确认缺失的动作。",
        "",
        "## 需要补录的镜头",
        "",
        "| 镜号 | 成片使用 | 建议录制 | 场景 | 主体/景别 | 必须完成的动作 | 运镜 | 对齐时间点 |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for item in gaps:
        c: ShotContract = item["contract"]
        capture_s = max(8, round(c.duration_seconds + 6, 1))
        beat = f"镜头内第 {c.beat_peak_frame - c.start_frame} 帧" if c.beat_peak_frame is not None else "无明确重音锚点"
        lines.append(
            f"| #{c.id:02d} | {c.duration_seconds:.2f} 秒 | {capture_s:g} 秒 | "
            f"{_cell(c.scene_type)} | {_cell(c.subject)}／{_cell(c.framing)} | "
            f"{_cell(c.action)} | {_cell(c.camera_motion)} | {beat} |"
        )
        lines.extend([
            "",
            f"### 镜头 #{c.id:02d}：拍摄步骤",
            f"1. 进入 {_cell(c.scene_type)} 场景，准备 {_cell(c.subject)}，调整为 {_cell(c.framing)} 景别并隐藏 HUD。",
            f"2. 开始录屏，先保留约 3 秒稳定画面，再完成 {_cell(c.action)}。",
            f"3. 按 {_cell(c.camera_motion)} 方向运镜，动作结束后再保留约 3 秒，累计至少录 {capture_s:g} 秒。",
            f"4. 将原始视频存入素材目录；选出包含完整动作的时间窗口，再重新构建素材索引。",
            f"- 缺口依据：{_cell(item.get('reason', '未找到合格候选'))}",
        ])
        if c.match_cut:
            lines.append("- 与下一镜头匹配剪辑：让人物结束姿态、构图位置和下一镜的起始姿态一致。")
        if c.viewfinder:
            lines.append("- 成片要求相机取景框 HUD 图层；录制原素材时不必保留游戏 HUD。")
        if c.notes:
            lines.append(f"- 导演说明：{_cell(c.notes)}")
        if c.action_anchors:
            lines.append(f"- 参考动作锚点：{_cell(c.action_anchors)}")
        lines.append("")
    lines.extend(["", "## 需要人工复核的镜头（不是确定缺口）", ""])
    for item in reviews:
        c = item["contract"]
        lines.append(
            f"- 镜头 #{c.id:02d}：{_cell(item.get('reason'))}；"
            f"候选：{_cell(item.get('best_candidate') or '无')}。"
            "请在候选时间窗口核对并标注动作/主体/相机证据。"
        )
    lines.extend([
        "",
        "## 提交检查",
        "",
        "- 原始录屏不要重新编码、裁短或删除关键动作的前后缓冲。",
        "- 录制时长是建议值，不是成片占用时长；以动作完整度为准。",
        "- 重新索引后，确保具体时间窗口的动作与运镜标签已通过人工核验或可信识别。",
    ])
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out_path
