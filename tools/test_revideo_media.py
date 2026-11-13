"""strips 与 loudness 的契约（测维护源；需要 ffmpeg，无模型调用）。"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent / 'scripts'
REPO = Path(__file__).resolve().parent.parent
PROJECT = Path(__file__).resolve().parent.parent


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / f'{name}.py')
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


check = load('check')
strips = load('strips')
anchors = load('anchors')
scorecard = load('scorecard')
fx = load('fx/motion_blur') if (ROOT / 'fx/motion_blur.py').is_file() else None


class MediaTests(unittest.TestCase):
    def setUp(self):
        view_dir = tempfile.TemporaryDirectory()
        self.addCleanup(view_dir.cleanup)
        view = Path(view_dir.name) / 'timeline_view.py'
        view.write_text('', encoding='utf-8')
        patcher = mock.patch.object(strips, 'VIEW', view)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_loudness_reports_gain_delta(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            for name, gain in (('a.wav', '0'), ('b.wav', '-6')):
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                                '-af', f'volume={gain}dB', str(d / name)], check=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ok = check.loudness(str(d / 'a.wav'), str(d / 'b.wav'))
            text = out.getvalue()
            self.assertTrue(ok)
            self.assertIn('PASS_LOUDNESS', text)
            delta = float(text.split('ΔI=')[1].split(' LU')[0])
            self.assertAlmostEqual(delta, -6, delta=1.0)

    def test_loudness_fails_without_audio(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'silent.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=0.2',
                            '-c:v', 'libx264', str(p)], check=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ok = check.loudness(str(p), str(p))
            self.assertFalse(ok)
            self.assertIn('FAIL_LOUDNESS', out.getvalue())

    def test_strips_samples_frame_centers(self):
        with tempfile.TemporaryDirectory() as d:
            ev = Path(d) / 'events.json'
            ev.write_text(json.dumps({'fps': 30, 'frames': 40, 'shots': [
                {'id': 1, 'start': 0, 'end': 30}, {'id': 2, 'start': 30, 'end': 40}]}), encoding='utf-8')
            argv = ['strips.py', str(ev), 'ref.mp4', 'out.mp4', str(Path(d) / 'strips'), '--boundaries']
            with mock.patch.object(strips.subprocess, 'run') as run, mock.patch.object(sys, 'argv', argv):
                strips.main()
            calls = [c.args[0] for c in run.call_args_list]
            self.assertEqual(len(calls), 2)
            # 切点 30：采样帧 26..34，取帧起点前 1ms，避免 -ss 落到下一帧
            self.assertEqual(calls[0][6:10], ['0.865', '1.132', '--n-frames', '9'])

    def test_single_frame_shot_stays_inside_frame(self):
        with tempfile.TemporaryDirectory() as d:
            ev = Path(d) / 'events.json'
            ev.write_text(json.dumps({'fps': 30, 'frames': 10, 'shots': [
                {'id': 1, 'start': 0, 'end': 5}, {'id': 2, 'start': 5, 'end': 6}]}), encoding='utf-8')
            argv = ['strips.py', str(ev), 'ref.mp4', 'out.mp4', str(Path(d) / 'strips'), '--shot', '2', '--all']
            with mock.patch.object(strips.subprocess, 'run') as run, mock.patch.object(sys, 'argv', argv):
                strips.main()
            args = run.call_args_list[0].args[0]
            self.assertEqual(args[8:10], ['--n-frames', '1'])
            start, end = float(args[6]), float(args[7])
            self.assertLess((start + end) / 2, 6 / 30)  # 中点仍在第 5 帧内
            self.assertGreaterEqual(start, 5 / 30 - 0.002)

    def test_strips_reports_missing_viewer(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.object(strips, 'VIEW', Path(d) / 'absent.py'), \
                mock.patch.object(sys, 'argv', ['strips.py', 'ev.json', 'r.mp4', 'o.mp4', d]):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
                strips.main()
            self.assertEqual(exit_.exception.code, 1)
            self.assertIn('FAIL_STRIPS', out.getvalue())

    def test_strips_reports_ffmpeg_failure(self):
        with tempfile.TemporaryDirectory() as d:
            ev = Path(d) / 'events.json'
            ev.write_text(json.dumps({'fps': 30, 'frames': 40, 'shots': [
                {'id': 1, 'start': 0, 'end': 30}, {'id': 2, 'start': 30, 'end': 40}]}), encoding='utf-8')
            argv = ['strips.py', str(ev), 'ref.mp4', 'out.mp4', str(Path(d) / 'strips'), '--boundaries']
            with mock.patch.object(strips.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg')), \
                    mock.patch.object(sys, 'argv', argv):
                out = io.StringIO()
                with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as exit_:
                    strips.main()
            self.assertEqual(exit_.exception.code, 1)
            self.assertIn('FAIL_STRIPS 帧条生成失败', out.getvalue())

    def test_loudness_warns_on_over_peak(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            quiet, loud = d / 'quiet.wav', d / 'loud.wav'
            for path, gain in ((quiet, '-20'), (loud, '30')):
                subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i', 'sine=frequency=440:duration=1',
                                '-af', f'volume={gain}dB', str(path)], check=True)
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                ok = check.loudness(str(loud), str(quiet))
            self.assertTrue(ok)
            self.assertIn('WARN_LOUDNESS', out.getvalue())

    def test_anchors_pass_fail_and_missing_phase(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            video = d / 'v.mp4'
            subprocess.run(['ffmpeg', '-v', 'error', '-y', '-f', 'lavfi', '-i',
                            'testsrc2=size=64x64:rate=30:duration=0.7', '-c:v', 'libx264', str(video)], check=True)
            ev = d / 'events.json'

            def run(out_frame):
                ev.write_text(json.dumps({'fps': 30, 'frames': 21, 'shots': [
                    {'id': 1, 'start': 0, 'end': 21,
                     'anchors': [{'phase': '收刀完成', 'ref_frame': 10, 'out_frame': out_frame}]}]}), encoding='utf-8')
                return subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'anchors.py'), str(ev),
                                       str(video), str(video), str(d / 'anchors'), '--max-diff', '2'],
                                      capture_output=True, text=True, encoding='utf-8')

            self.assertEqual(run(10).returncode, 0)
            self.assertTrue((d / 'anchors' / 'shot_001_anchor_1.png').is_file())
            self.assertEqual(run(13).returncode, 1)
            self.assertIn('差 +3 帧 > 2', run(13).stdout)
            self.assertEqual(run(None).returncode, 1)
            self.assertIn('成片未出现', run(None).stdout)
            for name, anchor in (('bad_phase', {'phase': '', 'ref_frame': 10, 'out_frame': 10}),
                                 ('bad_ref', {'phase': '收刀完成', 'ref_frame': 999, 'out_frame': 10})):
                bad = d / f'{name}.json'
                bad.write_text(json.dumps({'fps': 30, 'frames': 21, 'shots': [
                    {'id': 1, 'start': 0, 'end': 21, 'anchors': [anchor]}]}), encoding='utf-8')
                r = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'anchors.py'), str(bad),
                                    str(video), str(video), str(d / name)], capture_output=True, text=True,
                                   encoding='utf-8')
                self.assertEqual(r.returncode, 1, name)
                self.assertIn('FAIL_ANCHORS', r.stdout, name)
            missing = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'anchors.py'), str(ev),
                                      str(d / 'missing.mp4'), str(video), str(d / 'missing')],
                                     capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(missing.returncode, 1)
            self.assertIn('FAIL_ANCHORS 无法读取视频', missing.stdout)

    def test_scorecard_validates_and_compares_baseline(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            good = {'version': 'v13', 'reviewer': 'editor', 'scores':
                    {'action': 9, 'pacing': 8, 'framing': 8, 'quality': 8, 'audio': 8}, 'p0': [], 'p1': ['F470 手部']}
            (d / 'a.json').write_text(json.dumps(good), encoding='utf-8')
            self.assertTrue(scorecard.main_path(d / 'a.json', None))
            bad = dict(good, scores={'action': 9})
            (d / 'bad.json').write_text(json.dumps(bad), encoding='utf-8')
            self.assertFalse(scorecard.main_path(d / 'bad.json', None))
            low = dict(good, version='v14', scores={k: 6 for k in good['scores']})
            (d / 'low.json').write_text(json.dumps(low), encoding='utf-8')
            self.assertFalse(scorecard.main_path(d / 'low.json', d / 'a.json'))
            same = dict(good, version='v14')
            (d / 'same.json').write_text(json.dumps(same), encoding='utf-8')
            self.assertTrue(scorecard.main_path(d / 'same.json', d / 'a.json'))
            fake = dict(good, p0=['动作错位'])
            (d / 'fake.json').write_text(json.dumps(fake), encoding='utf-8')
            self.assertFalse(scorecard.main_path(d / 'fake.json', None))
            cjk = dict(good, p1=['第470帧 手部'])
            (d / 'cjk.json').write_text(json.dumps(cjk), encoding='utf-8')
            self.assertTrue(scorecard.main_path(d / 'cjk.json', None))

    def test_motion_blur_rejects_overlong_and_softens(self):
        self.assertIsNotNone(fx)
        fx.selftest()
        with self.assertRaises(ValueError):
            fx.validate_length(200)
        r = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'fx/motion_blur.py'),
                            'missing.mp4', 'out.mp4', '--start', '0', '--end', '1', '--length', '9'],
                           capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(r.returncode, 1)
        self.assertIn('FAIL_FX', r.stdout)

    def test_pending_shots(self):
        done = {'status': 'verified'}
        doc = {'shots': [{'id': 1, 'review': {'action': done, 'effects': done}},
                         {'id': 2, 'review': {'action': {'status': 'pending'}}},
                         {'id': 3}]}
        self.assertEqual([s['id'] for s in strips.pending_shots(doc)], [2, 3])
        old = {'shots': [{'id': 1}, {'id': 2}]}
        self.assertEqual([s['id'] for s in strips.pending_shots(old)], [1, 2])

    def test_strips_rejects_unknown_shot_before_reading_media(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            ev = d / 'events.json'
            ev.write_text(json.dumps({'fps': 30, 'frames': 60, 'shots': [
                {'id': 1, 'start': 0, 'end': 60, 'review': {'action': {'status': 'pending'}}}]}), encoding='utf-8')
            r = subprocess.run([sys.executable, '-B', '-X', 'utf8', str(ROOT / 'strips.py'), str(ev),
                                str(d / 'ref.mp4'), str(d / 'out.mp4'), str(d / 'strips'), '--shot', '9'],
                               capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(r.returncode, 1)
            self.assertIn('FAIL_STRIPS', r.stdout)


if __name__ == '__main__':
    unittest.main(verbosity=2)
