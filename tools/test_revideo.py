"""Regression probes for the installed revideo scripts. Media fixtures stay temporary."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import numpy as np

ROOT = Path(__file__).resolve().parent.parent / 'scripts'
REPO = Path(__file__).resolve().parent.parent
PROJECT = Path(__file__).resolve().parent.parent
PYTHON = sys.executable
RESULTS = []


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / (name + '.py'))
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run(args):
    return subprocess.run([str(a) for a in args], capture_output=True, text=True,
                          encoding='utf-8', errors='replace', timeout=90)


def record(name, passed, **details):
    RESULTS.append({'probe': name, 'passed': bool(passed), **details})
    print(json.dumps(RESULTS[-1], ensure_ascii=False), flush=True)


def command(name, args, success):
    p = run(args)
    record(name, (p.returncode == 0) == success, exit_code=p.returncode,
           output=(p.stdout + p.stderr)[-1200:])
    return p


with tempfile.TemporaryDirectory(prefix='revideo_regression_') as fixture:
    work = Path(fixture)
    ref, short, long = work / 'ref.mp4', work / 'short.mp4', work / 'long.mp4'
    for path, seconds in ((ref, 2), (long, 3)):
        p = run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', f'color=white:s=64x64:r=30:d={seconds}',
                 '-f', 'lavfi', '-i', f'sine=frequency=440:duration={seconds}',
                 '-c:v', 'libx264', '-c:a', 'aac', '-shortest', path])
        assert p.returncode == 0, p.stderr
    p = run(['ffmpeg', '-v', 'error', '-y', '-i', ref, '-frames:v', 20, '-an', '-c:v', 'libx264', short])
    assert p.returncode == 0, p.stderr
    corrupt = work / 'corrupt.mp4'
    corrupt.write_bytes(b'not a video')
    for check in ('compare', 'ssim'):
        for label, other, success in (('equal', ref, True), ('truncated', short, False),
                                      ('extra_tail', long, False), ('corrupt', corrupt, False)):
            command(f'{check}_{label}', [PYTHON, '-B', '-X', 'utf8', ROOT / 'check.py', check, ref, other], success)
    for label, start, n, other, success in (
        ('valid_range', 10, 30, ref, True), ('short_reference', 40, 30, ref, False),
        ('short_output', 0, 30, short, False), ('negative_start', -1, 30, ref, False),
        ('zero_count', 0, 0, ref, False)):
        command('compare_' + label, [PYTHON, '-B', '-X', 'utf8', ROOT / 'check.py', 'compare', ref, other, start, n], success)

    ev = {'fps': 30, 'fps_str': '30/1', 'frames': 60, 'size': [64, 64], 'ref': 'ref.mp4',
          'music': {'song': None, 'song_offset': None},
          'shots': [{'id': 1, 'start': 0, 'end': 60, 'material': 'ref.mp4', 'role': 'test'}], 'events': []}
    event_path, rendered = work / 'events.json', work / 'rendered.mp4'

    def render(name, data, success=True, extra=()):
        event_path.write_text(json.dumps(data), encoding='utf-8')
        return command(name, [PYTHON, '-B', '-X', 'utf8', ROOT / 'remake.py', event_path, rendered, *extra], success)

    render('default_remake_audio', ev)
    streams = json.loads(run(['ffprobe', '-v', 'error', '-count_frames', '-show_streams', '-of', 'json', rendered]).stdout)['streams']
    record('render_measured_streams', any(s['codec_type'] == 'audio' for s in streams)
           and next(s['nb_read_frames'] for s in streams if s['codec_type'] == 'video') == '60')
    for label, shots in (
        ('inconsistent', [{'id': 1, 'start': 0, 'end': 30, 'material': 'ref.mp4'}]),
        ('gap', [{'id': 1, 'start': 0, 'end': 20, 'material': 'ref.mp4'}, {'id': 2, 'start': 30, 'end': 60, 'material': 'ref.mp4'}]),
        ('overlap', [{'id': 1, 'start': 0, 'end': 40, 'material': 'ref.mp4'}, {'id': 2, 'start': 30, 'end': 60, 'material': 'ref.mp4'}]),
        ('duplicate_id', [{'id': 1, 'start': 0, 'end': 30, 'material': 'ref.mp4'}, {'id': 1, 'start': 30, 'end': 60, 'material': 'ref.mp4'}]),
        ('empty', []), ('negative_length', [{'id': 1, 'start': 0, 'end': -1, 'material': 'ref.mp4'}])):
        render('timeline_' + label, {**ev, 'shots': shots}, False)
    render('timeline_fps_mismatch', {**ev, 'fps_str': '60/1'}, False)
    render('missing_audio', {**ev, 'ref': 'short.mp4'}, False)
    render('explicit_music_missing', ev, False, ('--music', str(work / 'missing.wav')))
    song_ev = {**ev, 'music': {'song': 'long.mp4', 'song_offset': 1}}
    render('song_offset', song_ev)
    render('explicit_offset_overrides', song_ev, True, ('--offset', '0'))
    render('explicit_music_ignores_song_offset', {**ev, 'music': {'song': 'long.mp4', 'song_offset': 100}},
           True, ('--music', str(ref)))
    render('insufficient_audio', song_ev, False, ('--offset', '2'))
    render('short_material', {**ev, 'shots': [{**ev['shots'][0], 'material': 'short.mp4'}]}, False)
    fade = [{**ev['shots'][0], 'end': 30}, {'id': 2, 'start': 30, 'end': 60, 'material': 'ref.mp4', 'transition': 'fade:6'}]
    render('two_shot_fade', {**ev, 'shots': fade})

    audio = load('audio_guard')
    for speed, duration in ((0.5, 1.0), (1.0, 1.0), (2.0, 1.0), (4.0, 0.5)):
        wav = work / 'slice.wav'
        audio.safe_audio_slice(str(ref), 0, duration, speed=speed, out_wav=str(wav))
        raw = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(wav), '-f', 'f32le', '-ac', '1', '-ar', '48000', '-'], capture_output=True, check=True).stdout
        samples = np.frombuffer(raw, np.float32)
        a, b = samples[int(duration * 48000 * .1):int(duration * 48000 * .4)], samples[int(duration * 48000 * .7):int(duration * 48000 * .9)]
        first, last = float(np.sqrt(np.mean(a ** 2))), float(np.sqrt(np.mean(b ** 2)))
        record(f'audio_speed_{speed}', last > first * .5 and abs(len(samples) / 48000 - duration) < .002, first_rms=first, last_rms=last)
    for label, params in (('zero_speed', {'speed': 0}), ('negative_speed', {'speed': -1}), ('nan_speed', {'speed': float('nan')}),
                          ('inf_speed', {'speed': float('inf')}), ('zero_duration', {'duration': 0}),
                          ('short_source', {'speed': 4})):
        try:
            audio.safe_audio_slice(str(ref), 0, out_wav=str(work / 'invalid.wav'), **{'duration': 1, **params})
            passed = False
        except ValueError:
            passed = True
        record('audio_reject_' + label, passed)

    # The same validator provides passing, acceptance-failure and runtime-error modes.
    validator = work / 'validator.py'
    validator.write_text("import sys\nmode=sys.argv[1]\nif mode == 'crash': raise RuntimeError('fixture')\nprint('REJECT_FIXTURE' if mode == 'bad' else 'OK')\nraise SystemExit(1 if mode == 'bad' else 2 if mode == 'usage' else 0)\n", encoding='utf-8')
    base = [PYTHON, '-B', '-X', 'utf8', ROOT / 'check.py', 'negative', '--control-json', json.dumps([PYTHON, str(validator), 'ok']), '--fail-marker', 'REJECT_FIXTURE', '--']
    for mode in ('ok', 'bad', 'crash', 'usage'):
        command('negative_' + mode, [*base, PYTHON, validator, mode], mode == 'bad')
    command('negative_missing_contract', [PYTHON, ROOT / 'check.py', 'negative', PYTHON, '-c', 'raise SystemExit(2)'], False)
    command('negative_missing_executable', [*base, str(work / 'absent.exe')], False)

    av1 = Path('D:/2/dev/yanyun-cut/videos/yanyun-hengdao/raw/Where Winds Meet 2026.10.27 - 23.04.10.04.mp4')
    effects = load('effects')
    frames = list(effects.read_gray(str(av1), 10, 24))
    reference = subprocess.run(['ffmpeg', '-v', 'error', '-i', str(av1), '-vf', 'trim=start_frame=10:end_frame=34', '-fps_mode', 'passthrough', '-pix_fmt', 'gray', '-f', 'rawvideo', '-'], capture_output=True, check=True).stdout
    record('av1_exact_range', len(frames) == 24 and b''.join(f.tobytes() for f in frames) == reference, sample=str(av1), frames=len(frames))
    record('av1_detail', np.isfinite(effects.detail(str(av1), 10, 24)))
    command('av1_dips', [PYTHON, ROOT / 'effects.py', 'dips', av1, 10, 24], True)
    command('av1_compare', [PYTHON, ROOT / 'check.py', 'compare', av1, av1, 0, 24], True)
    av_events = {**ev, 'frames': 24, 'fps': 60, 'fps_str': '60/1', 'shots': [
        {'id': 1, 'start': 0, 'end': 12}, {'id': 2, 'start': 12, 'end': 24}]}
    event_path.write_text(json.dumps(av_events), encoding='utf-8')
    command('av1_energy_decoder', [PYTHON, ROOT / 'check.py', 'energy', event_path, av1, av1, work / 'energy.svg'], True)
    for name in ('effects', 'peaks'):
        command(name + '_selftest', [PYTHON, '-B', '-X', 'utf8', ROOT / (name + '.py'), 'selftest'], True)

report = Path(__file__).resolve().parents[1] / 'out/revideo_audit_probe.json'
report.parent.mkdir(parents=True, exist_ok=True)
report.write_text(json.dumps(RESULTS, ensure_ascii=False, indent=2), encoding='utf-8')
failed = [r['probe'] for r in RESULTS if not r['passed']]
print(f'{len(RESULTS) - len(failed)}/{len(RESULTS)} passed; failed: {failed}')
raise SystemExit(bool(failed))
