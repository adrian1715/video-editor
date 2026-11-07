"""Pure planning and validation functions shared by local and agent workflows."""
import copy
import hashlib
import json
import math
import re


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def revision(project):
    return hashlib.sha256(json.dumps(project, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def merge(base, patch, location=()):
    if not isinstance(patch, dict):
        raise ValueError('Patch must be an object')
    result = copy.deepcopy(base)
    for key, value in patch.items():
        optional = location == ('settings',) and key in {'captions','fps','lufs','caption','layout','preserve_audio','preserve_source'}
        if key not in base and not optional and location != ('exports',):
            raise ValueError('Unknown patch field: '+key)
        result[key] = merge(base[key], value, location+(key,)) if isinstance(base.get(key), dict) and isinstance(value, dict) else copy.deepcopy(value)
    return result


def words(source):
    if not isinstance(source,dict) or not isinstance(source.get('transcript',{}),dict):
        raise ValueError('Invalid source/transcript object')
    result = source.get('transcript', {}).get('words', [])
    if not isinstance(result, list):
        raise ValueError('Transcript words must be an array')
    last = -1
    for word in result:
        if not isinstance(word, dict) or not finite(word.get('start')) or not finite(word.get('end')) or not 0 <= word['start'] < word['end'] or word['start'] < last or not isinstance(word.get('text'), str):
            raise ValueError('Invalid or unsorted transcript word')
        last = word['start']
    return [w for w in result if w.get('type', 'word') == 'word' and w['text'].strip()]


def sentences(project):
    candidates = []
    for key, source in project['sources'].items():
        group = []
        for word in words(source):
            group.append(word)
            if re.search(r'[.!?]["\u201d\u2019]*$', word['text'].strip()):
                text = ' '.join(w['text'].strip() for w in group)
                candidates.append({'source': key, 'start': group[0]['start'], 'end': word['end'], 'text': text})
                group = []
        # Do not silently promote an ASR fragment into a complete idea.
    return candidates


def constraints(project, value=None):
    value = value or {'include': [], 'exclude': []}
    if not isinstance(value, dict) or set(value)-{'include', 'exclude'}:
        raise ValueError('Constraints must contain include/exclude arrays')
    for kind in ['include', 'exclude']:
        if not isinstance(value.get(kind, []), list):
            raise ValueError('Constraint ranges must be arrays')
        for r in value.get(kind, []):
            if not isinstance(r, dict) or r.get('source') not in project['sources'] or not finite(r.get('start')) or not finite(r.get('end')) or not 0 <= r['start'] < r['end'] <= float(project['sources'][r['source']]['metadata']['format']['duration']):
                raise ValueError('Invalid constraint range')
    return value


def overlaps(a, b):
    return a['source'] == b['source'] and a['start'] < b['end'] and b['start'] < a['end']


def signature(text):
    return set(re.findall(r'\w+', text.casefold()))


def duplicate(a, b):
    x, y = signature(a), signature(b)
    return bool(x and y and len(x & y)/len(x | y) >= .8)


def local_plan(project, target=60, rules=None):
    if not finite(target) or target <= 0:
        raise ValueError('Target must be positive seconds')
    rules = constraints(project, rules)
    pool = [r for r in sentences(project) if not any(overlaps(r, x) for x in rules.get('exclude', []))]
    if not pool:
        raise ValueError('No complete transcript sentences available; transcribe/correct punctuation or use manual ranges')
    selected, used = [], 0
    # Entire sentences containing required moments win over target duration.
    for required in rules.get('include', []):
        matches = [r for r in pool if overlaps(r, required)]
        if not matches or matches[0]['start'] > required['start'] or matches[-1]['end'] < required['end']:
            raise ValueError('Include cannot be satisfied without an excluded or incomplete sentence')
        for r in matches:
            if r not in selected:
                selected.append(r); used += r['end']-r['start']
    ranked = sorted(enumerate(pool), key=lambda item: (
        -len(set(re.findall(r'\b(?:because|learned|result|problem|solution|lesson|why|porque|aprendi|resultado|problema|solução|lição)\b', item[1]['text'].casefold()))), item[0]))
    for _, r in ranked:
        if r in selected or any(duplicate(r['text'], s['text']) for s in selected):
            continue
        d = r['end']-r['start']
        if used+d <= target or not selected:
            selected.append(r); used += d
    order = list(project['sources'])
    selected.sort(key=lambda r: (order.index(r['source']), r['start']))
    return {'schema_version': 1, 'base_revision': revision(project), 'constraints': rules,
            'ranges': [{**r, 'reason': 'Complete sentence; required moment' if any(overlaps(r,x) for x in rules.get('include',[])) else 'Complete sentence; deterministic relevance/chronology with duplicate filtering'} for r in selected],
            'review_notes': ['Sentence completeness checked mechanically; narrative coherence requires human review.'], 'target': target}


def validate_plan(project, plan):
    if not isinstance(plan, dict) or set(plan)-{'schema_version','base_revision','ranges','constraints','review_notes','target'}:
        raise ValueError('Unknown plan fields; only editing data is accepted')
    if plan.get('base_revision') != revision(project):
        raise ValueError('Stale plan: project changed; regenerate or rebase explicitly')
    if plan.get('schema_version',1) != 1:
        raise ValueError('Unsupported plan schema version')
    ranges = plan.get('ranges')
    if not isinstance(ranges, list) or not ranges:
        raise ValueError('Plan requires nonempty ranges')
    rules = constraints(project, plan.get('constraints'))
    candidates = sentences(project)
    for i, r in enumerate(ranges):
        if not isinstance(r,dict) or set(r)-{'source','start','end','text','reason'} or r.get('source') not in project['sources'] or not finite(r.get('start')) or not finite(r.get('end')):
            raise ValueError('Invalid plan range')
        if not isinstance(r.get('reason'),str) or not r['reason'].strip():
            raise ValueError('Every selection needs a reason')
        # Endpoints must coincide with whole sentence boundaries, themselves word boundaries.
        starts = [s['start'] for s in candidates if s['source']==r['source']]
        ends = [s['end'] for s in candidates if s['source']==r['source']]
        if r['start'] >= r['end'] or not any(abs(r['start']-v)<.001 for v in starts) or not any(abs(r['end']-v)<.001 for v in ends):
            raise ValueError('Plan cuts must follow complete sentence/word boundaries')
        if any(overlaps(r,x) for x in rules.get('exclude',[])) or any(overlaps(r,x) for x in ranges[:i]):
            raise ValueError('Plan contains excluded or overlapping ranges')
    for r in rules.get('include',[]):
        kept = sorted([x for x in ranges if x['source']==r['source']],key=lambda x:x['start'])
        cursor = r['start']
        for x in kept:
            if x['start'] <= cursor < x['end']: cursor=x['end']
        if cursor < r['end']: raise ValueError('Required moment missing from plan')
    return {'valid': True, 'subjective_review_required': True, 'duration': sum(r['end']-r['start'] for r in ranges)}


def semantic_context(project, instructions, target, rules):
    return {'instructions':instructions, 'target':target, 'constraints':rules,
            'sources': {k:{'words':words(v)} for k,v in project['sources'].items()}}
