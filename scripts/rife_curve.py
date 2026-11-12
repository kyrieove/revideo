"""revideo 通用工具：按时间戳曲线抽帧与 RIFE 插帧。
支持任意动作时间映射，避免非整数倍变速产生的停帧，单镜头内 120fps 毫秒级锁定采样。
"""
import glob
import math
import os
import shutil
import subprocess

DEFAULT_ENGINE = os.environ.get("RIFE_ENGINE", "rife-ncnn-vulkan")


def sample_curve(src_mp4, sample_times, n_frames, crop=None, tmp_dir=None, fps=30, engine=DEFAULT_ENGINE):
    """根据给定的目标时间戳序列 sample_times，通过 RIFE 120fps 补帧后提取 n_frames 帧。
    
    参数:
      src_mp4: 源视频路径 (必须是 ffmpeg 可读取的格式)
      sample_times: 长度为 n_frames 的浮点数列表，表示输出每一帧对应源视频的绝对时刻 (秒)
      n_frames: 输出总帧数，必须与 len(sample_times) 一致
      crop: ffmpeg 裁切滤镜字符串，如 "crop=1280:720:384:324"
      tmp_dir: 临时缓存目录；若为 None 则在系统临时目录创建
      fps: 成片帧率，默认 30
      engine: rife-ncnn-vulkan 所在根目录
      
    返回:
      final_dir: 包含生成的 00000001.png 到 %08d.png 的最终帧目录
    """
    assert len(sample_times) == n_frames, f"sample_times 长度 ({len(sample_times)}) 与 n_frames ({n_frames}) 不符"
    if tmp_dir is None:
        import tempfile
        tmp_dir = tempfile.mkdtemp(prefix="revideo_rife_")

    inputs = os.path.join(tmp_dir, "input")
    outputs = os.path.join(tmp_dir, "output")
    final_dir = os.path.join(tmp_dir, "final")
    os.makedirs(inputs, exist_ok=True)
    os.makedirs(outputs, exist_ok=True)
    os.makedirs(final_dir, exist_ok=True)

    # 边界预留 2 帧 margin 保证插帧边缘稳定
    t_min = min(sample_times) - 2 / 60.0
    t_max = max(sample_times) + 2 / 60.0
    duration = t_max - t_min
    count = int(math.ceil(duration * 60)) + 1

    vf_chain = []
    if crop:
        vf_chain.append(crop)
    vf_chain.append("fps=60")
    vf_str = ",".join(vf_chain)

    # 1. 抽取 60fps 连续源帧
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t_min:.4f}", "-i", src_mp4,
                    "-frames:v", str(count), "-vf", vf_str, os.path.join(inputs, "%08d.png")], check=True)
    actual_count = len(glob.glob(os.path.join(inputs, "*.png")))
    assert actual_count == count, f"抽取源帧数量不符: 预期 {count} 帧，实得 {actual_count} 帧"

    # 2. 调用 RIFE 补至 120fps (2倍插帧)
    exe = os.path.join(engine, "rife-ncnn-vulkan.exe")
    model = os.path.join(engine, "rife-v4.6")
    result = subprocess.run([exe, "-i", inputs, "-o", outputs, "-m", model, "-n", str(count * 2)],
                            capture_output=True, text=True)
    assert result.returncode == 0, f"RIFE 运行失败: {result.stderr[-2000:]}"
    rife_frames = sorted(glob.glob(os.path.join(outputs, "*.png")))
    assert len(rife_frames) == count * 2, f"RIFE 输出帧数不符: {len(rife_frames)} vs {count * 2}"

    # 3. 毫秒级锁定采样到 final 序列
    for idx, t_req in enumerate(sample_times):
        frame_idx = int(round((t_req - t_min) * 120.0))
        frame_idx = max(0, min(frame_idx, len(rife_frames) - 1))
        src_png = rife_frames[frame_idx]
        dst_png = os.path.join(final_dir, f"{idx + 1:08d}.png")
        shutil.copyfile(src_png, dst_png)

    assert len(glob.glob(os.path.join(final_dir, "*.png"))) == n_frames
    return final_dir
