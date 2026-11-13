"""审查修复的回归：滤镜注入、HTML 转义、指纹绕过、索引原子写入。"""
import json
import math
import os
import tempfile
import unittest
from pathlib import Path

from scripts.remake import audio_duration, parse_size, parse_trans
from scripts.smart_schema import fingerprint_render_plan, validate_decisions
from scripts.storyboard import generate_storyboard_html


class TestRemakeInjection(unittest.TestCase):
    def test_parse_trans_accepts_plain_names(self):
        self.assertEqual(parse_trans('wipeleft:4'), ('wipeleft', 4))
        self.assertEqual(parse_trans({'type': 'fade', 'frames': 3}), ('fade', 3))
        self.assertEqual(parse_trans('cut'), (None, 0))

    def test_parse_trans_rejects_filter_syntax(self):
        for bad in ('fade[a];movie=/etc/passwd,drawtext=textfile=x:6', {'type': 'fade,scale=1:1', 'frames': 6}):
            with self.assertRaises(ValueError):
                parse_trans(bad)

    def test_parse_size_rejects_non_integers(self):
        self.assertEqual(parse_size([1280, 720]), [1280, 720])
        for bad in (['1280', 720], [1280], [0, 720], '1280x720', [1280.5, 720]):
            with self.assertRaises(ValueError):
                parse_size(bad)

    def test_audio_duration_falls_back_to_container(self):
        self.assertEqual(audio_duration({}, {'duration': '2.5'}), 2.5)
        self.assertEqual(audio_duration({'duration': '1.0'}, {'duration': '2.5'}), 1.0)
        self.assertTrue(math.isnan(audio_duration({}, {})))


class TestStoryboardEscaping(unittest.TestCase):
    def test_escapes_fields_and_tolerates_null_material(self):
        xss = '<script>alert(1)</script>'
        ev = {'fps': 30, 'frames': 30, 'shots': [{
            'id': xss, 'start': 0, 'end': 30, 'material': None,
            'candidates': [{'path': 'a.mp4', 'in_sec': 1.0, 'score': xss, 'framing': xss, 'motion': xss}],
        }]}
        with tempfile.TemporaryDirectory() as d:
            src, out = Path(d) / 'events.json', Path(d) / 'sb.html'
            src.write_text(json.dumps(ev), encoding='utf-8')
            generate_storyboard_html(str(src), str(out))
            text = out.read_text(encoding='utf-8')
        self.assertNotIn('<script>alert', text)
        self.assertIn('a.mp4', text)
        self.assertIn('未选定', text)


class TestFingerprintBypass(unittest.TestCase):
    def _docs(self, asset, with_fp):
        cand = {'candidate_id': 'c1', 'path': str(asset)}
        if with_fp:
            from scripts.material_index import compute_source_fingerprint
            cand['source_fingerprint'] = compute_source_fingerprint(str(asset))
        events = {'frames': 30, 'shots': [{'id': 1, 'start': 0, 'end': 30}]}
        cands = {'slots': [{'shot_id': 1, 'candidates': [cand]}]}
        decisions = {
            'schema_version': 1,
            'candidates_sha256': fingerprint_render_plan(cands),
            'source_events_sha256': fingerprint_render_plan(events),
            'decisions': [{'shot_id': 1, 'confirmed': True, 'selected_candidate_id': 'c1'}],
        }
        return decisions, cands, events

    def test_missing_fingerprint_is_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            asset = Path(d) / 'a.mp4'
            asset.write_bytes(b'x' * 1024)
            validate_decisions(*self._docs(asset, True))
            with self.assertRaises(ValueError):
                validate_decisions(*self._docs(asset, False))


class TestIndexAtomicWrite(unittest.TestCase):
    def test_no_tmp_left_after_build(self):
        from scripts.material_index import build_index
        with tempfile.TemporaryDirectory() as d:
            idx = os.path.join(d, 'index.json')
            build_index([], idx)
            self.assertTrue(os.path.isfile(idx))
            self.assertEqual([f for f in os.listdir(d) if f.endswith('.tmp')], [])


if __name__ == '__main__':
    unittest.main()
