"""Input hashing, dataset loading and result serialisation helpers."""
from __future__ import annotations

import csv
import hashlib
import json
import platform
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

ROUTES_SHA256 = "35d7ebed00339bee21fe0ca47075c9b34008120522a47933a099efacf0b90753"
TOTAL_LENGTH_MM = 156597.221522
EXPECTED_CROSSINGS = 1283
EXPECTED_CROSSING_PAIRS = 1221


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            b = f.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def json_default(o: Any):
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, np.ndarray):
        return o.tolist()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(f"not serialisable: {type(o)}")


def write_json(path: Path, obj: Any, indent: int = 1) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=indent, default=json_default)


def read_json(path: Path) -> Any:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def write_csv(path: Path, rows: list[dict], fieldnames: list[str] | None = None) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    if fieldnames is None:
        fieldnames = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        w.writeheader()
        for r in rows:
            w.writerow(r)


# --------------------------------------------------------------------------- yaml
def _yaml_scalar(v: Any) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if v is None:
        return "null"
    if isinstance(v, float):
        if v != v:
            return ".nan"
        return repr(float(v))
    if isinstance(v, (int, np.integer)):
        return str(int(v))
    s = str(v)
    if s == "" or any(c in s for c in ":#\n{}[],&*?|>!%@`\"'"):
        return json.dumps(s, ensure_ascii=False)
    return s


def dump_yaml(obj: Any, indent: int = 0) -> str:
    """Small dependency-free YAML emitter (mappings / sequences / scalars)."""
    pad = "  " * indent
    lines: list[str] = []
    if isinstance(obj, dict):
        if not obj:
            return pad + "{}\n"
        for k, v in obj.items():
            key = _yaml_scalar(k)
            if isinstance(v, dict):
                if not v:
                    lines.append(f"{pad}{key}: {{}}\n")
                else:
                    lines.append(f"{pad}{key}:\n")
                    lines.append(dump_yaml(v, indent + 1))
            elif isinstance(v, (list, tuple)):
                if not v:
                    lines.append(f"{pad}{key}: []\n")
                else:
                    lines.append(f"{pad}{key}:\n")
                    lines.append(dump_yaml(list(v), indent + 1))
            else:
                lines.append(f"{pad}{key}: {_yaml_scalar(v)}\n")
        return "".join(lines)
    if isinstance(obj, (list, tuple)):
        for v in obj:
            if isinstance(v, (dict, list)):
                sub = dump_yaml(v, indent + 1)
                first, *rest = sub.splitlines(True)
                lines.append(f"{pad}- {first.lstrip()}")
                lines.extend(rest)
            else:
                lines.append(f"{pad}- {_yaml_scalar(v)}\n")
        return "".join(lines)
    return f"{pad}{_yaml_scalar(obj)}\n"


def write_yaml(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dump_yaml(obj), encoding="utf-8")


# ----------------------------------------------------------------------- dataset
@dataclass
class Dataset:
    root: Path
    routes_doc: dict
    routes: list
    assignment: list[dict]
    layer_planes: dict
    physical_stack: dict
    process_rules: dict
    crossing_stats: dict
    best_valid: dict
    validation: dict
    sha_index: dict
    sha_check: dict = field(default_factory=dict)

    @property
    def crossing_events(self) -> list[dict]:
        return self.crossing_stats["crossing_events"]


def load_dataset(root: Path, verify_hash: bool = True) -> Dataset:
    root = Path(root)
    sha_index = read_json(root / "SHA256.json")
    sha_check: dict[str, dict] = {}
    # Only the geometric/route payloads must match bit-exactly.  BEST_VALID.json
    # is a human-facing manifest that was rewritten after SHA256.json was
    # generated in the source repository (+310 bytes: validator_report and
    # model_payloads_completed); that discrepancy is recorded, not hidden.
    critical = {
        "routes_l3d.json", "assignment_1024.csv", "layer_planes.json",
        "physical_layer_stack.json", "process_rules.json", "crossing_stats.json",
        "validation.json",
    }
    for name, rec in sha_index.items():
        p = root / name.replace("\\", "/")
        if not p.exists():
            p = root / name
        got = sha256_file(p)
        ok = got == rec["sha256"]
        sha_check[name] = {
            "expected": rec["sha256"], "actual": got, "ok": ok,
            "bytes": p.stat().st_size, "expected_bytes": rec["bytes"],
            "size_ok": p.stat().st_size == rec["bytes"],
            "critical": name.replace("\\", "/") in critical,
        }
    if verify_hash:
        bad = [k for k, v in sha_check.items() if not v["ok"] and v["critical"]]
        if bad:
            raise RuntimeError(f"SHA256 mismatch for critical input(s) {bad}")
        if sha_check["routes_l3d.json"]["actual"] != ROUTES_SHA256:
            raise RuntimeError(
                "routes_l3d.json hash does not match the frozen final route hash"
            )

    from .geom3d import build_routes

    routes_doc = read_json(root / "routes_l3d.json")
    routes = build_routes(routes_doc)
    with open(root / "assignment_1024.csv", encoding="utf-8") as f:
        assignment = list(csv.DictReader(f))
    return Dataset(
        root=root,
        routes_doc=routes_doc,
        routes=routes,
        assignment=assignment,
        layer_planes=read_json(root / "layer_planes.json"),
        physical_stack=read_json(root / "physical_layer_stack.json"),
        process_rules=read_json(root / "process_rules.json"),
        crossing_stats=read_json(root / "crossing_stats.json"),
        best_valid=read_json(root / "BEST_VALID.json"),
        validation=read_json(root / "validation.json"),
        sha_index=sha_index,
        sha_check=sha_check,
    )


def runtime_info() -> dict:
    import scipy
    import matplotlib

    return {
        "python": sys.version.split()[0],
        "executable": sys.executable,
        "platform": platform.platform(),
        "numpy": np.__version__,
        "scipy": scipy.__version__,
        "matplotlib": matplotlib.__version__,
        "cpu_count": __import__("os").cpu_count(),
    }
