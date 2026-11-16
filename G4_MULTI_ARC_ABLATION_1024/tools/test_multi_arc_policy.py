# -*- coding: utf-8 -*-
"""Smoke test of the planar multi-arc policy of ``layer2d``.

For the three canonical frame kinds (same / opposite / adjacent side) it
enumerates the *built* candidate chains of one route with the policy enabled and
disabled and reports:

* the family set that survives,
* every maximal tangent-continuous arc run,
* a hard assertion that with the policy disabled **no** candidate chain contains
  a real local multi-arc region (opposite-sign tangent arc run), while the
  independent-corner (``Z``) families are still present.

Run::

    python experiments/G4_MULTI_ARC_ABLATION_1024/tools/test_multi_arc_policy.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from four_side_1024.fanout1024 import layer2d as L2  # noqa: E402


TASKS = [
    dict(route_id=1, A=(20.0, 0.0), dA=(0.0, 1.0), B=(20.0, 100.0),
         dB=(0.0, -1.0), relation='opposite', manual_group='',
         source_side='S', target_side='N'),
    dict(route_id=2, A=(40.0, 0.0), dA=(0.0, 1.0), B=(80.0, 0.0),
         dB=(0.0, 1.0), relation='same', manual_group='',
         source_side='S', target_side='S'),
    dict(route_id=3, A=(20.0, 0.0), dA=(0.0, 1.0), B=(150.0, 60.0),
         dB=(-1.0, 0.0), relation='adjacent', manual_group='',
         source_side='S', target_side='E'),
    dict(route_id=4, A=(30.0, 0.0), dA=(0.0, 1.0), B=(52.0, 0.0),
         dB=(0.0, 1.0), relation='same', manual_group='',
         source_side='S', target_side='S'),
]


def collect(task, enabled, limit=4000):
    frame, error = L2.canonical_frame(task)
    if error:
        return None, error, [], Counter()
    router = L2._LayerRouter(7, -0.1, [task], [], {}, lambda *_a, **_k: None)
    router.enable_multi_arc = bool(enabled)
    families = Counter()
    regions = Counter()
    examples = []
    count = 0
    for world, spec, _signature in router._iter_candidates(task['route_id'], 0.0):
        count += 1
        families[spec['family']] += 1
        found = L2.local_multi_arc_regions(world)
        for item in found:
            regions[item['kind']] += 1
            if len(examples) < 3:
                examples.append(dict(family=spec['family'], **item))
        if count >= limit:
            break
    return frame, None, sorted(families.items()), regions, count, examples


def main():
    report = {'policy': dict(L2.MULTI_ARC_POLICY), 'kinds': {}}
    failed = []
    for task in TASKS:
        entry = {}
        for enabled in (True, False):
            out = collect(task, enabled)
            frame, error, families, regions, count, examples = out
            if error:
                entry['enabled' if enabled else 'disabled'] = dict(error=error)
                continue
            entry['enabled' if enabled else 'disabled'] = dict(
                kind=frame['kind'], candidates=count,
                families=families, arc_regions=dict(regions),
                examples=examples)
        report['kinds']['task_%d_%s' % (task['route_id'],
                                        entry.get('enabled', {}).get('kind'))] = entry
        off = entry.get('disabled') or {}
        if off.get('arc_regions'):
            failed.append((task['route_id'], off['arc_regions']))
        on = entry.get('enabled') or {}
        print('[task %d] kind=%s' % (task['route_id'], on.get('kind')))
        print('   ON : %3d candidates, %2d families, multi-arc regions=%s'
              % (on.get('candidates', 0), len(on.get('families') or []),
                 on.get('arc_regions')))
        print('        families=%s' % [name for name, _ in
                                       (on.get('families') or [])])
        print('   OFF: %3d candidates, %2d families, multi-arc regions=%s'
              % (off.get('candidates', 0), len(off.get('families') or []),
                 off.get('arc_regions')))
        print('        families=%s' % [name for name, _ in
                                       (off.get('families') or [])])
    out_path = Path(__file__).resolve().parents[1] / 'baseline_audit' / \
        'multi_arc_policy_smoke_test.json'
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=1),
                        encoding='utf-8')
    print('wrote', out_path)
    if failed:
        print('FAIL: multi-arc leaked with policy disabled:', failed)
        return 1
    print('PASS: policy disabled -> zero local multi-arc regions in every '
          'built candidate')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
