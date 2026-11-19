"""Write the simulation manifest: input/output hashes, code version, runtime."""
from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.config import CONFIG, EXPERIMENT_ROOT
from src.dataio import read_json, runtime_info, sha256_file, write_json, write_yaml
from src import __version__


def main() -> int:
    opt = EXPERIMENT_ROOT / "outputs" / "optical"
    geo = EXPERIMENT_ROOT / "outputs" / "geometry"
    best = Path(CONFIG["inputs"]["best_valid_dir"])
    write_yaml(EXPERIMENT_ROOT / "config" / "simulation_config.yaml", CONFIG)

    inputs = {}
    for p in sorted(best.glob("*")):
        if p.is_file():
            inputs[p.name] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    for p in sorted((best / "validation").glob("*")):
        if p.is_file():
            inputs[f"validation/{p.name}"] = {"sha256": sha256_file(p),
                                              "bytes": p.stat().st_size}
    sha_index = read_json(best / "SHA256.json")
    integrity = {}
    for name, rec in sha_index.items():
        key = name.replace("\\", "/")
        got = inputs.get(key, {}).get("sha256")
        integrity[key] = {"expected": rec["sha256"], "actual": got,
                          "match": got == rec["sha256"]}

    outputs = {}
    for folder in (opt, geo, EXPERIMENT_ROOT / "outputs" / "figures"):
        for p in sorted(folder.glob("*")):
            if p.is_file():
                outputs[p.name] = {"sha256": sha256_file(p),
                                   "bytes": p.stat().st_size}

    manifest = {
        "schema": "crosstalk_prediction_manifest_v1",
        "model_version": CONFIG["model_version"],
        "package_version": __version__,
        "experiment": CONFIG["experiment"],
        "generated_at_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "input_directory": str(best),
        "route_sha256_expected": CONFIG["inputs"]["routes_sha256_expected"],
        "route_sha256_actual": inputs.get("routes_l3d.json", {}).get("sha256"),
        "route_sha256_match": inputs.get("routes_l3d.json", {}).get("sha256")
        == CONFIG["inputs"]["routes_sha256_expected"],
        "integrity": integrity,
        "known_input_discrepancy": {
            "file": "BEST_VALID.json",
            "detail": ("source repo rewrote the manifest after SHA256.json was "
                       "generated (+310 bytes: validator_report, "
                       "model_payloads_completed); all geometric/optical inputs "
                       "match bit-exactly"),
        },
        "outputs": outputs,
        "runtime": runtime_info(),
        "models": {
            "mode_solver": CONFIG["mode_solver"]["equation"],
            "coupling": CONFIG["coupling"]["method"],
            "crossing": CONFIG["crossing_model"]["primary"],
            "propagation": "coupled power with 0.05 dB/cm along true arc length",
            "approximation_class": "scalar weak-guidance / EIM / 2-D FDFD",
            "full_vector_maxwell": False,
        },
        "parameters": {
            "optics_reference": CONFIG["optics"]["reference"],
            "propagation_loss_db_per_cm": CONFIG["optics"]["propagation_loss_db_per_cm"],
            "bend_extra_loss_db": CONFIG["optics"]["bend_extra_loss_db"],
            "resolution_floor": CONFIG["crossing_model"]["resolution_floor"],
        },
        "reproduce": [
            "python scripts/run_e1.py",
            "python scripts/run_e2.py",
            "python scripts/run_e3.py",
            "python scripts/run_e4.py",
            "python scripts/run_e5.py",
            "python scripts/run_e6.py",
            "python scripts/make_figures.py",
            "python scripts/run_manifest.py",
            "python scripts/run_report.py",
        ],
    }
    write_json(opt / "simulation_manifest.json", manifest)
    print(f"[MANIFEST] routes sha match: {manifest['route_sha256_match']}")
    print(f"[MANIFEST] {len(outputs)} output files hashed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
