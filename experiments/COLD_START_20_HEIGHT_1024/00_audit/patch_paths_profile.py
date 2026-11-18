# -*- coding: utf-8 -*-
"""Fourth audited patch: make the frozen *path* modules 20-height aware.

Only run directories, the inherited crossing total and one hard-coded interface
height pair are changed.  Every default is exactly the historical 21-height
value, so a process that does not import ``coldstart20.bootstrap`` (which is
what publishes the ``COLDSTART20_*`` variables) behaves bit-identically to the
frozen pipeline.  No geometric rule, threshold or acceptance criterion moves.
"""
import sys
from pathlib import Path

PKG = Path(r'C:\Users\lihao\Desktop\Graduation Project\OpticalWaveguideRouter2D'
           r'\four_side_1024\fanout1024')

PATCHES = []


def patch(name, old, new, count=1):
    PATCHES.append(dict(name=name, old=old, new=new, count=count))


# ===========================================================================
# native3d/common.py -- directories + MOVABLE_PLANES (deleted identity 19)
# ===========================================================================
patch('native3d/common.py: import profile_env',
      "from .. import common as C\nfrom ..reheight21 import model as M\n",
      "from .. import common as C\nfrom ..reheight21 import model as M\n"
      "from ..coldstart20 import profile_env as PE\n")

patch('native3d/common.py: directories',
      "#: frozen accepted C4-free baseline (E5) -- READ ONLY\n"
      "E5_DIR = OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024' / 'E5_joint_repair_final'\n"
      "#: previous balanced 21-height success baseline (READ ONLY)\n"
      "BASELINE_21H_DIR = OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'\n"
      "#: new experiment root\n"
      "RUN_DIR = OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024'\n",
      "#: accepted C4-free baseline (E5) -- READ ONLY.  Frozen 21-height default;\n"
      "#: the 20-height profile publishes COLDSTART20_E5_DIR.\n"
      "E5_DIR = PE.path_env(\n"
      "    'E5_DIR',\n"
      "    OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024' / 'E5_joint_repair_final')\n"
      "#: previous balanced 21-height success baseline (READ ONLY)\n"
      "BASELINE_21H_DIR = PE.path_env(\n"
      "    'FANOUT_BASELINE_DIR',\n"
      "    OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024')\n"
      "#: new experiment root\n"
      "RUN_DIR = PE.path_env('NATIVE3D_ABC_RUN',\n"
      "                      OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024')\n")

patch('native3d/common.py: MOVABLE_PLANES derived from the profile',
      "#: the 13 non-manual routing heights usable by movable routes\n"
      "MOVABLE_PLANES = (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18, 19)\n"
      "MANUAL_PLANES = tuple(int(pid) for pid in M.MANUAL_PLANE_IDS)\n",
      "#: every non-manual routing height usable by movable routes.  Derived\n"
      "#: from the active height profile: 13 ids at 21 heights, 12 ids at 20\n"
      "#: heights (identity 19 no longer exists).  The 21-height result is the\n"
      "#: exact frozen tuple (6, 7, 20, 1001, 8, 9, 14, 15, 16, 1002, 17, 18, 19).\n"
      "MANUAL_PLANES = tuple(int(pid) for pid in M.MANUAL_PLANE_IDS)\n"
      "MOVABLE_PLANES = tuple(int(pid) for pid in M.PLANE_IDS\n"
      "                       if int(pid) not in set(MANUAL_PLANES))\n")

# ===========================================================================
# native3d/route_model.py -- interface lead heights
# ===========================================================================
patch('native3d/route_model.py: interface heights',
      "            interface_heights = (0.0, 0.5)\n",
      "            interface_heights = (float(M.Z1_INTERFACE_MM),\n"
      "                                 float(M.Z2_INTERFACE_MM))\n")

# ===========================================================================
# native3d/phase2.py -- Phase-1 dir + inherited crossing total
# ===========================================================================
patch('native3d/phase2.py: import profile_env',
      "from .. import common as C\nfrom . import common as N\nfrom . import guard as G\n",
      "from .. import common as C\nfrom ..coldstart20 import profile_env as PE\n"
      "from . import common as N\nfrom . import guard as G\n")

patch('native3d/phase2.py: phase-1 dir and inherited crossings',
      "#: accepted Phase-1 Native 3D layout (READ ONLY)\n"
      "PHASE1_DIR = N.OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024'\n"
      "PHASE1_RUN_DIR = PHASE1_DIR / 'experiment_C'\n"
      "#: inherited baseline crossing count\n"
      "BASELINE_CROSSINGS = 2440\n"
      "#: new Phase-2 root\n"
      "RUN2 = N.OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024'\n",
      "#: accepted Phase-1 Native 3D layout (READ ONLY).  Same run directory the\n"
      "#: frozen 21-height experiment used, parameterised for the active profile.\n"
      "PHASE1_DIR = N.RUN_DIR\n"
      "PHASE1_RUN_DIR = PHASE1_DIR / 'experiment_C'\n"
      "#: new Phase-2 root\n"
      "RUN2 = PE.path_env('NATIVE3D_DEF_RUN',\n"
      "                   N.OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024')\n"
      "\n"
      "\n"
      "def _inherited_crossings():\n"
      '    """Crossing total of the accepted Phase-1 layout (never a literal).\n'
      "\n"
      "    The historical 21-height Phase-2 experiment was hard-wired to 2440; a\n"
      "    different height profile must inherit whatever its own Phase-1\n"
      "    produced.  The value is read from the accepted layout's\n"
      "    ``crossing_stats.json`` (``COLDSTART20_PHASE1_CROSSINGS`` wins for a\n"
      "    bit-reproducible rerun).\n"
      '    """\n'
      "    override = PE.int_env('PHASE1_CROSSINGS')\n"
      "    if override is not None:\n"
      "        return int(override)\n"
      "    for path in (PHASE1_DIR / 'crossing_stats.json',\n"
      "                 PHASE1_RUN_DIR / 'crossing_stats.json'):\n"
      "        try:\n"
      "            payload = json.loads(Path(path).read_text(encoding='utf-8'))\n"
      "        except (OSError, ValueError):\n"
      "            continue\n"
      "        value = (payload.get('totals') or {}).get('crossings')\n"
      "        if value is not None:\n"
      "            return int(value)\n"
      "    if PE.is_20h():\n"
      "        raise RuntimeError(\n"
      "            'the accepted Phase-1 layout has no crossing_stats.json; set '\n"
      "            'COLDSTART20_PHASE1_CROSSINGS or validate Phase 1 first: %s'\n"
      "            % (PHASE1_DIR,))\n"
      "    return 2440\n"
      "\n"
      "\n"
      "#: inherited baseline crossing count of the accepted Phase-1 layout\n"
      "BASELINE_CROSSINGS = _inherited_crossings()\n")

# ===========================================================================
# xyzrouter/paths.py -- run directories
# ===========================================================================
patch('xyzrouter/paths.py: import profile_env',
      "from .. import common as C\n\nROOT = Path(C.ROOT)\n",
      "from .. import common as C\nfrom ..coldstart20 import profile_env as PE\n"
      "\nROOT = Path(C.ROOT)\n")

patch('xyzrouter/paths.py: run directories',
      "#: previous-round join-optimised native-3D run (READ ONLY)\n"
      "NATIVE_JOINT_DIR = OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024'\n"
      "NATIVE_PHASE1_DIR = OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024'\n"
      "NON_C4_DIR = OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024'\n"
      "E5_DIR = NON_C4_DIR / 'E5_joint_repair_final'\n"
      "\n"
      "#: this round's run directory\n"
      "XYZ_RUN_DIR = OUTPUT_ROOT / 'XYZ_JOINT_G123_1024'\n",
      "#: previous-round join-optimised native-3D run (READ ONLY)\n"
      "NATIVE_JOINT_DIR = PE.path_env(\n"
      "    'NATIVE3D_DEF_RUN', OUTPUT_ROOT / 'NATIVE_3D_JOINT_OPT_1024')\n"
      "NATIVE_PHASE1_DIR = PE.path_env(\n"
      "    'NATIVE3D_ABC_RUN', OUTPUT_ROOT / 'NATIVE_3D_CROSSING_OPT_1024')\n"
      "NON_C4_DIR = PE.path_env('NONC4_ROOT',\n"
      "                         OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024')\n"
      "E5_DIR = PE.path_env('E5_DIR', NON_C4_DIR / 'E5_joint_repair_final')\n"
      "\n"
      "#: this round's run directory\n"
      "XYZ_RUN_DIR = PE.path_env('XYZ_RUN',\n"
      "                          OUTPUT_ROOT / 'XYZ_JOINT_G123_1024')\n")

# ===========================================================================
# nonc4/paths.py -- programme root + frozen baseline geometry source
# ===========================================================================
patch('nonc4/paths.py: import profile_env',
      "from .. import common as C\nfrom ..reheight21 import model as M\n",
      "from .. import common as C\nfrom ..coldstart20 import profile_env as PE\n"
      "from ..reheight21 import model as M\n")

patch('nonc4/paths.py: programme root and baseline dirs',
      "#: root of the whole C4-free research programme\n"
      "EXPERIMENT_ROOT = C.OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024'\n"
      "#: frozen 21-height baseline (READ-ONLY, never written here)\n"
      "BASELINE_21H_DIR = C.OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024'\n"
      "#: frozen 18-layer baseline of the 21-height work (READ-ONLY)\n"
      "BASELINE_18L_DIR = C.RUN_DIR\n",
      "#: root of the whole C4-free research programme\n"
      "EXPERIMENT_ROOT = PE.path_env(\n"
      "    'NONC4_ROOT', C.OUTPUT_ROOT / 'NON_C4_CROSSING_OPT_1024')\n"
      "#: frozen upstream baseline whose 368 manual-U geometry is re-used\n"
      "#: (READ-ONLY, never written here).  21 heights: the 21-height fanout-first\n"
      "#: run; 20 heights: the 20-height fanout-first run (stage 03).\n"
      "BASELINE_21H_DIR = PE.path_env(\n"
      "    'FANOUT_BASELINE_DIR',\n"
      "    C.OUTPUT_ROOT / 'FANOUT_FIRST_21_HEIGHT_REBALANCED_1024')\n"
      "#: frozen 18-layer baseline (READ-ONLY; assignment contract source)\n"
      "BASELINE_18L_DIR = C.RUN_DIR\n")

# ===========================================================================
# xyzrouter/g4/paths.py -- archive root + start fingerprint
# ===========================================================================
patch('g4/paths.py: import os',
      "import hashlib\nimport json\nimport csv\nfrom pathlib import Path\n",
      "import csv\nimport hashlib\nimport json\nimport os\nfrom pathlib import Path\n")

patch('g4/paths.py: import profile_env',
      "from .. import paths as XP\nfrom ... import common as C\n\nROOT = Path(C.ROOT)\n"
      "G4_ROOT = ROOT / 'experiments' / 'xyz_joint_g4_1024'\n"
      "\n"
      "#: verified G3 legal optimum: the mandatory common start point of every G4 arm\n"
      "START_DIR = XP.XYZ_RUN_DIR / 'best_valid'\n"
      "START_ROUTES_SHA256 = '711cf910d5c75ea788be877ef88b588fe3d59a90a2ae2d3636bb5b5896834077'\n"
      "START_CROSSINGS = 1322\n",
      "from .. import paths as XP\nfrom ... import common as C\n"
      "from ...coldstart20 import profile_env as PE\n\nROOT = Path(C.ROOT)\n"
      "G4_ROOT = PE.path_env('G4_ROOT',\n"
      "                      ROOT / 'experiments' / 'xyz_joint_g4_1024')\n"
      "\n"
      "#: verified G3 legal optimum: the mandatory common start point of every G4 arm\n"
      "START_DIR = XP.XYZ_RUN_DIR / 'best_valid'\n"
      "\n"
      "\n"
      "def _sha256(path):\n"
      "    digest = hashlib.sha256()\n"
      "    with Path(path).open('rb') as handle:\n"
      "        for chunk in iter(lambda: handle.read(1 << 20), b''):\n"
      "            digest.update(chunk)\n"
      "    return digest.hexdigest()\n"
      "\n"
      "\n"
      "def _start_fingerprint(start_dir):\n"
      '    """Routes SHA256 + crossing total of the G3 legal optimum (no literals).\n'
      "\n"
      "    The frozen 21-height archive hard-wired ``711cf910...`` / 1322; a\n"
      "    different height profile must fingerprint its own G3 optimum, so the\n"
      "    values are computed from ``best_valid`` (env overrides\n"
      "    ``COLDSTART20_START_SHA`` / ``COLDSTART20_START_CROSSINGS`` win for a\n"
      "    bit-reproducible rerun).\n"
      '    """\n'
      "    sha = os.environ.get('COLDSTART20_START_SHA')\n"
      "    crossings = PE.int_env('START_CROSSINGS')\n"
      "    routes = Path(start_dir) / 'routes_l3d.json'\n"
      "    if sha is None and routes.exists():\n"
      "        sha = _sha256(routes)\n"
      "    if crossings is None:\n"
      "        for name in ('crossing_stats.json', 'summary.json'):\n"
      "            path = Path(start_dir) / name\n"
      "            try:\n"
      "                payload = json.loads(path.read_text(encoding='utf-8'))\n"
      "            except (OSError, ValueError):\n"
      "                continue\n"
      "            value = ((payload.get('totals') or {}).get('crossings')\n"
      "                     or payload.get('crossings'))\n"
      "            if value is not None:\n"
      "                crossings = int(value)\n"
      "                break\n"
      "    if PE.is_20h() and (sha is None or crossings is None):\n"
      "        raise RuntimeError(\n"
      "            'the 20-height G4 start point must be a validated G3 legal '\n"
      "            'optimum with routes_l3d.json + crossing total: %s'\n"
      "            % (start_dir,))\n"
      "    return sha, crossings\n"
      "\n"
      "\n"
      "START_ROUTES_SHA256, START_CROSSINGS = _start_fingerprint(START_DIR)\n")


def main():
    changed = {}
    failures = []
    for item in PATCHES:
        path = PKG / item['name'].split(':')[0]
        text = path.read_text(encoding='utf-8')
        found = text.count(item['old'])
        if found != item['count']:
            failures.append((item['name'], found, item['count']))
            continue
        path.write_text(text.replace(item['old'], item['new']), encoding='utf-8')
        changed[path.name] = changed.get(path.name, 0) + 1
        print(f'OK   {item["name"]}')
    if failures:
        print('\nFAILURES:')
        for name, found, want in failures:
            print(f'  {name}: found {found}, expected {want}')
        return 1
    print('\nfiles changed:', changed)
    return 0


if __name__ == '__main__':
    sys.exit(main())

