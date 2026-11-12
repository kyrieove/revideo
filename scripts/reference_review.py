"""Reference evidence and action/effects review in the existing events.json.

Initialize an existing plan: reference_review.py events.json [--rea breakdown.json].
Check it: check.py review events.json. This checks review completeness, not film quality.
"""
import argparse
import hashlib
import json
import math
from pathlib import Path


KINDS = ('action', 'effects', 'material_relation')
QUESTIONS = {'action': '核对动作阶段及推进顺序',
             'effects': '核对镜头内及段尾局部效果；空图层列表不代表没有效果',
             'material_relation': '说明本镜的素材关系（动作/物件/几何/展示）；只写同人物/同场景不算，意义不明须标出',
             'upstream': '核实上游分歧或不确定判断，说明哪些推断不适用于本次复刻',
             'boundary': '逐帧裁决列出的切点分歧'}


def required_kinds(reference, version=2):
    base = reference.get('base') or {}
    kinds = KINDS if version >= 2 else KINDS[:2]
    return (*kinds, *(('upstream',) if base.get('disputed') or base.get('uncertain') else ()),
            *(('boundary',) if reference.get('cut_disagreement') else ()))


def has_review(doc):
    """True when any per-shot review entry is no longer pending."""
    shots = doc.get('shots') if isinstance(doc, dict) else None
    return any(isinstance(s, dict) and isinstance(s.get('review'), dict)
               and any(isinstance(r, dict) and r.get('status') != 'pending' for r in s['review'].values())
               for s in shots or [])


def head_hash(path):
    with Path(path).open('rb') as f:
        return hashlib.sha256(f.read(64 << 20)).hexdigest()


def timeline(doc):
    shots = doc.get('shots')
    if not isinstance(shots, list) or not shots or type(doc.get('frames')) is not int:
        raise ValueError('事件表必须包含 shots 和整数 frames')
    end, ids = 0, set()
    for shot in shots:
        if (not isinstance(shot, dict) or type(shot.get('id')) is not int
                or shot['id'] in ids or type(shot.get('start')) is not int
                or type(shot.get('end')) is not int or shot['start'] != end
                or shot['end'] <= end):
            raise ValueError('镜头必须具有唯一整数 ID，连续覆盖完整时间线')
        ids.add(shot['id'])
        end = shot['end']
    if end != doc['frames']:
        raise ValueError('镜头未覆盖 frames')
    return shots


def attach(doc, event_dir, rea_path=None):
    """Validate before mutation. Never infer action/effect correctness from a label."""
    shots = timeline(doc)
    if ('reference_review' in doc or any(isinstance(s, dict) and ('review' in s or 'reference' in s)
                                         for s in shots)):
        raise ValueError('已有参考复核记录，拒绝覆盖；请在原记录上修改')
    ref = Path(doc['ref'])
    ref = ref if ref.is_absolute() else Path(event_dir) / ref
    meta = {'version': 2, 'ref_sha256_head': head_hash(ref),
            'fps': doc['fps'], 'frames': doc['frames'], 'size': doc['size']}
    records = [{} for _ in shots]
    report_dir = Path(event_dir)
    if rea_path is not None:
        report = Path(rea_path).resolve()
        report_dir = report.parent
        raw = report.read_bytes()
        data = json.loads(raw)
        schema = data.get('schema')
        if schema not in (None, 'rea_video.breakdown.v1'):
            raise ValueError(f'不支持的 rea-video schema：{schema}')
        records = data.get('shots')
        if not isinstance(records, list) or len(records) != len(shots):
            raise ValueError('rea-video 镜头数量与事件表不一致')
        for rec, shot in zip(records, shots):
            if (not isinstance(rec, dict) or type(rec.get('start_frame')) is not int
                    or rec['start_frame'] != shot['start']
                    or ('end_frame' in rec and (type(rec['end_frame']) is not int
                                               or rec['end_frame'] != shot['end']))):
                raise ValueError('rea-video 镜头边界与事件表不一致')
        source = data.get('source') or {}
        if schema is not None:
            if (not isinstance(source, dict) or not isinstance(source.get('fps'), (int, float))
                    or not math.isclose(source['fps'], doc['fps'], rel_tol=0, abs_tol=1e-6)
                    or [source.get('width'), source.get('height')] != doc['size']
                    or any('end_frame' not in rec for rec in records)):
                raise ValueError('rea-video 缺少或不匹配的帧率、尺寸、结束帧')
            if not source.get('sha256_head'):
                raise ValueError('rea-video 缺少原片指纹，不能证明报告属于当前参考片')
        if source.get('sha256_head') and source['sha256_head'] != meta['ref_sha256_head']:
            raise ValueError('rea-video 报告属于另一份参考片（指纹不匹配）')
        meta['rea'] = {'path': str(report), 'sha256': hashlib.sha256(raw).hexdigest(),
                       'schema': schema, 'tool': data.get('tool'),
                       'legacy_cut_only': schema is None}
    disagreements = set(doc.get('cuts_scenedetect', [])) ^ {s['start'] for s in shots[1:]}
    references = []
    for shot, rec in zip(shots, records):
        evidence = {'start': shot['start'], 'end': shot['end']}
        if 'cuts_scenedetect' in doc:
            evidence['cut_disagreement'] = sorted(f for f in disagreements if shot['start'] <= f < shot['end'])
        if rea_path is not None and not meta['rea']['legacy_cut_only']:
            evidence.update({key: rec[key] for key in
                             ('id', 'base', 'deterministic', 'layers', 'beats') if key in rec})
            evidence['aspects'] = {key: value for key, value in (rec.get('aspects') or {}).items()
                                   if key in ('framing', 'camera', 'lighting', 'grade')}
            evidence['readers'] = {key: {k: v for k, v in (rec.get(key) or {}).items()
                                        if k in ('description', 'evidence', 'label_probs', 'by')}
                                   for key in ('vlm', 'review')}
            evidence['assets'] = {key: str((report_dir / value).resolve())
                                  for key, value in (rec.get('assets') or {}).items() if isinstance(value, str)}
        references.append(evidence)
    doc['reference_review'] = meta
    for shot, evidence in zip(shots, references):
        shot['reference'] = evidence
        shot['review'] = {kind: {'status': 'pending', 'note': '', 'reviewer': '', 'evidence': []}
                          for kind in required_kinds(evidence)}
    return doc


def check(event_path):
    """Fail on missing/stale review; print upstream opinions without endorsing them."""
    path = Path(event_path).resolve()
    try:
        doc = json.loads(path.read_text(encoding='utf-8'))
        shots = timeline(doc)
        meta = doc.get('reference_review')
        if not isinstance(meta, dict) or meta.get('version') not in (1, 2):
            raise ValueError('缺少或不支持 reference_review；先用 reference_review.py 初始化')
        if any(doc.get(key) != meta.get(key) for key in ('fps', 'frames', 'size')):
            raise ValueError('参考时间基准或尺寸已变化，旧复核不能复用')
        ref = Path(doc['ref'])
        ref = ref if ref.is_absolute() else path.parent / ref
        if head_hash(ref) != meta.get('ref_sha256_head'):
            raise ValueError('参考片已变化，旧复核不能复用')
        rea = meta.get('rea')
        records = None
        if rea:
            raw = Path(rea['path']).read_bytes()
            if hashlib.sha256(raw).hexdigest() != rea['sha256']:
                raise ValueError('上游报告已变化，旧复核不能复用')
            if rea.get('legacy_cut_only'):
                print('WARN 旧报告仅导入切点；没有可依赖的逐镜证据')
            else:
                records = {rec.get('start_frame'): rec for rec in json.loads(raw).get('shots') or []
                           if isinstance(rec, dict)}
        if 'cuts_scenedetect' not in doc and doc.get('cuts_from') == 'rea-video':
            raise ValueError('缺少 cuts_scenedetect，无法核对切点分歧；需重新分析')
        disagreements = (set(doc['cuts_scenedetect']) ^ {s['start'] for s in shots[1:]}
                         if 'cuts_scenedetect' in doc else set())
        pending = 0
        for shot in shots:
            prefix = f"shot {shot['id']} [{shot['start']},{shot['end']})"
            reference = shot.get('reference')
            if not isinstance(reference, dict) or (reference.get('start'), reference.get('end')) != (shot['start'], shot['end']):
                raise ValueError(f'{prefix} 参考范围已改变或缺失，需重新核对')
            rec = (records or {}).get(shot['start'])
            if records is not None and rec is None:
                raise ValueError(f'{prefix} 事件表镜头与上游报告不一致，需重新初始化')
            cut_dis = sorted(f for f in disagreements if shot['start'] <= f < shot['end'])
            base = (rec if rec is not None else reference).get('base') or {}
            if base:
                print(f"INFO {prefix} 上游推断（非动作结论）：{base.get('label')} confidence={base.get('confidence')} by={base.get('decided_by')}")
                for key in ('uncertain', 'disputed'):
                    if base.get(key):
                        print(f'WARN {prefix} {key}: {base[key]}')
                for text in base.get('evidence') or []:
                    print(f'INFO 上游依据：{text}')
            for reader, opinion in (reference.get('readers') or {}).items():
                if opinion.get('description'):
                    print(f"INFO {reader} 看图描述（待核实）：{opinion['description']}")
            for layer in reference.get('layers') or []:
                print('INFO 图层候选（非完整效果清单）：' + json.dumps(layer, ensure_ascii=False))
            if cut_dis:
                print(f"WARN {prefix} 切点分歧帧：{cut_dis}")
            kinds = KINDS if meta.get('version', 1) >= 2 else KINDS[:2]
            for kind in (*kinds, *(('upstream',) if base.get('disputed') or base.get('uncertain') else ()),
                         *(('boundary',) if cut_dis else ())):
                review = (shot.get('review') or {}).get(kind)
                valid = False
                if isinstance(review, dict):
                    valid = (review.get('status') in ('verified', 'not_applicable', 'deviation')
                             and all(isinstance(review.get(k), str) and review[k].strip() for k in ('note', 'reviewer')))
                    evidence = review.get('evidence')
                    if valid and isinstance(evidence, list) and evidence:
                        for item in evidence:
                            if not isinstance(item, dict) or not isinstance(item.get('file'), str) or not item['file'].strip():
                                valid = False
                                break
                            file = Path(item['file'])
                            file = file if file.is_absolute() else path.parent / file
                            frame = item.get('frame')
                            if not file.is_file() or type(frame) is not int or not shot['start'] <= frame < shot['end']:
                                valid = False
                                break
                    else:
                        valid = False
                if not valid:
                    pending += 1
                    print(f'FAIL_REFERENCE_REVIEW {prefix} {kind} 未完成：{QUESTIONS[kind]}，附说明、复核者和参考帧证据；不适用也须说明')
        print(f"{'FAIL_REFERENCE_REVIEW' if pending else 'PASS_REFERENCE_REVIEW'} {pending} 项未完成；仅核对参考复核记录完整性，不证明成片动作或效果一致")
        return pending == 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        print(f'FAIL_REFERENCE_REVIEW {exc}')
        return False


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('events', type=Path)
    ap.add_argument('--rea', type=Path)
    o = ap.parse_args()
    try:
        doc = json.loads(o.events.read_text(encoding='utf-8'))
        attach(doc, o.events.resolve().parent, o.rea)
        temp = o.events.with_suffix('.review.tmp')
        temp.write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding='utf-8')
        temp.replace(o.events)
    except (OSError, ValueError, TypeError, KeyError, AttributeError) as exc:
        ap.exit(1, f'FAIL_REFERENCE_REVIEW {exc}\n')
    print('已初始化原事件表；逐镜填写 review.action / review.effects，再运行 check.py review')


if __name__ == '__main__':
    main()
