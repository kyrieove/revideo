"""smart_reference.py - 参考片目标特征推导 (M2)"""

from typing import Any, Dict, List, Optional


def derive_targets(events: Dict[str, Any], reference_video: Optional[str] = None, manual_labels: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    """从参考片事件表推导各个镜头槽位的目标特征画像。"""
    targets = []
    shots = events.get("shots", [])
    for shot in shots:
        sid = shot.get("id")
        start = shot.get("start", 0)
        end = shot.get("end", 0)
        dur_frames = end - start
        
        target = {
            "shot_id": sid,
            "duration_frames": dur_frames,
            "role": shot.get("role", "unknown"),
            "target_scale": shot.get("scale_ref", "unknown"),
            "target_motion": "unknown",
            "needs_review": True
        }
        targets.append(target)
    return targets
