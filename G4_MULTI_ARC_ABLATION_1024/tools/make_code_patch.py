# -*- coding: utf-8 -*-
"""Reconstruct the pre-change sources of the two modified files.

The project checkout is not a git working tree, so the ablation needs an exact
reversible record of the code change.  Every edit applied by this experiment is
listed below as a ``(new_text, old_text)`` pair; reversing them rebuilds the
original file byte for byte, which is then diffed against the current file to
produce ``code_changes/g4_multi_arc.patch``.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]

EDITS = {
    'four_side_1024/fanout1024/layer2d.py': [
        (
            'import csv\nimport hashlib\nimport json\nimport math\nimport os\n'
            'import time\nfrom collections import Counter, OrderedDict, defaultdict\n'
            'from pathlib import Path',
            'import csv\nimport hashlib\nimport json\nimport math\n'
            'import time\nfrom collections import Counter, OrderedDict, defaultdict\n'
            'from pathlib import Path',
        ),
        (
            '        self.layer_id = int(layer_id)\n'
            '        self.z_mm = float(z_mm)\n'
            '        self.cfg = dict(DEFAULT_CFG, **(cfg or {}))\n'
            '        self.log = log\n'
            '        #: planar multi-arc policy of this router (see MULTI_ARC_POLICY)\n'
            '        self.enable_multi_arc = multi_arc_enabled(self.cfg)\n'
            '        self._multi_arc_skipped_specs = 0\n'
            '        self._multi_arc_rejected_candidates = 0\n',
            '        self.layer_id = int(layer_id)\n'
            '        self.z_mm = float(z_mm)\n'
            '        self.cfg = dict(DEFAULT_CFG, **(cfg or {}))\n'
            '        self.log = log\n',
        ),
        (
            '        tiers = OrderedDict()\n'
            '        for spec in self._specs(route_id, frame, phase):\n'
            '            if not self.enable_multi_arc and spec_uses_multi_arc(spec):\n'
            '                self._multi_arc_skipped_specs += 1\n'
            '                self.stats[\'multi_arc_skipped_specs\'] = \\\n'
            '                    self._multi_arc_skipped_specs\n'
            '                continue\n'
            '            tier = _family_tier(spec[\'family\'])\n',
            '        tiers = OrderedDict()\n'
            '        for spec in self._specs(route_id, frame, phase):\n'
            '            tier = _family_tier(spec[\'family\'])\n',
        ),
        (
            '                    if reason is not None:\n'
            '                        self._rejection_counts[reason] += 1\n'
            '                        continue\n'
            '                    if not self.enable_multi_arc and local_multi_arc_regions(world):\n'
            '                        # exact geometric gate: never emit a planar chain that\n'
            '                        # combines several arcs inside one local region\n'
            '                        self._multi_arc_rejected_candidates += 1\n'
            '                        self.stats[\'multi_arc_rejected_candidates\'] = \\\n'
            '                            self._multi_arc_rejected_candidates\n'
            '                        self._rejection_counts[\'multi_arc_forbidden\'] += 1\n'
            '                        continue\n'
            '                    signature = _signature(world)\n',
            '                    if reason is not None:\n'
            '                        self._rejection_counts[reason] += 1\n'
            '                        continue\n'
            '                    signature = _signature(world)\n',
        ),
    ],
    'four_side_1024/fanout1024/xyzrouter/local_reroute.py': [
        (
            "    router_cfg = dict(L2.DEFAULT_CFG)\n"
            "    router_cfg['enable_multi_arc'] = L2.multi_arc_enabled(cfg)\n",
            "    router_cfg = dict(L2.DEFAULT_CFG)\n",
        ),
    ],
}

#: the big policy block is handled separately (it is a pure insertion)
POLICY_ANCHOR = "def _rounded(value, digits=6):\n    out = round(float(value), digits)\n    return 0.0 if out == 0.0 else out\n\n\n"
POLICY_BLOCK_START = "# ---------------------------------------------------------------------------\n# planar multi-arc policy"


def strip_policy_block(text):
    start = text.index(POLICY_BLOCK_START)
    end = text.index('def _location', start) if 'def _location' in text[start:] else None
    marker = '\n\ndef spec_uses_multi_arc(spec):'
    spec_start = text.index(marker, start)
    tail = text.index('\n\n\n', spec_start)
    return text[:start] + text[tail + 3:]


def main():
    out_dir = Path(__file__).resolve().parents[1] / 'code_changes'
    out_dir.mkdir(parents=True, exist_ok=True)
    patch_chunks = []
    for relative, edits in EDITS.items():
        current = (ROOT / relative).read_text(encoding='utf-8')
        original = current
        for new_text, old_text in edits:
            if new_text not in original:
                raise SystemExit('edit not found in %s:\n%s' % (relative, new_text[:120]))
            original = original.replace(new_text, old_text, 1)
        if relative.endswith('layer2d.py'):
            original = strip_policy_block(original)
        (out_dir / (Path(relative).name + '.orig')).write_text(
            original, encoding='utf-8')
        diff = difflib.unified_diff(
            original.splitlines(keepends=True), current.splitlines(keepends=True),
            fromfile='a/' + relative, tofile='b/' + relative, n=3)
        patch_chunks.append(''.join(diff))
    patch = ''.join(patch_chunks)
    (out_dir / 'g4_multi_arc.patch').write_text(patch, encoding='utf-8')
    added = sum(1 for line in patch.splitlines()
                if line.startswith('+') and not line.startswith('+++'))
    removed = sum(1 for line in patch.splitlines()
                  if line.startswith('-') and not line.startswith('---'))
    print('patch written: %d added / %d removed lines'
          % (added, removed))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
