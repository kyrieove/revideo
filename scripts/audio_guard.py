"""revideo 通用工具：短切片音频安全阀与视听解耦。
杜绝快切蒙太奇中短切片运行 atempo 导致的 WSOLA 颗粒破碎杂音，以及画面反转时的怪异倒吸气音效。
"""
import json
import math
import subprocess


def safe_audio_slice(src_mp4, start_t, duration, speed=1.0, is_reverse=False,
                     volume_db=0.0, out_wav=None, min_stretch_dur=0.233):
    """安全生成音频切片。
    
    参数:
      src_mp4: 源音频/视频文件路径
      start_t: 起始时间戳 (秒)
      duration: 切片目标时长 (秒)
      speed: 目标播放速度 (倍率)
      is_reverse: 画面是否倒放；若为 True 且未显式指定反转音频，则输出静音防杂音
      volume_db: 音量增益 (dB)
      out_wav: 输出 WAV 路径
      min_stretch_dur: 允许执行 atempo 时间拉伸的最短时长门限 (秒，默认 0.233 秒即 7 帧)，低于该门限禁止慢放拉伸
    """
    if out_wav is None:
        raise ValueError('必须指定 out_wav 输出路径')
    if (not all(math.isfinite(v) for v in (duration, speed, start_t, volume_db, min_stretch_dur))
            or duration <= 0 or speed <= 0 or start_t < 0 or min_stretch_dur < 0):
        raise ValueError('duration、speed 必须有限且为正；start_t 和 min_stretch_dur 必须有限且非负')

    # 1. 倒放镜头默认不倒放原声（避免吸气倒放怪音，直接生成静音垫轨）
    if is_reverse:
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.4f}", out_wav], check=True)
        return out_wav

    # 2. 超短切片（例如 <= 7 帧，0.233 秒）若做慢速拉伸 (speed < 1.0)，禁止使用 atempo
    if duration <= min_stretch_dur and speed < 1.0:
        # 直接输出静音填充，防止 WSOLA 颗粒严重破碎失真
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-f", "lavfi",
                        "-i", "anullsrc=r=48000:cl=stereo", "-t", f"{duration:.4f}", out_wav], check=True)
        return out_wav

    # 缺失源音频不能由 apad 静默掩盖；只允许滤镜自身的边界补齐。
    info = json.loads(subprocess.check_output([
        'ffprobe', '-v', 'error', '-select_streams', 'a:0',
        '-show_entries', 'stream=duration:format=duration', '-of', 'json', src_mp4]))
    if not info.get('streams'):
        raise ValueError('源文件没有音轨')
    available = float(info['streams'][0].get('duration', info.get('format', {}).get('duration', 'nan')))
    if not math.isfinite(available) or start_t + duration * speed > available + 0.001:
        raise ValueError(f'源音频不足：需到 {start_t + duration * speed:.4f} 秒，源长 {available:.4f} 秒')
    # 3. 正常时长切片执行标准处理
    tempo_filters = []
    if speed != 1.0:
        curr = speed
        while curr < 0.5:
            tempo_filters.append("atempo=0.5")
            curr /= 0.5
        while curr > 2.0:
            tempo_filters.append('atempo=2.0')
            curr /= 2.0
        tempo_filters.append(f"atempo={curr:.8g}")

    af_parts = ["asetpts=PTS-STARTPTS"]
    if tempo_filters:
        af_parts.extend(tempo_filters)
    af_parts.extend(["apad", f"atrim=duration={duration:.4f}"])
    if volume_db != 0.0:
        af_parts.append(f"volume={volume_db:+.1f}dB")

    # 微淡入淡出（各 20ms）消除拼接边界直流跳变和点击音 (pop/click)
    fade_d = min(0.02, duration / 4.0)
    if fade_d > 0.005:
        af_parts.append(f"afade=t=in:st=0:d={fade_d:.4f}")
        af_parts.append(f"afade=t=out:st={duration - fade_d:.4f}:d={fade_d:.4f}")

    af_str = ",".join(af_parts)
    common = ["ffmpeg", "-v", "error", "-y", "-ss", f"{start_t:.4f}", "-t", f"{duration * speed + 0.1:.4f}", "-i", src_mp4]
    subprocess.run(common + ["-vn", "-af", af_str, "-ar", "48000", "-ac", "2", out_wav], check=True)
    return out_wav
