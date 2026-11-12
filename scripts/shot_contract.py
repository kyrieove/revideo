"""shot_contract.py - 镜头叙事契约模型与校验契约 (Narrative Shot Contract)

定义每个镜头在影视叙事维度的硬性要求，包括主体、景别、关键动作、运镜流向及转场匹配。
用于替代原先单一的标量能量与色彩匹配。
"""

import json
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
            notes=data.get("notes", "")
        )


def validate_contracts(contracts: List[ShotContract]) -> bool:
    """校验契约连续性与时间合法性。"""
    if not contracts:
        raise ValueError("契约列表不能为空")
    prev_end = None
    for c in contracts:
        if c.end_frame <= c.start_frame:
            raise ValueError(f"镜头 #{c.id} 结束帧 ({c.end_frame}) 必须大于起始帧 ({c.start_frame})")
        if prev_end is not None and c.start_frame != prev_end:
            raise ValueError(f"镜头 #{c.id} 起始帧 ({c.start_frame}) 与前一镜头结束帧 ({prev_end}) 不连续")
        prev_end = c.end_frame
    return True


def save_contracts(contracts: List[ShotContract], path: Path) -> None:
    data = {
        "version": 1,
        "total_shots": len(contracts),
        "total_frames": contracts[-1].end_frame if contracts else 0,
        "contracts": [c.to_dict() for c in contracts]
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def load_contracts(path: Path) -> List[ShotContract]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    item_list = raw.get("contracts", [])
    return [ShotContract.from_dict(item) for item in item_list]
