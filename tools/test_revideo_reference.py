"""Reference-review contracts, real report replay and CLI integration (no model calls)."""
import contextlib
from copy import deepcopy
import importlib.util
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path('D:/2/dev/claude-video/tools/revideo')
PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('reference_review', ROOT / 'reference_review.py')
assert spec is not None and spec.loader is not None
rr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rr)


class ReferenceReviewTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='revideo_reference_')
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.ref = self.work / 'ref.mp4'
        self.ref.write_bytes(b'reference fixture')
        self.event = self.work / 'events.json'
        self.report = self.work / 'breakdown.json'
        self.doc = {'ref': 'ref.mp4', 'fps': 30, 'frames': 60, 'size': [64, 64],
                    'shots': [{'id': 1, 'start': 0, 'end': 30, 'material': 'new.mp4'},
                              {'id': 2, 'start': 30, 'end': 60, 'material': 'other.mp4'}]}
        self.data = {'schema': 'rea_video.breakdown.v1', 'tool': {'version': '0.1.0'},
                     'source': {'fps': 30, 'width': 64, 'height': 64,
                                'sha256_head': rr.head_hash(self.ref)},
                     'shots': [{'id': f'shot_{s["id"]:03}', 'start_frame': s['start'], 'end_frame': s['end'],
                                'base': {'label': 'live_action', 'confidence': .31, 'decided_by': 'deterministic',
                                         'evidence': ['measured texture'], 'disputed': 'reader disagrees'},
                                'layers': [{'kind': 'static_graphic'}],
                                'vlm': {'description': 'turning face'}, 'assets': {'sheet': 'shot.jpg'}}
                               for s in self.doc['shots']]}
        self.save_report()

    def save_report(self):
        self.report.write_text(json.dumps(self.data), encoding='utf-8')

    def attach(self):
        rr.attach(self.doc, self.work, self.report)

    def check(self):
        self.event.write_text(json.dumps(self.doc), encoding='utf-8')
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ok = rr.check(self.event)
        return ok, out.getvalue()

    def close(self):
        for shot in self.doc['shots']:
            for kind in shot['review']:
                shot['review'][kind] = {'status': 'verified', 'reviewer': 'fixture reviewer',
                                        'note': 'Observed reference only, not output acceptance',
                                        'evidence': [{'file': 'ref.mp4', 'frame': shot['start']}]}

    def test_real_fields_survive_without_becoming_render_settings(self):
        before = deepcopy(self.doc['shots'])
        self.attach()
        self.assertEqual(self.doc['shots'][0]['reference']['base'], self.data['shots'][0]['base'])
        self.assertEqual(self.doc['shots'][0]['reference']['layers'], self.data['shots'][0]['layers'])
        self.assertEqual(self.doc['shots'][0]['reference']['readers']['vlm']['description'], 'turning face')
        self.assertTrue(Path(self.doc['shots'][0]['reference']['assets']['sheet']).is_absolute())
        self.assertEqual([{k: s[k] for k in original} for s, original in zip(self.doc['shots'], before)], before)
        ok, output = self.check()
        self.assertFalse(ok)
        self.assertIn('reader disagrees', output)
        self.assertIn('turning face', output)
        self.assertEqual(output.count('未完成：'), 8)  # 2 shots × (action/effects/material_relation + upstream)

    def test_complete_review_and_explicit_not_applicable(self):
        self.attach()
        self.close()
        self.doc['shots'][0]['review']['effects']['status'] = 'not_applicable'
        self.assertTrue(self.check()[0])
        self.doc['shots'][1]['review']['effects']['status'] = 'deviation'
        self.assertTrue(self.check()[0])

    def test_not_applicable_without_evidence_is_not_a_bypass(self):
        self.attach()
        self.close()
        self.doc['shots'][0]['review']['effects'] = {'status': 'not_applicable'}
        self.assertFalse(self.check()[0])

    def test_missing_action_or_effect_is_not_passed(self):
        self.attach()
        self.close()
        for kind in rr.KINDS:
            original = self.doc['shots'][0]['review'].pop(kind)
            self.assertFalse(self.check()[0])
            self.doc['shots'][0]['review'][kind] = original

    def test_bad_closures_rejected(self):
        self.attach()
        self.close()
        target = self.doc['shots'][0]['review']['action']
        for key, value in [('status', 'done'), ('reviewer', ''), ('note', ' '), ('evidence', []),
                           ('evidence', [{'file': 'absent.jpg', 'frame': 0}]),
                           ('evidence', [{'file': 'ref.mp4', 'frame': 30}]),
                           ('evidence', [{'file': 'ref.mp4', 'frame': True}]),
                           ('evidence', [{'file': 'ref.mp4', 'frame': -1}]),
                           ('evidence', [{'file': 'ref.mp4'}])]:
            with self.subTest(key=key, value=value):
                original = target[key]
                target[key] = value
                self.assertFalse(self.check()[0])
                target[key] = original

    def test_unknown_schema_or_mismatched_source_rejected_without_mutation(self):
        for change in ('schema', 'fps', 'width', 'hash', 'end', 'start', 'missing_hash', 'count'):
            with self.subTest(change=change):
                data = deepcopy(self.data)
                if change == 'schema':
                    data['schema'] = 'rea_video.breakdown.v99'
                elif change in ('fps', 'width'):
                    data['source'][change] = 999
                elif change == 'hash':
                    data['source']['sha256_head'] = 'wrong'
                elif change == 'missing_hash':
                    del data['source']['sha256_head']
                elif change == 'end':
                    del data['shots'][0]['end_frame']
                elif change == 'start':
                    data['shots'][1]['start_frame'] = 31
                else:
                    data['shots'].pop()
                self.report.write_text(json.dumps(data), encoding='utf-8')
                before = deepcopy(self.doc)
                with self.assertRaises(ValueError):
                    self.attach()
                self.assertEqual(self.doc, before)

    def test_legacy_start_only_report_is_explicit_and_pending(self):
        self.data = {'shots': [{'start_frame': 0}, {'start_frame': 30}]}
        self.save_report()
        self.attach()
        ok, output = self.check()
        self.assertFalse(ok)
        self.assertIn('旧报告仅导入切点', output)
        self.assertNotIn('base', self.doc['shots'][0]['reference'])

    def test_cut_disagreements_become_required_tasks(self):
        self.doc['cuts_scenedetect'] = [29]
        self.attach()
        self.assertEqual(self.doc['shots'][0]['reference']['cut_disagreement'], [29])
        self.assertEqual(self.doc['shots'][1]['reference']['cut_disagreement'], [30])
        self.close()
        self.assertTrue(self.check()[0])
        del self.doc['shots'][0]['review']['boundary']
        self.assertFalse(self.check()[0])

    def test_without_rea_report_still_requires_content_review(self):
        rr.attach(self.doc, self.work)
        self.assertFalse(self.check()[0])
        self.close()
        self.assertTrue(self.check()[0])

    def test_reinitialization_does_not_destroy_review(self):
        self.attach()
        self.close()
        before = deepcopy(self.doc)
        with self.assertRaises(ValueError):
            self.attach()
        self.assertEqual(self.doc, before)

    def test_stale_report_reference_timing_or_shot_rejected(self):
        self.attach()
        self.close()
        self.assertTrue(self.check()[0])
        for key, value in [('fps', 60), ('size', [1, 1])]:
            original = self.doc[key]
            self.doc[key] = value
            self.assertFalse(self.check()[0])
            self.doc[key] = original
        self.doc['shots'][0]['reference']['end'] = 31
        self.assertFalse(self.check()[0])
        self.doc['shots'][0]['reference']['end'] = 30
        self.ref.write_bytes(b'changed reference')
        self.assertFalse(self.check()[0])
        self.ref.write_bytes(b'reference fixture')
        self.report.write_text('{}', encoding='utf-8')
        self.assertFalse(self.check()[0])

    def test_removing_imported_evidence_does_not_drop_required_tasks(self):
        self.doc['cuts_scenedetect'] = [29]
        self.attach()
        self.close()
        self.assertTrue(self.check()[0])
        for shot in self.doc['shots']:
            shot['reference'].pop('base')
            shot['reference'].pop('cut_disagreement')
            shot['review'].pop('upstream')
            shot['review'].pop('boundary')
        ok, output = self.check()
        self.assertFalse(ok)
        self.assertEqual(output.count('未完成：'), 4)  # 每镜的上游分歧与切点分歧仍从报告/事件表重新推导

    def test_has_review_detects_filled_table(self):
        self.assertFalse(rr.has_review(self.doc))
        self.attach()
        self.assertFalse(rr.has_review(self.doc))  # 全是 pending 时允许重新分析覆盖
        self.doc['shots'][0]['review']['action']['status'] = 'verified'
        self.assertTrue(rr.has_review(self.doc))

    def test_missing_scenedetect_cuts_cannot_drop_boundary_review(self):
        self.doc['cuts_from'] = 'rea-video'
        self.doc['cuts_scenedetect'] = [29]
        self.attach()
        self.close()
        self.assertTrue(self.check()[0])
        del self.doc['cuts_scenedetect']
        self.assertFalse(self.check()[0])

    def test_cli_initialization_and_check(self):
        self.event.write_text(json.dumps(self.doc), encoding='utf-8')
        args = [sys.executable, '-B', '-X', 'utf8']
        init = subprocess.run([*args, str(ROOT / 'reference_review.py'), str(self.event), '--rea', str(self.report)],
                              capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(init.returncode, 0, init.stderr)
        check = subprocess.run([*args, str(ROOT / 'check.py'), 'review', str(self.event)],
                               capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(check.returncode, 1)
        self.assertIn('FAIL_REFERENCE_REVIEW', check.stdout)
        initialized = self.event.read_bytes()
        again = subprocess.run([*args, str(ROOT / 'reference_review.py'), str(self.event)], capture_output=True)
        self.assertEqual(again.returncode, 1)
        self.assertEqual(initialized, self.event.read_bytes())

    def test_real_teto_report_replay(self):
        report = PROJECT / 'videos/_refs/chenying-teto/final/breakdown.json'
        if not report.exists():
            self.skipTest('chenying-teto breakdown not in repo')
        data = json.loads(report.read_text(encoding='utf-8'))
        source = data['source']
        doc = {'ref': source['path'], 'fps': source['fps'], 'frames': data['shots'][-1]['end_frame'],
               'size': [source['width'], source['height']],
               'shots': [{'id': i + 1, 'start': s['start_frame'], 'end': s['end_frame']}
                         for i, s in enumerate(data['shots'])]}
        original = deepcopy(doc['shots'])
        rr.attach(doc, self.work, report)
        self.assertEqual(len(doc['shots']), 18)
        self.assertEqual(sum(len(s['reference'].get('layers', [])) for s in doc['shots']),
                         sum(len(s.get('layers', [])) for s in data['shots']))
        self.assertEqual([(s['start'], s['end']) for s in doc['shots']],
                         [(s['start'], s['end']) for s in original])
        self.doc = doc
        ok, output = self.check()
        self.assertFalse(ok)
        self.assertEqual(output.count('未完成：'), 62)  # 54 action/effects/material_relation + 8 upstream doubts in this saved report
        self.assertEqual(sum('upstream' in s['review'] for s in doc['shots']), 8)


if __name__ == '__main__':
    unittest.main(verbosity=2)
