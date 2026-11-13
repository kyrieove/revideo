"""viewfinder_fx.py - 高保真相机取景框 HUD 视效合成图层生成与视频叠加"""

import cv2
import numpy as np


def generate_viewfinder_overlay(width: int = 1920, height: int = 1080, rec_red: bool = True) -> np.ndarray:
    """生成 1920x1080 电影级透明通道相机取景框 HUD 图层 (BGRA)。"""
    overlay = np.zeros((height, width, 4), dtype=np.uint8)
    
    white = (255, 255, 255, 225)
    red = (30, 30, 235, 255)
    
    margin = 55
    arm = 90
    th = 3
    
    # 1. 四角 L 形取景标线
    cv2.line(overlay, (margin, margin), (margin + arm, margin), white, th)
    cv2.line(overlay, (margin, margin), (margin, margin + arm), white, th)
    cv2.line(overlay, (width - margin, margin), (width - margin - arm, margin), white, th)
    cv2.line(overlay, (width - margin, margin), (width - margin, margin + arm), white, th)
    cv2.line(overlay, (margin, height - margin), (margin + arm, height - margin), white, th)
    cv2.line(overlay, (margin, height - margin), (margin, height - margin - arm), white, th)
    cv2.line(overlay, (width - margin, height - margin), (width - margin - arm, height - margin), white, th)
    cv2.line(overlay, (width - margin, height - margin), (width - margin, height - margin - arm), white, th)
    
    # 2. 右上角 REC 录制指示
    font = cv2.FONT_HERSHEY_SIMPLEX
    if rec_red:
        cv2.circle(overlay, (width - 180, margin + 25), 9, red, -1)
    cv2.putText(overlay, "REC", (width - 160, margin + 33), font, 0.9, white, 2, cv2.LINE_AA)
    
    # 3. 左上角 电池图标
    bx, by, bw, bh = margin + 120, margin + 18, 55, 24
    cv2.rectangle(overlay, (bx, by), (bx + bw, by + bh), white, 2)
    cv2.rectangle(overlay, (bx + bw, by + 6), (bx + bw + 5, by + bh - 6), white, -1)
    cv2.rectangle(overlay, (bx + 4, by + 4), (bx + bw - 15, by + bh - 4), white, -1)
    
    # 4. 中央对焦框 [ . ]
    cx, cy = width // 2, height // 2
    f_arm = 35
    f_box = 80
    cv2.line(overlay, (cx - f_box, cy - f_box), (cx - f_box + f_arm, cy - f_box), white, 2)
    cv2.line(overlay, (cx - f_box, cy - f_box), (cx - f_box, cy - f_box + f_arm), white, 2)
    cv2.line(overlay, (cx + f_box, cy - f_box), (cx + f_box - f_arm, cy - f_box), white, 2)
    cv2.line(overlay, (cx + f_box, cy - f_box), (cx + f_box, cy - f_box + f_arm), white, 2)
    cv2.line(overlay, (cx - f_box, cy + f_box), (cx - f_box + f_arm, cy + f_box), white, 2)
    cv2.line(overlay, (cx - f_box, cy + f_box), (cx - f_box, cy - f_box + f_arm), white, 2)
    cv2.line(overlay, (cx + f_box, cy + f_box), (cx + f_box - f_arm, cy + f_box), white, 2)
    cv2.line(overlay, (cx + f_box, cy + f_box), (cx + f_box, cy - f_box + f_arm), white, 2)
    cv2.circle(overlay, (cx, cy), 5, white, -1)
    
    # 5. 底部曝光标尺
    meter_text = "3...2...1... [ ] ...1...2...3"
    t_size = cv2.getTextSize(meter_text, font, 0.7, 2)[0]
    tx = (width - t_size[0]) // 2
    cv2.putText(overlay, meter_text, (tx, height - margin - 15), font, 0.7, white, 2, cv2.LINE_AA)
    
    return overlay


def apply_viewfinder_to_frame(frame: np.ndarray, overlay: np.ndarray) -> np.ndarray:
    """对单帧画面叠加取景框 HUD 图层。"""
    if frame.shape[:2] != overlay.shape[:2]:
        frame = cv2.resize(frame, (overlay.shape[1], overlay.shape[0]))
    
    alpha = overlay[:, :, 3] / 255.0
    out = frame.copy()
    for c in range(3):
        out[:, :, c] = ((1.0 - alpha) * frame[:, :, c] + alpha * overlay[:, :, c]).astype(np.uint8)
    return out
