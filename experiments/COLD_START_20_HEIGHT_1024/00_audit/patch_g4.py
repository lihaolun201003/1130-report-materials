# -*- coding: utf-8 -*-
"""Minimum audited patches for the 20-height **G4** port.

Frozen 21-height behaviour is preserved bit-for-bit: every changed branch either
is profile-driven (identical value when ``coldstart20.bootstrap`` was never
imported) or only fires under the ``COLDSTART20_PROFILE=20_height_raised``
profile.  No geometric threshold, tolerance, acceptance rule or crossing policy
is touched.

Patches
-------
(a) ``xyzrouter/g4/contract_audit.py``
    * the four height-table ``CODE_CITATIONS`` entries are derived from the
      ACTIVE model module (``coldstart20/model20.py`` under the 20H profile,
      ``reheight21/model.py`` without it) and use the real plane counts
      (``len(M.BODY_PLANES)`` / ``len(M.PLANE_IDS)``) instead of the 21-height
      prose literals;
    * the ``heights_21`` logic check becomes ``heights_<plane_count>`` (20 under
      the 20H profile) and still requires ``heights_match_model``;
    * the audit result records the active profile (name / module / plane counts).
(b) ``xyzrouter/g4/independent_metrics.py``
    * the port-interface z expectation uses ``M.interface_z('z1'/'z2')``
      (0.0/0.5 at 21 heights, 0.025/0.525 at 20 heights) instead of 0.0/0.5.
(c) ``xyzrouter/g4/run_g4b.py``
    * ``SCAN_CFG.max_target_layers`` = ``len(M.BODY_PLANES)`` (19 at 21 heights,
      18 at 20 heights) instead of the 21-height literal 19.
(d) ``xyzrouter/g4/paths.py``
    * hard start-point validity guard ``assert_start_profile()`` called from
      ``load_start()``: every flat / layer-sequence / target z, every assignment
      ``target_layer`` / ``target_z_mm`` / ``interface_z_mm`` must be a routing
      height of the ACTIVE model; 1024 routes / 1024 rows / 368 manual-U rows;
      under the 20H profile the imported model must be the 20-plane model with
      identity 19 deleted.  The historical 21-height G3 optimum loaded into a
      20-height process now fails loudly instead of silently running (audit
      §3.3).  ``load_authority()`` is exempt (identity/port authority only);
    * ``AUTHORITY_DIR`` prefers the frozen run authority (unchanged), then the
      frozen archive copy / frozen run copy, so the 20H arms' validator has the
      shared identity/port baseline even before stage 07 exports its own copy
      (audit §3.2).
(e) ``xyzrouter/g4/arm_base.py``
    * ``load_start()`` records the start's *own* crossing total (no longer
      ``GP.START_CROSSINGS``); ``ArmContext.load()`` logs it, sets
      ``state.start_total`` as the authoritative value and stores the actual
      start fingerprint on ``ArmSpec`` so ``config.json`` / ``summary()`` never
      report the global 1322 constant for a different start (audit §3.4).
(f) the G4 arms' independent validation subprocess must import the frozen
    validator *after* the bootstrap: ``artifacts.validator_command()`` launches
    the bootstrap-first G4 driver under the 20H profile (unchanged
    ``python -m ...validate_xyz`` without it).
(g) every 20H snapshot written by ``artifacts.flush`` (arm output, best_valid,
    checkpoints) additionally carries the ACTIVE 20-plane ``layer_planes.json``
    generated from ``model20.layer_planes_payload()`` with the snapshot's real
    per-plane assignment counts.  The frozen validator prefers the run's
    ``layer_planes.json``; without it a 20H run would silently be checked
    against a 21-height layer_planes.json from the authority baseline.  The
    branch is off without the 20H profile.

Run (from the project root, once, after the 21H baseline was archived)::

    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\00_audit\\patch_g4.py
    .venv\\Scripts\\python.exe experiments\\COLD_START_20_HEIGHT_1024\\00_audit\\patch_g4.py --check

The script is idempotent: a patch whose exact pre-image is absent and whose
exact post-image is present once is reported as ``ALREADY APPLIED``; anything
else is a hard failure (no partial file is written).
"""
import argparse
import hashlib
import sys
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
PKG = PROJECT / 'four_side_1024' / 'fanout1024'

PATCHES = []


def patch(file, name, old, new):
    PATCHES.append(dict(file=file, name=name, old=old, new=new))


# ===========================================================================
# (a) contract_audit.py -- profile-driven height-table citations + checks
# ===========================================================================
patch('xyzrouter/g4/contract_audit.py',
      'contract_audit: height-table citations are derived from the active model',
      "    ('four_side_1024/fanout1024/reheight21/model.py', r'^BODY_PLANES = ', '19 body routing heights'),\n"
      "    ('four_side_1024/fanout1024/reheight21/model.py', r'^INTERFACE_PLANES = ', '2 routable interface heights'),\n"
      "    ('four_side_1024/fanout1024/reheight21/model.py', r'^MIN_3D_CLEARANCE_MM\\s*=', '21-height model 50 um 3D clearance'),\n"
      "    ('four_side_1024/fanout1024/reheight21/model.py', r'^MIN_LAYER_PITCH_MM\\s*=', '21-height model 50 um pitch'),\n",
      "    # the four height-table citations below are derived from the ACTIVE\n"
      "    # height profile at call time (``model_code_citations()``):\n"
      "    # ``reheight21/model.py`` without the bootstrap, ``coldstart20/model20.py``\n"
      "    # once the 20-height profile is installed.\n")

patch('xyzrouter/g4/contract_audit.py',
      'contract_audit: active-model citation helpers',
      "    ('four_side_1024/fanout1024/xyzrouter/world_adapter.py', r'^CLEARANCE_MM\\s*=', 'G1/G2/G3 router world clearance 50 um'),\n"
      "    ('four_side_1024/fanout1024/xyzrouter/world_adapter.py', r\"crossing_policy='strict'\", 'router world strict D56 policy'),\n"
      "]\n"
      "\n"
      "\n"
      "# ===========================================================================\n"
      "# helpers\n"
      "# ===========================================================================\n"
      "def read_json(path):\n",
      "    ('four_side_1024/fanout1024/xyzrouter/world_adapter.py', r'^CLEARANCE_MM\\s*=', 'G1/G2/G3 router world clearance 50 um'),\n"
      "    ('four_side_1024/fanout1024/xyzrouter/world_adapter.py', r\"crossing_policy='strict'\", 'router world strict D56 policy'),\n"
      "]\n"
      "\n"
      "\n"
      "def _rel_model_file(model):\n"
      "    try:\n"
      "        return Path(model.__file__).resolve().relative_to(ROOT).as_posix()\n"
      "    except (AttributeError, ValueError):\n"
      "        return None\n"
      "\n"
      "\n"
      "def active_model():\n"
      '    """The height model installed in this process (20H after bootstrap)."""\n'
      "    from four_side_1024.fanout1024.reheight21 import model as M\n"
      "    return M\n"
      "\n"
      "\n"
      "def model_code_citations():\n"
      '    """Plane-table / threshold citations of the ACTIVE model module."""\n'
      "    model = active_model()\n"
      "    relative = _rel_model_file(model)\n"
      "    plane_count = len(model.PLANE_IDS)\n"
      "    return [\n"
      "        (relative, r'^BODY_PLANES = ',\n"
      "         '%d body routing heights' % len(model.BODY_PLANES)),\n"
      "        (relative, r'^INTERFACE_PLANES = ',\n"
      "         '%d routable interface heights' % len(model.INTERFACE_PLANES)),\n"
      "        (relative, r'^MIN_3D_CLEARANCE_MM\\s*=',\n"
      "         '%d-height model 50 um 3D clearance' % plane_count),\n"
      "        (relative, r'^MIN_LAYER_PITCH_MM\\s*=',\n"
      "         '%d-height model 50 um pitch' % plane_count),\n"
      "    ]\n"
      "\n"
      "\n"
      "def code_citations():\n"
      '    """Frozen physics citations + the ACTIVE height-profile citations."""\n'
      "    return list(CODE_CITATIONS) + model_code_citations()\n"
      "\n"
      "\n"
      "# ===========================================================================\n"
      "# helpers\n"
      "# ===========================================================================\n"
      "def read_json(path):\n")

patch('xyzrouter/g4/contract_audit.py',
      'contract_audit: collect_code_evidence uses code_citations()',
      '    for relative, pattern, label in CODE_CITATIONS:\n',
      '    for relative, pattern, label in code_citations():\n')

patch('xyzrouter/g4/contract_audit.py',
      'contract_audit: heights_21 -> heights_<plane_count>',
      "    cross_checks['heights_21'] = (heights['used_height_count'] == 21\n"
      "                                  and heights['heights_match_model'])\n",
      "    _model = active_model()\n"
      "    cross_checks['heights_%d' % len(_model.PLANE_IDS)] = (\n"
      "        heights['used_height_count'] == len(_model.PLANE_IDS)\n"
      "        and heights['heights_match_model'])\n")

patch('xyzrouter/g4/contract_audit.py',
      'contract_audit: record the active height profile in the audit result',
      "    result = dict(\n"
      "        schema='g4_geometry_contract_audit_v1',\n"
      "        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),\n",
      "    result = dict(\n"
      "        schema='g4_geometry_contract_audit_v1',\n"
      "        profile=dict(\n"
      "            name=getattr(_model, 'PROFILE', None),\n"
      "            module=str(getattr(_model, '__name__', '')),\n"
      "            file=_rel_model_file(_model),\n"
      "            plane_count=len(_model.PLANE_IDS),\n"
      "            body_plane_count=len(_model.BODY_PLANES),\n"
      "            interface_z={key: float(value)\n"
      "                         for key, value in _model.INTERFACE_Z.items()}),\n"
      "        generated_at=time.strftime('%Y-%m-%dT%H:%M:%S'),\n")

# ===========================================================================
# (b) independent_metrics.py -- port interface z from the active model
# ===========================================================================
patch('xyzrouter/g4/independent_metrics.py',
      'independent_metrics: active-model helper',
      "EXPECTED_ROUTES_SHA256 = ('711cf910d5c75ea788be877ef88b588fe3d9a90a2ae2d3636bb5b5896834077')\n"
      "\n"
      "\n"
      "# ===========================================================================\n"
      "# small scalar 2-D geometry\n",
      "EXPECTED_ROUTES_SHA256 = ('711cf910d5c75ea788be877ef88b588fe3d9a90a2ae2d3636bb5b5896834077')\n"
      "\n"
      "\n"
      "def _MODEL():\n"
      '    """Active height model (``model20`` after coldstart20.bootstrap)."""\n'
      "    from four_side_1024.fanout1024.reheight21 import model as M\n"
      "    return M\n"
      "\n"
      "\n"
      "# ===========================================================================\n"
      "# small scalar 2-D geometry\n")

patch('xyzrouter/g4/independent_metrics.py',
      'independent_metrics: port z from M.interface_z (0.025/0.525 in 20H)',
      "        z_start = float(first['z_mm'])\n"
      "        z_end = float(last['z_mm'])\n"
      "        want_z = 0.0 if str(route.get('plane')) == 'z1' else 0.5\n"
      "        dzs = abs(z_start - want_z)\n",
      "        z_start = float(first['z_mm'])\n"
      "        z_end = float(last['z_mm'])\n"
      "        want_z = float(_MODEL().interface_z(\n"
      "            'z1' if str(route.get('plane')) == 'z1' else 'z2'))\n"
      "        dzs = abs(z_start - want_z)\n")

# ===========================================================================
# (c) run_g4b.py -- target-height cap from the active model
# ===========================================================================
patch('xyzrouter/g4/run_g4b.py',
      'run_g4b: import the active model (19H at 21 heights, 18 at 20 heights)',
      "from four_side_1024.fanout1024.xyzrouter import manual_reheight as MR  # noqa: E402\n"
      "from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402\n",
      "from four_side_1024.fanout1024.reheight21 import model as M  # noqa: E402\n"
      "from four_side_1024.fanout1024.xyzrouter import manual_reheight as MR  # noqa: E402\n"
      "from four_side_1024.fanout1024.xyzrouter import route_builder as RB  # noqa: E402\n")

patch('xyzrouter/g4/run_g4b.py',
      'run_g4b: SCAN_CFG.max_target_layers = len(M.BODY_PLANES)',
      "SCAN_CFG = dict(max_target_layers=19, max_lead_pairs=1,\n",
      "SCAN_CFG = dict(max_target_layers=len(M.BODY_PLANES), max_lead_pairs=1,\n")

# ===========================================================================
# (d) g4/paths.py -- hard start-point validity guard + crossings/authority
# ===========================================================================
patch('xyzrouter/g4/paths.py',
      'paths: authority resolver with frozen-archive fallback',
      "#: frozen authoritative 2409 baseline (identity + manual-U contract only)\n"
      "AUTHORITY_DIR = XP.BASELINE_AUTHORITY\n",
      "#: frozen authoritative baseline (identity + port + manual-U contract only)\n"
      "def _resolve_authority_dir():\n"
      '    """Identity/port/manual-U authority directory (read-only, never a start).\n'
      "\n"
      "    The 20-height G3 run exports its own ``baseline_authoritative/`` under\n"
      "    the run dir; until that exists the frozen archive copy of the same\n"
      "    21-height baseline is the shared identity/port authority (the validator\n"
      "    with ``manual_policy=fully_optimizable`` only uses identity / port /\n"
      "    connection fields, never the routing heights).  The frozen 21-height\n"
      "    path is preferred and unchanged.\n"
      '    """\n'
      "    candidates = [Path(XP.BASELINE_AUTHORITY)]\n"
      "    candidates.extend([\n"
      "        Path(C.ROOT) / 'experiments' / 'xyz_joint_g123_1024' /\n"
      "        'baseline_authoritative',\n"
      "        Path(C.OUTPUT_ROOT) / 'manual_c4_new_connectivity' /\n"
      "        'XYZ_JOINT_G123_1024' / 'baseline_authoritative',\n"
      "    ])\n"
      "    for candidate in candidates:\n"
      "        if (candidate / 'routes_l3d.json').exists():\n"
      "            return candidate\n"
      "    return Path(XP.BASELINE_AUTHORITY)\n"
      "\n"
      "\n"
      "AUTHORITY_DIR = _resolve_authority_dir()\n")

patch('xyzrouter/g4/paths.py',
      'paths: hard start-profile guard + real start crossings + guarded load_start',
      "def load_start(start_dir=None):\n"
      '    """Load the G3 legal optimum (default) as the common G4 start point.\n'
      "\n"
      "    Returns the same dict shape as ``xyzrouter.paths.load_baseline`` plus the\n"
      "    verified start fingerprint.\n"
      '    """\n'
      "    start = Path(start_dir or START_DIR)\n"
      "    payload = read_json(start / 'routes_l3d.json')\n"
      "    routes = payload['routes']\n"
      "    rows = read_csv_rows(start / 'assignment_1024.csv')\n"
      "    return dict(dir=str(start), payload=payload, routes=routes, rows=rows,\n"
      "                routes_sha256=sha256_file(start / 'routes_l3d.json'),\n"
      "                assignment_sha256=sha256_file(start / 'assignment_1024.csv'),\n"
      "                crossings=int(START_CROSSINGS))\n"
      "\n"
      "\n"
      "def load_authority():\n"
      '    """Load the frozen 2409 authoritative baseline (read-only)."""\n'
      "    return load_start(AUTHORITY_DIR)\n",
      "def _active_model():\n"
      '    """The height model installed in this process (20H after bootstrap)."""\n'
      "    from ...reheight21 import model as M\n"
      "    return M\n"
      "\n"
      "\n"
      "def _model_file(model):\n"
      "    try:\n"
      "        return Path(model.__file__).resolve().relative_to(ROOT).as_posix()\n"
      "    except (AttributeError, ValueError):\n"
      "        return None\n"
      "\n"
      "\n"
      "def start_model_summary():\n"
      '    """Fingerprint of the ACTIVE height profile (used by the start guard)."""\n'
      "    model = _active_model()\n"
      "    return dict(\n"
      "        profile=getattr(model, 'PROFILE', None),\n"
      "        model_module=str(getattr(model, '__name__', '')),\n"
      "        model_file=_model_file(model),\n"
      "        plane_count=len(model.PLANE_IDS),\n"
      "        body_plane_count=len(model.BODY_PLANES),\n"
      "        plane_ids=[int(pid) for pid in model.PLANE_IDS],\n"
      "        interface_z={key: float(value)\n"
      "                     for key, value in model.INTERFACE_Z.items()},\n"
      "        min_3d_clearance_mm=float(model.MIN_3D_CLEARANCE_MM),\n"
      "        min_layer_pitch_mm=float(model.MIN_LAYER_PITCH_MM),\n"
      "        min_bend_radius_mm=float(model.MIN_BEND_RADIUS_MM),\n"
      "    )\n"
      "\n"
      "\n"
      "def assert_start_profile(start, context='load_start'):\n"
      '    """HARD validity guard: the start state must belong to the ACTIVE profile.\n'
      "\n"
      "    This is a *validity* guard, not a relaxation.  Every flat height of\n"
      "    every route, every ``layer_z_sequence`` entry, every route\n"
      "    ``target_z_mm``/``target_layer`` and every assignment ``target_layer`` /\n"
      "    ``target_z_mm`` / ``interface_z_mm`` must be a routing height of the\n"
      "    model installed in this process; the identity counts (1024 routes, 1024\n"
      "    assignment rows, 368 manual-U rows) must hold; and under the 20-height\n"
      "    profile the imported model must really be the 20-plane model with\n"
      "    identity 19 deleted.\n"
      "\n"
      "    The frozen 21-height archive loaded a 21-height G3 optimum into a\n"
      "    20-height process without any error (21 distinct flat heights, 50\n"
      "    routes on the deleted plane L19).  This guard makes that silent\n"
      "    21H/20H mix impossible (audit g4.md section 3.3).\n"
      '    """\n'
      "    model = _active_model()\n"
      "    summary = start_model_summary()\n"
      "    plane_ids = set(int(pid) for pid in model.PLANE_IDS)\n"
      "    plane_z = {round(float(model.plane_z(pid)), 9): int(pid)\n"
      "               for pid in model.PLANE_IDS}\n"
      "    problems = []\n"
      "    if PE.is_20h():\n"
      "        if len(plane_ids) != 20 or 19 in plane_ids:\n"
      "            problems.append(\n"
      "                'the 20-height profile is active but the imported model has '\n"
      "                '%d planes (identity 19 present=%s): bootstrap did not '\n"
      "                'install coldstart20.model20 before g4 was imported'\n"
      "                % (len(plane_ids), 19 in plane_ids))\n"
      "    routes = list(start.get('routes') or ())\n"
      "    rows = list(start.get('rows') or ())\n"
      "    if len(routes) != 1024:\n"
      "        problems.append('route payload has %d routes (expected 1024)'\n"
      "                        % len(routes))\n"
      "    if len(rows) != 1024:\n"
      "        problems.append('assignment has %d rows (expected 1024)' % len(rows))\n"
      "    manual = [row for row in rows\n"
      "              if str(row.get('manual_group') or '').strip()]\n"
      "    if len(manual) != 368:\n"
      "        problems.append('assignment has %d manual-U rows (expected 368)'\n"
      "                        % len(manual))\n"
      "    bad_flat = {}\n"
      "    bad_target_z = {}\n"
      "    bad_layers = {}\n"
      "    for route in routes:\n"
      "        for part in route.get('parts') or ():\n"
      "            if str(part.get('kind')) != 'flat':\n"
      "                continue\n"
      "            z = round(float(part.get('z_mm')), 9)\n"
      "            if z not in plane_z:\n"
      "                bad_flat[z] = bad_flat.get(z, 0) + 1\n"
      "        for z in route.get('layer_z_sequence') or ():\n"
      "            z = round(float(z), 9)\n"
      "            if z not in plane_z:\n"
      "                bad_flat[z] = bad_flat.get(z, 0) + 1\n"
      "        target_z = route.get('target_z_mm')\n"
      "        if target_z is not None:\n"
      "            z = round(float(target_z), 9)\n"
      "            if z not in plane_z:\n"
      "                bad_target_z[z] = bad_target_z.get(z, 0) + 1\n"
      "        target_layer = route.get('target_layer')\n"
      "        if target_layer is not None and \\\n"
      "                int(float(target_layer)) not in plane_ids:\n"
      "            bad_layers[int(float(target_layer))] = bad_layers.get(\n"
      "                int(float(target_layer)), 0) + 1\n"
      "    if bad_flat:\n"
      "        problems.append('route flat/layer heights not in the %d-plane model: '\n"
      "                        '%s' % (len(plane_ids),\n"
      "                                {float(k): v for k, v\n"
      "                                 in sorted(bad_flat.items())}))\n"
      "    if bad_target_z:\n"
      "        problems.append('route target heights not in the %d-plane model: %s'\n"
      "                        % (len(plane_ids),\n"
      "                           {float(k): v for k, v\n"
      "                            in sorted(bad_target_z.items())}))\n"
      "    if bad_layers:\n"
      "        problems.append('route target layers not in the model: %s'\n"
      "                        % {int(k): v for k, v in sorted(\n"
      "                            bad_layers.items())})\n"
      "    bad_row_layers = {}\n"
      "    bad_row_z = {}\n"
      "    bad_interface = {}\n"
      "    for row in rows:\n"
      "        layer = int(float(row.get('target_layer')))\n"
      "        z = float(row.get('target_z_mm'))\n"
      "        if layer not in plane_ids:\n"
      "            bad_row_layers[layer] = bad_row_layers.get(layer, 0) + 1\n"
      "        elif abs(z - float(model.plane_z(layer))) > 1e-9:\n"
      "            bad_row_z[layer] = bad_row_z.get(layer, 0) + 1\n"
      "        plane = str(row.get('plane') or '').strip()\n"
      "        if plane in getattr(model, 'INTERFACE_Z', {}):\n"
      "            interface_z = float(row.get('interface_z_mm'))\n"
      "            if abs(interface_z - float(model.interface_z(plane))) > 1e-9:\n"
      "                bad_interface[plane] = bad_interface.get(plane, 0) + 1\n"
      "    if bad_row_layers:\n"
      "        problems.append('assignment target_layer not in the model: %s'\n"
      "                        % bad_row_layers)\n"
      "    if bad_row_z:\n"
      "        problems.append('assignment target_z_mm != '\n"
      "                        'model.plane_z(target_layer) for layers: %s'\n"
      "                        % bad_row_z)\n"
      "    if bad_interface:\n"
      "        problems.append('assignment interface_z_mm != model interface '\n"
      "                        'height for: %s' % bad_interface)\n"
      "    if problems:\n"
      "        raise RuntimeError(\n"
      "            'G4 start point rejected by the %s-profile validity guard '\n"
      "            '[%s]: %s (start=%s).  A 21-height G3 optimum must never be '\n"
      "            'loaded into a 20-height process; run the 20H G3 stage first.'\n"
      "            % (summary['profile'] or 'unknown', context,\n"
      "               '; '.join(problems), start.get('dir')))\n"
      "    return dict(summary, route_count=len(routes),\n"
      "                assignment_rows=len(rows),\n"
      "                manual_route_count=len(manual),\n"
      "                checks=dict(profile_20h=(len(plane_ids) == 20),\n"
      "                            plane_19_absent=(19 not in plane_ids),\n"
      "                            flat_heights_in_model=True,\n"
      "                            target_z_in_model=True,\n"
      "                            target_layers_in_model=True,\n"
      "                            assignment_layers_in_model=True,\n"
      "                            assignment_z_in_model=True,\n"
      "                            interface_z_in_model=True,\n"
      "                            route_count_1024=True,\n"
      "                            manual_route_count_368=True))\n"
      "\n"
      "\n"
      "def start_crossing_total(start_dir):\n"
      '    """Exact crossing total recorded by a start directory, or ``None``.\n'
      "\n"
      "    The start state's *own* count is used (``crossing_stats.json`` /\n"
      "    ``summary.json`` / a G4 ``START.json``); the global ``START_CROSSINGS``\n"
      "    constant is never a data source for ``load_start`` (lightweight chain\n"
      "    checkpoints may carry no statistics, in which case the authoritative\n"
      "    value is ``state.start_total`` after the arm loaded its state).\n"
      '    """\n'
      "    for name in ('crossing_stats.json', 'summary.json', 'START.json'):\n"
      "        path = Path(start_dir) / name\n"
      "        if not path.exists():\n"
      "            continue\n"
      "        try:\n"
      "            payload = json.loads(path.read_text(encoding='utf-8'))\n"
      "        except (OSError, ValueError):\n"
      "            continue\n"
      "        totals = payload.get('totals') or payload\n"
      "        value = totals.get('crossings')\n"
      "        if value is None:\n"
      "            value = payload.get('crossings')\n"
      "        if value is not None:\n"
      "            return int(value)\n"
      "    return None\n"
      "\n"
      "\n"
      "def load_start(start_dir=None, validate_profile=True):\n"
      '    """Load a G4 start point (default: the 20H G3 legal optimum).\n'
      "\n"
      "    Returns the same dict shape as ``xyzrouter.paths.load_baseline`` plus\n"
      "    the start fingerprint.  ``crossings`` is the start's own recorded total\n"
      "    (or ``None`` for a lightweight chain checkpoint) and ``profile`` is the\n"
      "    hard validity-guard result.  ``validate_profile=False`` is only used for\n"
      "    the read-only identity authority, which may belong to another model.\n"
      '    """\n'
      "    start = Path(start_dir or START_DIR)\n"
      "    payload = read_json(start / 'routes_l3d.json')\n"
      "    routes = payload['routes']\n"
      "    rows = read_csv_rows(start / 'assignment_1024.csv')\n"
      "    loaded = dict(dir=str(start), payload=payload, routes=routes, rows=rows,\n"
      "                  routes_sha256=sha256_file(start / 'routes_l3d.json'),\n"
      "                  assignment_sha256=sha256_file(\n"
      "                      start / 'assignment_1024.csv'),\n"
      "                  crossings=start_crossing_total(start))\n"
      "    if validate_profile:\n"
      "        loaded['profile'] = assert_start_profile(loaded,\n"
      "                                                 context='load_start')\n"
      "    return loaded\n"
      "\n"
      "\n"
      "def load_authority():\n"
      '    """Load the read-only identity/port/manual-U authority baseline.\n'
      "\n"
      "    The authority is not a start state and may belong to the 18-layer model\n"
      "    even when a different routing profile is active, so the start-profile\n"
      "    validity guard deliberately does not apply here.\n"
      '    """\n'
      "    return load_start(AUTHORITY_DIR, validate_profile=False)\n")

# ===========================================================================
# (e) arm_base.py -- report the actual loaded start, never the 1322 constant
# ===========================================================================
patch('xyzrouter/g4/arm_base.py',
      'arm_base: ArmSpec records the actual start metadata',
      "        self.manual_frozen = bool(manual_frozen)\n"
      "        self.start_dir = Path(start_dir or GP.START_DIR)\n"
      "        self.log = log or log_default\n"
      "        self.started = time.time()\n",
      "        self.manual_frozen = bool(manual_frozen)\n"
      "        self.start_dir = Path(start_dir or GP.START_DIR)\n"
      "        self.log = log or log_default\n"
      "        self.started = time.time()\n"
      "        #: actual start metadata; filled by :meth:`ArmContext.load` (a chain\n"
      "        #: link start is not the global G3 optimum: never report the constant)\n"
      "        self.start_routes_sha256 = None\n"
      "        self.start_crossings = None\n")

patch('xyzrouter/g4/arm_base.py',
      'arm_base: as_dict uses the actual start, not GP.START_CROSSINGS',
      "    def as_dict(self):\n"
      "        return dict(arm=self.arm, out_dir=str(self.out_dir),\n"
      "                    seed=self.seed, budget=dict(self.budget),\n"
      "                    manual_frozen=self.manual_frozen,\n"
      "                    start_dir=str(self.start_dir),\n"
      "                    start_routes_sha256=GP.START_ROUTES_SHA256,\n"
      "                    start_crossings=int(GP.START_CROSSINGS),\n"
      "                    started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),\n"
      "                    cfg=dict(self.cfg))\n",
      "    def as_dict(self):\n"
      "        start_sha = (self.start_routes_sha256\n"
      "                     if self.start_routes_sha256 is not None\n"
      "                     else GP.START_ROUTES_SHA256)\n"
      "        start_crossings = (self.start_crossings\n"
      "                           if self.start_crossings is not None\n"
      "                           else GP.START_CROSSINGS)\n"
      "        return dict(arm=self.arm, out_dir=str(self.out_dir),\n"
      "                    seed=self.seed, budget=dict(self.budget),\n"
      "                    manual_frozen=self.manual_frozen,\n"
      "                    start_dir=str(self.start_dir),\n"
      "                    start_profile=getattr(M, 'PROFILE', None),\n"
      "                    start_routes_sha256=start_sha,\n"
      "                    start_crossings=(int(start_crossings)\n"
      "                                     if start_crossings is not None\n"
      "                                     else None),\n"
      "                    started_at=time.strftime('%Y-%m-%dT%H:%M:%S'),\n"
      "                    cfg=dict(self.cfg))\n")

patch('xyzrouter/g4/arm_base.py',
      'arm_base: load() logs the start artwork total (not the constant)',
      "        self.baseline = GP.load_start(start)\n"
      "        sha = self.baseline['routes_sha256']\n"
      "        self.log('[arm] start %s sha256=%s crossings=%d' % (\n"
      "            self.baseline['dir'], sha, GP.START_CROSSINGS))\n",
      "        self.baseline = GP.load_start(start)\n"
      "        sha = self.baseline['routes_sha256']\n"
      "        claimed = self.baseline.get('crossings')\n"
      "        self.log('[arm] start %s sha256=%s crossings=%s' % (\n"
      "            self.baseline['dir'], sha,\n"
      "            'recount-pending' if claimed is None else claimed))\n")

patch('xyzrouter/g4/arm_base.py',
      'arm_base: state.start_total is the reported start (metadata bug fix)',
      "        self.state.start_total = int(self.state.total)\n"
      "        self.log('[arm] loaded state routes=%d crossings=%d (%.2fs)' % (\n"
      "            len(self.state.routes), self.state.total, self.state.build_time))\n"
      "        return self\n",
      "        self.state.start_total = int(self.state.total)\n"
      "        # metadata bug fix (audit section 3.4): the arm must report the\n"
      "        # start state it actually loaded, never the global G3 constant.\n"
      "        self.spec.start_routes_sha256 = sha\n"
      "        self.spec.start_crossings = int(self.state.total)\n"
      "        if claimed is not None and int(claimed) != int(self.state.total):\n"
      "            self.log('[arm] WARNING: start artefacts report crossings=%d '\n"
      "                     'but the recounted state total is %d; the recounted '\n"
      "                     'value is used for delta_vs_start'\n"
      "                     % (int(claimed), int(self.state.total)))\n"
      "        self.log('[arm] loaded state routes=%d crossings=%d (%.2fs)' % (\n"
      "            len(self.state.routes), self.state.total, self.state.build_time))\n"
      "        return self\n")

patch('xyzrouter/g4/arm_base.py',
      'arm_base: summary() never falls back to the 1322 constant',
      "    def summary(self):\n"
      "        start_total = int(getattr(self.state, 'start_total',\n"
      "                                  GP.START_CROSSINGS))\n"
      "        return dict(arm=self.spec.arm, total=int(self.state.total),\n"
      "                    start_crossings=start_total,\n"
      "                    delta=int(self.state.total) - start_total,\n",
      "    def summary(self):\n"
      "        start_total = getattr(self.state, 'start_total', None)\n"
      "        if start_total is None:\n"
      "            start_total = self.spec.start_crossings\n"
      "        if start_total is None:\n"
      "            raise RuntimeError(\n"
      "                'arm summary requested before the start state was loaded: '\n"
      "                'the crossing delta would be taken against the wrong '\n"
      "                'baseline')\n"
      "        start_total = int(start_total)\n"
      "        return dict(arm=self.spec.arm, total=int(self.state.total),\n"
      "                    start_crossings=start_total,\n"
      "                    delta=int(self.state.total) - start_total,\n")

# ===========================================================================
# (f) artifacts.py -- profile-first validator subprocess
# ===========================================================================
patch('xyzrouter/g4/artifacts.py',
      'artifacts: import the cold-start profile env switch',
      "from ...reheight21 import model as M\n"
      "from . import ledger as L\n",
      "from ...coldstart20 import profile_env as PE\n"
      "from ...reheight21 import model as M\n"
      "from . import ledger as L\n")

patch('xyzrouter/g4/artifacts.py',
      'artifacts: validator subprocess is bootstrap-first under the 20H profile',
      "def run_validation(run_dir, out_dir, baseline_dir=None, manual_policy='fully_optimizable',\n"
      "                   python=None, log=None):\n"
      '    """Run the frozen independent validator in a fresh process."""\n'
      "    log = log or (lambda *_a, **_k: None)\n"
      "    cmd = [python or sys.executable, '-m',\n"
      "           'four_side_1024.fanout1024.xyzrouter.validate_xyz',\n"
      "           '--run-dir', str(run_dir),\n"
      "           '--out-dir', str(out_dir),\n"
      "           '--manual-policy', str(manual_policy)]\n"
      "    if baseline_dir:\n"
      "        cmd.extend(['--baseline-dir', str(baseline_dir)])\n"
      "    started = time.time()\n",
      "def validator_command(run_dir, out_dir, baseline_dir=None,\n"
      "                      manual_policy='fully_optimizable', python=None):\n"
      '    """CLI of the frozen independent validator under the ACTIVE profile.\n'
      "\n"
      "    Under the 20-height cold-start profile the frozen ``validate_xyz`` module\n"
      "    must be imported *after* ``coldstart20.bootstrap``; the bootstrap-first\n"
      "    G4 driver is used as the wrapper (its ``validate`` sub-command imports\n"
      "    ``validate_xyz`` inside the profile-installed process).  Without the\n"
      "    20-height profile the historical command is returned unchanged.\n"
      '    """\n'
      "    executable = python or sys.executable\n"
      "    if PE.is_20h():\n"
      "        cmd = [executable, '-m',\n"
      "               'four_side_1024.fanout1024.coldstart20.run_g4', 'validate',\n"
      "               '--run-dir', str(run_dir),\n"
      "               '--out-dir', str(out_dir),\n"
      "               '--manual-policy', str(manual_policy)]\n"
      "    else:\n"
      "        cmd = [executable, '-m',\n"
      "               'four_side_1024.fanout1024.xyzrouter.validate_xyz',\n"
      "               '--run-dir', str(run_dir),\n"
      "               '--out-dir', str(out_dir),\n"
      "               '--manual-policy', str(manual_policy)]\n"
      "    if baseline_dir:\n"
      "        cmd.extend(['--baseline-dir', str(baseline_dir)])\n"
      "    return cmd\n"
      "\n"
      "\n"
      "def run_validation(run_dir, out_dir, baseline_dir=None, manual_policy='fully_optimizable',\n"
      "                   python=None, log=None):\n"
      '    """Run the frozen independent validator in a fresh process."""\n'
      "    log = log or (lambda *_a, **_k: None)\n"
      "    cmd = validator_command(run_dir, out_dir, baseline_dir=baseline_dir,\n"
      "                            manual_policy=manual_policy, python=python)\n"
      "    started = time.time()\n")

# ===========================================================================
# (g) artifacts.py -- 20H snapshots carry the ACTIVE model's layer table
# ===========================================================================
patch('xyzrouter/g4/artifacts.py',
      'artifacts: 20H snapshots write a real 20-plane layer_planes.json',
      "    hashes = dict(\n"
      "        routes_l3d_json=GP.sha256_file(out_dir / 'routes_l3d.json'),\n"
      "        assignment_1024_csv=GP.sha256_file(out_dir / 'assignment_1024.csv'))\n"
      "    if include_stats:\n",
      "    hashes = dict(\n"
      "        routes_l3d_json=GP.sha256_file(out_dir / 'routes_l3d.json'),\n"
      "        assignment_1024_csv=GP.sha256_file(out_dir / 'assignment_1024.csv'))\n"
      "    if PE.is_20h() and hasattr(M, 'layer_planes_payload'):\n"
      "        # configuration patch: every 20-height snapshot carries the ACTIVE\n"
      "        # 20-plane model table, so the frozen validator (_load_model prefers\n"
      "        # the run's layer_planes.json) can never fall back to a 21-height\n"
      "        # baseline table.  Frozen 21-height behaviour is untouched (this\n"
      "        # branch is off without the 20H profile).\n"
      "        assigned = {}\n"
      "        for planner in (state.rows or {}).values():\n"
      "            layer = int(planner.get('target_layer'))\n"
      "            assigned[layer] = assigned.get(layer, 0) + 1\n"
      "        GP.write_json(out_dir / 'layer_planes.json',\n"
      "                      M.layer_planes_payload(assigned=assigned))\n"
      "        hashes['layer_planes_json'] = GP.sha256_file(\n"
      "            out_dir / 'layer_planes.json')\n"
      "    if include_stats:\n")

#: post-conditions that prove the patches landed (checked by ``--check``)
POSTCONDITIONS = [
    ('xyzrouter/g4/contract_audit.py', 'def model_code_citations():'),
    ('xyzrouter/g4/contract_audit.py', "cross_checks['heights_%d' % len(_model.PLANE_IDS)]"),
    ('xyzrouter/g4/contract_audit.py', "'%d-height model 50 um 3D clearance' % plane_count"),
    ('xyzrouter/g4/independent_metrics.py', "_MODEL().interface_z("),
    ('xyzrouter/g4/run_g4b.py', 'max_target_layers=len(M.BODY_PLANES)'),
    ('xyzrouter/g4/paths.py', 'def assert_start_profile(start, context='),
    ('xyzrouter/g4/paths.py', 'def start_crossing_total(start_dir):'),
    ('xyzrouter/g4/paths.py', 'def _resolve_authority_dir():'),
    ('xyzrouter/g4/arm_base.py', 'self.spec.start_crossings = int(self.state.total)'),
    ('xyzrouter/g4/arm_base.py', "if start_total is None:"),
    ('xyzrouter/g4/artifacts.py', 'def validator_command('),
    ('xyzrouter/g4/artifacts.py', "hashes['layer_planes_json']"),
]


def _sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def run(apply=True):
    applied, skipped, failures = [], [], []
    changed_files = {}
    for item in PATCHES:
        path = PKG / item['file']
        try:
            text = path.read_text(encoding='utf-8')
        except OSError as error:
            failures.append((item['name'], 'cannot read %s: %s'
                             % (path, error)))
            continue
        found_old = text.count(item['old'])
        found_new = text.count(item['new'])
        if found_new == 1:
            # post-image already present exactly once -> this patch is applied.
            # (Some patches are pure insertions whose post-image *contains* the
            # pre-image, so post-image must be tested first for idempotency.)
            skipped.append(item['name'])
            print('SKIP %-72s already applied' % item['name'])
        elif found_old == 1:
            if apply:
                updated = text.replace(item['old'], item['new'], 1)
                if updated.count(item['new']) != 1:
                    failures.append((item['name'],
                                     'post-image count after write is not 1 in '
                                     '%s' % path))
                    print('FAIL %-72s post-image count != 1' % item['name'])
                    continue
                path.write_text(updated, encoding='utf-8')
                changed_files[item['file']] = changed_files.get(
                    item['file'], 0) + 1
            applied.append(item['name'])
            print('OK   %-72s %s' % (item['name'], item['file']))
        else:
            failures.append((item['name'],
                             'expected exactly 1 pre-image, found %d '
                             '(post-image count %d) in %s'
                             % (found_old, found_new, path)))
            print('FAIL %-72s pre-image=%d post-image=%d'
                  % (item['name'], found_old, found_new))
    missing = []
    for relative, needle in POSTCONDITIONS:
        text = (PKG / relative).read_text(encoding='utf-8')
        if needle not in text:
            missing.append((relative, needle))
    if apply:
        for relative in changed_files:
            source = (PKG / relative).read_text(encoding='utf-8')
            try:
                # a preserved UTF-8 BOM (legacy file) is fine for the Python
                # tokenizer but not for a bare compile() call
                compile(source.lstrip('\ufeff'), str(PKG / relative), 'exec')
            except SyntaxError as error:
                failures.append((relative, 'post-patch SyntaxError: %s' % error))
    print('')
    print('patches applied : %d' % len(applied))
    print('already applied : %d' % len(skipped))
    print('files changed   : %s' % {key: value for key, value
                                    in sorted(changed_files.items())})
    print('sha256 after    : %s' % {
        relative: _sha256(PKG / relative) for relative in sorted(changed_files)})
    if missing:
        failures.extend([('postcondition', '%s: missing %r' % (relative, needle))
                         for relative, needle in missing])
    if failures:
        print('')
        print('FAILURES:')
        for name, detail in failures:
            print('  %s: %s' % (name, detail))
        return 1
    print('all postconditions present')
    return 0


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true',
                        help='verify only; never write (exit 0 when every '
                             'patch is applied)')
    parser.add_argument('--dry-run', action='store_true',
                        help='print the plan; never write')
    args = parser.parse_args(argv)
    print('project : %s' % PROJECT)
    print('package : %s' % PKG)
    print('mode    : %s' % ('check' if args.check else
                            ('dry-run' if args.dry_run else 'apply')))
    if args.check:
        return run(apply=False)
    if args.dry_run:
        applied, skipped, failures = [], [], []
        for item in PATCHES:
            text = (PKG / item['file']).read_text(encoding='utf-8')
            found_old = text.count(item['old'])
            found_new = text.count(item['new'])
            state = ('apply' if found_old == 1 else
                     'already' if found_old == 0 and found_new == 1 else
                     'FAIL(%d/%d)' % (found_old, found_new))
            print('%-74s %-8s %s' % (item['name'], state, item['file']))
        return 0
    return run(apply=True)


if __name__ == '__main__':
    sys.exit(main())
