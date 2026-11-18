# -*- coding: utf-8 -*-
"""Audited configuration patch: make the G1/G2a/G2b/G3 XYZ chain 20-height safe.

Every edit is an **exact-match** replacement (occurrence count asserted); a
re-run after a successful apply detects "already applied" and skips instead of
failing.  Nothing geometric changes -- R15, the 50 um true-3D clearance, the
strict D56 crossing index, the glass envelope and the 1024/368 connection
contract are untouched.

Patch list (audit: experiments/COLD_START_20_HEIGHT_1024/00_audit/g123.md)
--------------------------------------------------------------------------
1. ``xyzrouter/optimizer.py`` -- checkpoint scoping (audit 2.4 / 9.7).
   The frozen code writes every stage's checkpoint into the one global
   ``paths.DIRS['checkpoints']`` directory; in the 21-height campaign G1 and
   the concurrently running G3_cold overwrote each other's checkpoints.
   A checkpoint must never escape its own stage: the root now defaults to
   ``<stage out_dir>/checkpoints`` (an explicit ``checkpoint_dir`` still wins).
2. ``xyzrouter/run_g1.py`` -- 2409 literal (audit 4 #5, LOGIC):
   the expected start total is read from the start layout's own
   ``crossing_stats.json`` (state.total stays the recomputed truth) instead of
   the frozen 21-height literal.
3. ``xyzrouter/run_g1.py`` -- fatal validation under the 20-height profile
   (audit 9.8): the frozen runner only logs a validation failure; the 20-height
   chain must stop.  The 21-height log-only behaviour is preserved.
4. ``xyzrouter/run_warmstart_chain.py`` -- bootstrap-first chain (audit 9.1):
   the frozen chain launches every stage as ``python -m <stage>``, which binds
   the frozen 21-height model before ``coldstart20.bootstrap`` can install the
   20-height one.  Under the active 20-height profile the stages are imported
   and called in-process; the 21-height subprocess behaviour is unchanged.
5. ``xyzrouter/run_router_validation.py`` -- 2409 hard gate (audit 4 #6,
   LOGIC): the expected start total comes from the start layout's own
   ``crossing_stats.json`` instead of the frozen literal.
6. ``xyzrouter/run_router_validation.py`` -- the P2 Z-only / XY+Z / comparison
   records compute ``total_before`` and ``removed`` from the frozen 2409
   literal (golden numbers that would silently mis-report a 20-height run);
   they now use the total of the layout each arm actually started from.  The
   21-height numbers are bit-identical because its start total is 2409.

Deliberately **not** patched here (REPORT-class 21-height text/labels/golden
numbers; they do not affect execution and are listed in the stage report):
``xyzrouter/report.py`` (2409 table headers and narrative),
``xyzrouter/run_reports.py`` (fair-comparison text/archive default; the 20H
driver passes ``--archive`` explicitly), ``xyzrouter/visualize.py`` (21-panel
suite, ``BASELINE_REFERENCE = 2409.0``; not executed by the G1-G3 chain),
``xyzrouter/optimizer.py`` crossing-definition strings, ``xyzrouter/preflight_audit.py``
(21H provenance tool, replaced by the 20H authority snapshot in the driver) and
``xyzrouter/l7_geometry_audit.py`` (optional 21H provenance).
"""
import py_compile
import sys
from pathlib import Path

PROJECT = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D')
PKG = PROJECT / 'four_side_1024' / 'fanout1024'

PATCHES = []


def patch(name, old, new, marker=None):
    PATCHES.append(dict(name=name, old=old, new=new, marker=marker))


# ===========================================================================
# 1. xyzrouter/optimizer.py -- stage-scoped checkpoints
# ===========================================================================
patch(
    'optimizer.py: stage-scoped checkpoint root (constructor)',
    "    def __init__(self, state, baseline, out_dir, cfg=None, log=None):\n"
    "        self.state = state\n"
    "        self.baseline = baseline\n"
    "        self.out_dir = Path(out_dir)\n"
    "        self.out_dir.mkdir(parents=True, exist_ok=True)\n"
    "        self.cfg = dict(LR.DEFAULT_CFG, **(cfg or {}))\n",
    "    def __init__(self, state, baseline, out_dir, cfg=None, log=None,\n"
    "                 checkpoint_dir=None):\n"
    "        self.state = state\n"
    "        self.baseline = baseline\n"
    "        self.out_dir = Path(out_dir)\n"
    "        self.out_dir.mkdir(parents=True, exist_ok=True)\n"
    "        #: stage-scoped checkpoint root.  The frozen 21-height campaign wrote\n"
    "        #: every stage's checkpoints into the single global\n"
    "        #: ``paths.DIRS['checkpoints']`` directory, so G1 and the concurrent\n"
    "        #: G3_cold corrupted each other (audit g123.md 2.4).  A checkpoint\n"
    "        #: must never escape its own stage: default = <out_dir>/checkpoints;\n"
    "        #: an explicit ``checkpoint_dir`` still wins.\n"
    "        self.checkpoint_dir = (\n"
    "            Path(checkpoint_dir) if checkpoint_dir is not None\n"
    "            else self.out_dir / 'checkpoints')\n"
    "        self.cfg = dict(LR.DEFAULT_CFG, **(cfg or {}))\n")

patch(
    'optimizer.py: save_checkpoint uses the stage-scoped root',
    "    def save_checkpoint(self, name):\n"
    "        directory = P.DIRS['checkpoints'] / name\n"
    "        directory.mkdir(parents=True, exist_ok=True)\n",
    "    def save_checkpoint(self, name):\n"
    "        # stage-scoped: never the shared ``paths.DIRS['checkpoints']``\n"
    "        # (defect 2.4 of the frozen campaign); see __init__.\n"
    "        directory = Path(self.checkpoint_dir) / name\n"
    "        directory.mkdir(parents=True, exist_ok=True)\n")

# ===========================================================================
# 2. xyzrouter/run_g1.py -- import profile_env
# ===========================================================================
patch(
    'run_g1.py: import profile_env',
    "from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402\n"
    "from four_side_1024.fanout1024.xyzrouter import local_reroute as LR  # noqa: E402\n",
    "from four_side_1024.fanout1024.coldstart20 import profile_env as PE  # noqa: E402\n"
    "from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402\n"
    "from four_side_1024.fanout1024.xyzrouter import local_reroute as LR  # noqa: E402\n",
    marker='from four_side_1024.fanout1024.coldstart20 import profile_env as PE')

# ===========================================================================
# 3. xyzrouter/run_g1.py -- expected start total read from the start layout
# ===========================================================================
patch(
    'run_g1.py: expected start crossings read from the start layout',
    "def load_state(baseline_dir=None, log=log):\n"
    "    baseline = P.load_baseline(baseline_dir)\n",
    "def authority_crossings(baseline_dir):\n"
    '    """Stored crossing total of the start layout (never a 21-height literal).\n'
    "\n"
    "    ``state.total`` is the recomputed truth; the start directory's own\n"
    "    ``crossing_stats.json`` is the expected (authority) value.  Returns\n"
    "    ``None`` when the start directory has no statistics, in which case the\n"
    "    recomputed total is logged as the truth.\n"
    '    """\n'
    "    stats_path = Path(baseline_dir) / 'crossing_stats.json'\n"
    "    try:\n"
    "        payload = json.loads(stats_path.read_text(encoding='utf-8'))\n"
    "    except (OSError, ValueError):\n"
    "        return None\n"
    "    value = (payload.get('totals') or {}).get('crossings')\n"
    "    return None if value is None else int(value)\n"
    "\n"
    "\n"
    "def load_state(baseline_dir=None, log=log):\n"
    "    baseline = P.load_baseline(baseline_dir)\n",
    marker='def authority_crossings(baseline_dir):')

patch(
    'run_g1.py: 2409 warning -> real start total',
    "    if int(state.total) != 2409:\n"
    "        log('[g1] WARNING: baseline crossings=%d (expected 2409)' % state.total)\n",
    "    expected = authority_crossings(baseline['dir'])\n"
    "    if expected is not None and int(state.total) != int(expected):\n"
    "        log('[g1] WARNING: recomputed baseline crossings=%d != authority '\n"
    "            'crossing_stats %d' % (state.total, expected))\n"
    "    else:\n"
    "        log('[g1] baseline crossings=%d (authority start state)' % state.total)\n")

# ===========================================================================
# 4. xyzrouter/run_g1.py -- validation failure fatal under the 20H profile
# ===========================================================================
patch(
    'run_g1.py: 20H validation failure is fatal',
    "            log('[g1] validation_pass=%s violations=%s' % (\n"
    "                report.get('validation_pass'), report.get('violation_count')))\n"
    "        except Exception as error:  # noqa: BLE001\n"
    "            log('[g1] validation unavailable/failed: %s' % error)\n",
    "            log('[g1] validation_pass=%s violations=%s' % (\n"
    "                report.get('validation_pass'), report.get('violation_count')))\n"
    "            if not report.get('validation_pass') and PE.is_20h():\n"
    "                raise RuntimeError(\n"
    "                    '[g1] 20-height driver: independent validation FAILED '\n"
    "                    '(violations=%s, kinds=%s)'\n"
    "                    % (report.get('violation_count'),\n"
    "                       json.dumps(report.get('violation_counts_by_check')\n"
    "                                  or {})))\n"
    "        except Exception as error:  # noqa: BLE001\n"
    "            if PE.is_20h():\n"
    "                # the 20-height chain must stop on a failed validation\n"
    "                raise\n"
    "            log('[g1] validation unavailable/failed: %s' % error)\n")

# ===========================================================================
# 5. xyzrouter/run_warmstart_chain.py -- in-process stages under the 20H profile
# ===========================================================================
patch(
    'run_warmstart_chain.py: bootstrap-first in-process stages under 20H',
    "def run_module(module, args):\n"
    "    command = [PY, '-m', module] + list(args)\n"
    "    log('RUN ' + ' '.join(command))\n"
    "    started = time.time()\n"
    "    result = subprocess.run(command, cwd=str(ROOT))\n"
    "    seconds = time.time() - started\n"
    "    log('DONE %s rc=%s (%.1f min)' % (module, result.returncode, seconds / 60.0))\n"
    "    return result.returncode, seconds\n",
    "def run_module(module, args):\n"
    '    """Run one chain stage, bootstrap-first under the 20-height profile.\n'
    "\n"
    "    ``python -m <stage>`` imports the frozen 21-height model before\n"
    "    ``coldstart20.bootstrap`` can install the 20-height one, so under the\n"
    "    active 20-height profile the stage module is imported and called\n"
    "    in-process.  The frozen 21-height subprocess behaviour is unchanged.\n"
    '    """\n'
    "    from four_side_1024.fanout1024.coldstart20 import profile_env as PE\n"
    "    started = time.time()\n"
    "    if PE.is_20h():\n"
    "        import importlib\n"
    "        argv = [str(value) for value in args]\n"
    "        log('IN-PROCESS %s %s' % (module, ' '.join(argv)))\n"
    "        stage = importlib.import_module(module)\n"
    "        returncode = int(stage.main(argv) or 0)\n"
    "        seconds = time.time() - started\n"
    "        log('DONE %s rc=%s (%.1f min)'\n"
    "            % (module, returncode, seconds / 60.0))\n"
    "        return returncode, seconds\n"
    "    command = [PY, '-m', module] + list(args)\n"
    "    log('RUN ' + ' '.join(command))\n"
    "    result = subprocess.run(command, cwd=str(ROOT))\n"
    "    seconds = time.time() - started\n"
    "    log('DONE %s rc=%s (%.1f min)' % (module, result.returncode, seconds / 60.0))\n"
    "    return result.returncode, seconds\n")

# ===========================================================================
# 6. xyzrouter/run_router_validation.py -- start-total helper
# ===========================================================================
patch(
    'run_router_validation.py: stored start-total helper',
    "def now():\n"
    "    return time.strftime('%Y-%m-%dT%H:%M:%S')\n"
    "\n"
    "\n"
    "# ---------------------------------------------------------------------------\n"
    "# geometry helpers (real parts only)\n",
    "def now():\n"
    "    return time.strftime('%Y-%m-%dT%H:%M:%S')\n"
    "\n"
    "\n"
    "def stored_baseline_crossings(baseline_dir):\n"
    '    """Crossing total stored in the start layout (never a 21-height literal).\n'
    "\n"
    "    The authoritative start state's own ``crossing_stats.json`` supplies the\n"
    "    expected value; ``None`` means the start directory has no statistics and\n"
    "    the recomputed baseline total is the truth.\n"
    '    """\n'
    "    path = Path(baseline_dir) / 'crossing_stats.json'\n"
    "    try:\n"
    "        payload = json.loads(path.read_text(encoding='utf-8'))\n"
    "    except (OSError, ValueError):\n"
    "        return None\n"
    "    value = (payload.get('totals') or {}).get('crossings')\n"
    "    return None if value is None else int(value)\n"
    "\n"
    "\n"
    "# ---------------------------------------------------------------------------\n"
    "# geometry helpers (real parts only)\n")

# ===========================================================================
# 7. xyzrouter/run_router_validation.py -- 2409 hard gate
# ===========================================================================
patch(
    'run_router_validation.py: 2409 gate -> authoritative start total',
    "    baseline, state = E.load_state(None, log=log)\n"
    "    baseline_crossings = int(state.total)\n"
    "    if baseline_crossings != 2409:\n"
    "        raise RuntimeError('baseline crossings %d != authoritative 2409'\n"
    "                           % baseline_crossings)\n",
    "    baseline, state = E.load_state(None, log=log)\n"
    "    baseline_crossings = int(state.total)\n"
    "    expected_crossings = stored_baseline_crossings(baseline['dir'])\n"
    "    if (expected_crossings is not None\n"
    "            and baseline_crossings != int(expected_crossings)):\n"
    "        raise RuntimeError(\n"
    "            'baseline crossings %d != authoritative start total %d'\n"
    "            % (baseline_crossings, expected_crossings))\n")

# ===========================================================================
# 8. xyzrouter/run_router_validation.py -- P2 arms start from the real total
# ===========================================================================
patch(
    'run_router_validation.py: P2 z-only arm start total',
    "def run_p2_z_only(state, selection):\n"
    '    """Strategy A: only physical height may change; XY body path is untouched."""\n'
    "    started = time.time()\n"
    "    route_reports = []\n",
    "def run_p2_z_only(state, selection):\n"
    '    """Strategy A: only physical height may change; XY body path is untouched."""\n'
    "    started = time.time()\n"
    "    start_total = int(state.total)\n"
    "    route_reports = []\n")

patch(
    'run_router_validation.py: P2 z-only arm totals',
    "        per_route=route_reports,\n"
    "        total_before=2409,\n"
    "        total_after=int(state.total),\n"
    "        removed=2409 - int(state.total),\n"
    "        budget=dict(max_evals_per_route=P2_MAX_EVAL_PER_ROUTE,\n",
    "        per_route=route_reports,\n"
    "        total_before=start_total,\n"
    "        total_after=int(state.total),\n"
    "        removed=start_total - int(state.total),\n"
    "        budget=dict(max_evals_per_route=P2_MAX_EVAL_PER_ROUTE,\n")

patch(
    'run_router_validation.py: P2 XY+Z arm start total',
    "def run_p2_xy_z(state, selection):\n"
    '    """Strategy B: full XY+Z engine freedom (``local_reroute.reroute_one``)."""\n'
    "    started = time.time()\n"
    "    route_reports = []\n",
    "def run_p2_xy_z(state, selection):\n"
    '    """Strategy B: full XY+Z engine freedom (``local_reroute.reroute_one``)."""\n'
    "    started = time.time()\n"
    "    start_total = int(state.total)\n"
    "    route_reports = []\n")

patch(
    'run_router_validation.py: P2 XY+Z arm totals',
    "        per_route=route_reports,\n"
    "        total_before=2409,\n"
    "        total_after=int(state.total),\n"
    "        removed=2409 - int(state.total),\n"
    "        budget=dict(cfg={key: value for key, value in ENGINE_CFG.items()\n",
    "        per_route=route_reports,\n"
    "        total_before=start_total,\n"
    "        total_after=int(state.total),\n"
    "        removed=start_total - int(state.total),\n"
    "        budget=dict(cfg={key: value for key, value in ENGINE_CFG.items()\n")

patch(
    'run_router_validation.py: P2 comparison start total',
    "    baseline_sel, state_sel = E.load_state(None, log=log)\n"
    "    snapshot_sel = crossing_snapshot(state_sel)\n",
    "    baseline_sel, state_sel = E.load_state(None, log=log)\n"
    "    baseline_total = int(state_sel.total)\n"
    "    snapshot_sel = crossing_snapshot(state_sel)\n")

patch(
    'run_router_validation.py: P2 comparison record',
    "    z_only_removed = int(report_a['removed'])\n"
    "    xy_z_removed = int(report_b['removed'])\n"
    "    comparison = dict(\n"
    "        total_before=2409,\n",
    "    z_only_removed = int(report_a['removed'])\n"
    "    xy_z_removed = int(report_b['removed'])\n"
    "    comparison = dict(\n"
    "        total_before=baseline_total,\n")


def _normalized_text(path):
    """Read a file as text with LF endings + remember its original EOL style."""
    raw = Path(path).read_bytes()
    crlf = raw.count(b'\r\n')
    bare_lf = raw.count(b'\n') - crlf
    eol = '\r\n' if crlf > bare_lf else '\n'
    text = raw.decode('utf-8')
    if eol == '\r\n':
        text = text.replace('\r\n', '\n')
    return text, eol


def _write_text_preserving(path, text, eol):
    """Write text with the file's original EOL style (keeps the diff minimal)."""
    if eol == '\r\n':
        text = text.replace('\n', '\r\n')
    Path(path).write_bytes(text.encode('utf-8'))


def main():
    changed = {}
    failures = []
    skipped = []
    touched = set()
    for item in PATCHES:
        relative = item['name'].split(':')[0]
        path = PKG / 'xyzrouter' / relative
        text, eol = _normalized_text(path)
        old, new = item['old'], item['new']
        marker = item.get('marker')
        if marker is not None:
            occurrences = text.count(marker)
            if occurrences > 1:
                failures.append((item['name'],
                                 'marker %r found %d times (duplicate apply?)'
                                 % (marker, occurrences)))
                print('FAIL %s (duplicate marker)' % item['name'])
                continue
            if occurrences == 1:
                skipped.append(item['name'])
                print('SKIP %s (already applied)' % item['name'])
                continue
        count = text.count(old)
        if count == 0 and text.count(new) >= 1:
            skipped.append(item['name'])
            print('SKIP %s (already applied)' % item['name'])
            continue
        if count != 1:
            failures.append((item['name'], 'found %d occurrences, expected 1'
                             % count))
            print('FAIL %s (found %d, expected 1)' % (item['name'], count))
            continue
        _write_text_preserving(path, text.replace(old, new), eol)
        changed[str(path)] = changed.get(str(path), 0) + 1
        touched.add(path)
        print('OK   %s' % item['name'])
    if failures:
        print('\nFAILURES:')
        for name, reason in failures:
            print('  %s: %s' % (name, reason))
        return 1
    print('\nfiles changed: %s' % {p.name: n for p, n in
                                   ((Path(k), v) for k, v in changed.items())})
    if skipped:
        print('already applied entries skipped: %d' % len(skipped))
    # every patched file must still compile
    for path in sorted(touched):
        py_compile.compile(str(path), doraise=True)
        print('compile OK %s' % path.name)
    return 0


if __name__ == '__main__':
    sys.exit(main())
