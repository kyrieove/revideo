"""shot_contract.py - 镜头叙事契约模型与校验契约 (Narrative Shot Contract)

定义每个镜头在影视叙事维度的硬性要求，包括主体、景别、关键动作、运镜流向及转场匹配。
用于替代原先单一的标量能量与色彩匹配。
"""

import json
import math
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class ShotContract:
    id: int
    start_frame: int
    end_frame: int
    duration_frames: int
    duration_seconds: float
    beat_peak_frame: Optional[int] = None
    subject: str = "player_character"  # player_character, npc, scenery_empty, environment
    framing: str = "full_shot"         # close_up, medium_shot, full_shot, long_shot
    action: str = "static"             # 核心动作描述，如 walking_right, pose_drinking, sheathing_sword
    camera_motion: str = "static"      # pan_right, pan_left, push_in, pull_out, static
    match_cut: bool = False            # 是否为动作/主体位置连续的 Match Cut 转场
    viewfinder: bool = False           # 是否需要叠加相机 HUD 图层
    scene_type: str = "scenic"         # 场景类型如 snow_mountain, watermill, bamboo_forest
    notes: str = ""                    # 导演/操作者备忘说明
    narrative_role: str = ""           # establish/action/reveal/transition...
    subject_position: Dict[str, Any] = field(default_factory=dict)
    action_anchors: List[Dict[str, Any]] = field(default_factory=list)
    camera_trajectory: Dict[str, Any] = field(default_factory=dict)
    transition_contract: Dict[str, Any] = field(default_factory=dict)
    visual_style: Dict[str, Any] = field(default_factory=dict)
    evidence: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ShotContract":
        return cls(
            id=int(data["id"]),
            start_frame=int(data["start_frame"]),
            end_frame=int(data["end_frame"]),
            duration_frames=int(data.get("duration_frames", data["end_frame"] - data["start_frame"])),
            duration_seconds=float(data.get("duration_seconds", (data["end_frame"] - data["start_frame"]) / 30.0)),
            beat_peak_frame=data.get("beat_peak_frame"),
            subject=data.get("subject", "player_character"),
            framing=data.get("framing", "full_shot"),
            action=data.get("action", "static"),
            camera_motion=data.get("camera_motion", "static"),
            match_cut=bool(data.get("match_cut", False)),
            viewfinder=bool(data.get("viewfinder", False)),
            scene_type=data.get("scene_type", "scenic"),
            notes=data.get("notes", ""),
            narrative_role=data.get("narrative_role", ""),
            subject_position=dict(data.get("subject_position") or {}),
            action_anchors=list(data.get("action_anchors") or []),
            camera_trajectory=dict(data.get("camera_trajectory") or {}),
            transition_contract=dict(data.get("transition_contract") or {}),
            visual_style=dict(data.get("visual_style") or {}),
            evidence=dict(data.get("evidence") or {})
        )


def validate_contracts(
    contracts: List[ShotContract],
    fps: Optional[float] = None,
    shots: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """验证完整覆盖、唯一镜号、精确帧数、锚点和可选时间轴映射。"""
    if not contracts:
        raise ValueError("契约列表不能为空")
    if fps is not None and (not math.isfinite(fps) or fps <= 0):
        raise ValueError("fps 必须有限且为正")
    if shots is not None and len(shots) != len(contracts):
        raise ValueError("契约镜头数量与时间轴不一致")
    prev_end = 0
    ids = set()
    for i, c in enumerate(contracts):
        if type(c.id) is not int or c.id in ids:
            raise ValueError(f"契约镜头 ID 无效或重复: {c.id}")
        ids.add(c.id)
        if not all(type(v) is int for v in (c.start_frame, c.end_frame, c.duration_frames)):
            raise ValueError(f"镜头 #{c.id} 帧号必须是整数")
        if c.start_frame != prev_end or c.end_frame <= c.start_frame:
            raise ValueError(f"镜头 #{c.id} 与前一镜头不连续或帧区间无效")
        if c.duration_frames != c.end_frame - c.start_frame:
            raise ValueError(f"镜头 #{c.id} duration_frames 与起止帧不一致")
        if i == 0 and c.match_cut:
            raise ValueError(f"镜头 #{c.id} 是首镜，不能要求与不存在的上一镜进行 Match Cut")
        if not math.isfinite(c.duration_seconds) or c.duration_seconds <= 0:
            raise ValueError(f"镜头 #{c.id} duration_seconds 无效")
        if fps is not None and abs(c.duration_seconds - c.duration_frames / fps) > 0.5 / fps:
            raise ValueError(f"镜头 #{c.id} 时长与时间轴帧率不一致")
        if c.beat_peak_frame is not None:
            if type(c.beat_peak_frame) is not int or not c.start_frame <= c.beat_peak_frame < c.end_frame:
                raise ValueError(f"镜头 #{c.id} 重音帧不在镜头内")
        for anchor in c.action_anchors:
            if not isinstance(anchor, dict):
                raise ValueError(f"镜头 #{c.id} 动作锚点格式错误")
            frame = anchor.get("frame")
            if frame is not None and (type(frame) is not int or not c.start_frame <= frame < c.end_frame):
                raise ValueError(f"镜头 #{c.id} 动作锚点越界")
        if shots is not None:
            shot = shots[i]
            if (shot.get("id"), shot.get("start"), shot.get("end")) != (c.id, c.start_frame, c.end_frame):
                raise ValueError(f"镜头 #{c.id} 与时间轴编号或边界不一致")
        prev_end = c.end_frame
    return True

def evaluate_match_cut_transition(
    previous_window: Optional[Dict[str, Any]],
    current_window: Dict[str, Any],
    contract: ShotContract,
) -> Dict[str, Any]:
    """对齐接缝两侧经过时间标注的动作姿态及归一化主体位置。

    只接受窗口边界的显式 anchor，避免使用全片的平均人物位置替代切点证据。
    """
    if not contract.match_cut:
        return {"status": "PASS", "reason": "not_required"}
    if previous_window is None:
        return {"status": "REVIEW_REQUIRED", "reason": "match_cut_missing_previous"}
    left = previous_window.get("end_anchor")
    right = current_window.get("start_anchor")
    if not isinstance(left, dict) or not isinstance(right, dict):
        return {"status": "REVIEW_REQUIRED", "reason": "match_cut_boundary_anchors_missing"}
    left_pose, right_pose = left.get("pose"), right.get("pose")
    if not isinstance(left_pose, str) or not left_pose or not isinstance(right_pose, str) or not right_pose:
        return {"status": "REVIEW_REQUIRED", "reason": "match_cut_pose_unknown"}
    if left_pose != right_pose:
        return {"status": "GAP", "reason": "match_cut_pose_mismatch"}
    p1, p2 = left.get("position"), right.get("position")
    if not isinstance(p1, dict) or not isinstance(p2, dict):
        return {"status": "REVIEW_REQUIRED", "reason": "match_cut_position_unknown"}
    try:
        x1, y1, x2, y2 = [float(x) for x in (p1["x"], p1["y"], p2["x"], p2["y"])]
        tolerance = float(contract.transition_contract.get("max_position_delta", 0.16))
    except (ValueError, TypeError, KeyError):
        return {"status": "REVIEW_REQUIRED", "reason": "match_cut_position_unreadable"}
    if (not all(math.isfinite(x) and 0 <= x <= 1 for x in (x1, y1, x2, y2))
        or not math.isfinite(tolerance) or not 0 <= tolerance <= 1):
        return {"status": "REVIEW_REQUIRED", "reason": "match_cut_invalid_coordinates"}
    if math.hypot(x1 - x2, y1 - y2) > tolerance:
        return {"status": "GAP", "reason": "match_cut_subject_position_mismatch"}
    return {"status": "PASS", "reason": "match_cut_poses_and_positions_aligned"}


def save_contracts(contracts: List[ShotContract], path: Path) -> None:
    data = {
        "version": 1,
        "total_shots": len(contracts),
        "total_frames": contracts[-1].end_frame if contracts else 0,
        "contracts": [c.to_dict() for c in contracts]
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_contracts(path: Path) -> List[ShotContract]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if raw.get("version") != 1:
        raise ValueError("不支持的契约版本")
    item_list = raw.get("contracts", [])
    result = [ShotContract.from_dict(item) for item in item_list]
    validate_contracts(result)
    if len(result) != raw.get("total_shots") or result[-1].end_frame != raw.get("total_frames"):
        raise ValueError("契约头部统计与实际镜头不一致")
    return result
