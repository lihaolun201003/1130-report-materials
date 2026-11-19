"""Validate drawing inputs and extract the exact L7 geometry for figure 10."""
import argparse
from collections import Counter
import csv
from hashlib import sha256
from itertools import combinations
import json
from math import atan2, cos, dist, hypot, isclose, pi, sin
from pathlib import Path

HERE = Path(__file__).resolve().parent
WORKSPACE = HERE.parents[3]
EXPERIMENT = Path("experiments/COLD_START_20_HEIGHT_1024")
PROGRAMME = Path("04_initial_3d_and_e5_repair/nonc4_programme")
EXPERIMENTS = {"E1": "E1_family_pure", "E3": "E3_family_pure_sa_seed11"}
SOURCE_COMMIT = "e9025598810e3e224724e38cbcd66f105f10643e"
ORIGINAL_HASHES = {
    "发明专利_权利要求书.docx": "42a301b5948a20affd29965edf0589344caa251faa97407c6ea8adc34988570c",
    "发明专利_说明书.docx": "98ae313b6f56b00186b7696d2d776be3a6c65f9513acb7cc46b658c071c0bb5c",
    "发明专利_说明书摘要.docx": "f09728bddcf7cd778cd3a2bbc62750e26f05aaf08fc333b8c8bc4dfcb31fba1b",
    "发明专利_说明书附图.pdf": "9d673f80869ed9bd5605ac90d280397f991e1bb71d5b7b32c8365495580bf53a",
}
FAMILIES = {
    "Z1V": [6, 7], "Z1H": [20, 1001, 8], "Z2_NE": [9, 14],
    "Z2_SE": [15, 16], "Z2_NW": [17], "Z2_SW": [18, 1002],
}
HEIGHT_IDS = [2, 3, 4, 5, 6, 7, 20, 1001, 8, 9, 10, 11, 12,
              13, 14, 15, 16, 1002, 17, 18]
CHORDS = [
    ((27, 103), (86, 141)), ((27, 136), (86, 99)),
    ((27, 118), (86, 158)), ((27, 155), (86, 120)),
]
EXPECTED_EDGES = {(1, 2), (2, 3), (3, 4), (1, 4)}
GROUPS = [((1, 2), (3, 4)), ((1, 3), (2, 4))]
CASES = [
    (((0, 0), (28, 24)), ((0, 24), (28, 0))),
    (((0, 2), (28, 7)), ((0, 17), (28, 22))),
    (((0, 14), (16, 10)), ((16, 10), (28, 24))),
]


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def digest(path):
    return sha256(path.read_bytes()).hexdigest()


def orientation(a, b, c, eps=1e-12):
    determinant = (b[0] - a[0]) * (c[1] - a[1]) - (b[1] - a[1]) * (c[0] - a[0])
    return 0 if abs(determinant) < eps else (1 if determinant > 0 else -1)


def crosses(first, second):
    a, b = first
    c, d = second
    return (orientation(a, b, c) * orientation(a, b, d) == -1
            and orientation(c, d, a) * orientation(c, d, b) == -1)


def chord(row):
    return tuple(tuple(float(row[f"{end}_{axis}_mm"]) for axis in "xy")
                 for end in ("source", "target"))


def family(row):
    sides = "".join(sorted(row["source_side"] + row["target_side"]))
    if row["plane"] == "z1":
        return {"NS": "Z1V", "EW": "Z1H"}[sides]
    return {"EN": "Z2_NE", "ES": "Z2_SE", "NW": "Z2_NW", "SW": "Z2_SW"}[sides]


def primitive_distance(point, primitive):
    x, y = point
    x0, y0 = primitive["p0"]
    x1, y1 = primitive["p1"]
    if primitive["kind"] == "line":
        dx, dy = x1 - x0, y1 - y0
        length_sq = dx * dx + dy * dy
        t = ((x - x0) * dx + (y - y0) * dy) / length_sq if length_sq else 0
        t = max(0, min(1, t))
        return hypot(x - x0 - t * dx, y - y0 - t * dy)
    assert primitive["kind"] == "arc"
    cx, cy = primitive["center"]
    start, sweep = primitive["start_angle"], primitive["sweep"]
    angle = atan2(y - cy, x - cx)
    delta = ((angle - start) if sweep > 0 else (start - angle)) % (2 * pi)
    if delta <= abs(sweep):
        return abs(hypot(x - cx, y - cy) - primitive["radius"])
    return min(hypot(x - x0, y - y0), hypot(x - x1, y - y1))


def check_experiment(root, short, height_by_id):
    folder = root / PROGRAMME / EXPERIMENTS[short]
    assignment_path = folder / "assignment_1024.csv"
    plan_path = folder / "assignment_plan.json"
    stats_path = folder / "crossing_stats.json"
    routes_path = folder / "routes_l3d.json"
    with assignment_path.open(encoding="utf-8-sig", newline="") as source:
        rows = list(csv.DictReader(source))
    plan, stats, geometry = map(read_json, (plan_path, stats_path, routes_path))
    assert stats["routes_file_sha256"] == digest(routes_path)
    assert plan["order"] == {"E1": "port", "E3": "route_id"}[short]
    assert plan["allocation"] == FAMILIES
    assert geometry["experiment"] == stats["experiment"] == plan["experiment"] == EXPERIMENTS[short]
    assigned = {int(row["route_id"]): row for row in rows}
    routes = {int(route["route_id"]): route for route in geometry["routes"]}
    assert len(rows) == len(assigned) == len(routes) == stats["routed"] == 1024 and stats["failed"] == 0
    assert assigned.keys() == routes.keys()
    movable, frozen = [], Counter()
    for route_id, row in assigned.items():
        plane = int(row["target_layer"])
        height = float(row["target_z_mm"])
        assert isclose(height, height_by_id[plane]["z_mm"], abs_tol=1e-12)
        route = routes[route_id]
        assert (route["target_plane"], route["target_z_mm"]) == (plane, height)
        assert (route["source_endpoint"], route["target_endpoint"]) == (row["source_endpoint"], row["target_endpoint"])
        assert plan["route_planes"][str(route_id)] == plane
        if row["manual_group"].strip():
            frozen[plane] += 1
            continue
        f = family(row)
        assert plane in FAMILIES[f]
        movable.append((route_id, f, plane, chord(row)))
    assert frozen == {2: 64, 3: 64, 4: 64, 5: 64, 10: 16, 11: 16, 12: 40, 13: 40}
    assert len(movable) == 656 and len(plan["route_planes"]) == 1024 and sum(frozen.values()) == 368

    conflict_counts, cross_family = Counter(), Counter()
    for (_, fa, za, ca), (_, fb, zb, cb) in combinations(movable, 2):
        if not crosses(ca, cb):
            continue
        if fa != fb:
            cross_family[tuple(sorted((fa, fb)))] += 1
        if za == zb:
            assert fa == fb
            conflict_counts[fa] += 1
    count = sum(conflict_counts.values())
    expected = {"E1": (5835, 6803), "E3": (2273, 3275)}[short]
    assert (count, stats["totals"]["crossings"]) == expected
    assert stats["totals"]["violations"] == 0
    assert Counter(event["plane_id"] for event in stats["crossing_events"]) == {
        p["plane_id"]: p["crossings"] for p in stats["planes"] if p["crossings"]
    }

    l7 = height_by_id[7]["z_mm"]
    # Keep complete flat parts of all routes at this actual z. Transitions are
    # not planar curves. Other heights are excluded even if their XY overlaps.
    paths = {route_id: [part["primitives"] for part in route["parts"]
                        if part["kind"] == "flat" and isclose(part["z_mm"], l7, abs_tol=1e-10)]
             for route_id, route in routes.items()}
    paths = {route_id: parts for route_id, parts in paths.items() if parts}
    for route_id, parts in paths.items():
        for part in parts:
            for a, b in zip(part, part[1:]):
                assert dist(a["p1"], b["p0"]) < 1e-6, route_id
            for p in part:
                if p["kind"] == "arc":
                    for angle, endpoint in ((p["start_angle"], p["p0"]),
                                            (p["start_angle"] + p["sweep"], p["p1"])):
                        cx, cy = p["center"]
                        r = p["radius"]
                        assert dist(endpoint, (cx + r * cos(angle), cy + r * sin(angle))) < 1e-6
    events = [e for e in stats["crossing_events"] if e["plane_id"] == 7]
    assert all(e["z_mm"] == l7 for e in events)
    plane_stats = next(p for p in stats["planes"] if p["plane_id"] == 7)
    assert len(paths) == plane_stats["route_count"]
    assert len(events) == plane_stats["crossings"] == {"E1": 1102, "E3": 460}[short]
    deviation = 0.0
    for e in events:
        pt = e["x_mm"], e["y_mm"]
        assert all(0 <= v <= 150 for v in pt)
        for key in ("route_a", "route_b"):
            deviation = max(deviation, min(primitive_distance(pt, p)
                                           for part in paths[e[key]] for p in part))
    assert deviation <= stats["crossing_rule"]["sagitta_mm"] + 1e-6, deviation

    return {
        "experiment": EXPERIMENTS[short], "order": plan["order"],
        "assignment_rows": len(rows), "movable_count": len(movable), "frozen_count": sum(frozen.values()),
        "intragroup_chords": count, "intragroup_chords_by_family": dict(conflict_counts),
        "crossings_all_heights": stats["totals"]["crossings"],
        "z_mm": l7, "plane_route_count": len(paths), "plane_crossings": len(events),
        "maximum_event_to_centerline_mm": deviation,
        "crossings_by_height": {p["label"]: p["crossings"] for p in stats["planes"]},
        "source_sha256": {f.name: digest(f) for f in (assignment_path, plan_path, stats_path, routes_path)},
        "paths": paths, "events": events,
    }, cross_family, [(i, f, c) for i, f, _, c in movable]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment", type=Path, default=WORKSPACE / "OpticalWaveguideRouter2D" / EXPERIMENT)
    parser.add_argument("--report-repo", type=Path, help="Optional checkout of the cited GitHub commit")
    args = parser.parse_args()
    height_path = args.experiment / "01_height_config/height_table_20.json"
    model = read_json(height_path)
    heights = model["heights"]
    assert [h["plane_id"] for h in heights] == HEIGHT_IDS
    assert [round(h["z_mm"] * 1000) for h in heights] == list(range(-325, 626, 50))
    assert model["glass"] == {"z_min_mm": -0.35, "z_max_mm": 0.65, "thickness_mm": 1.0}
    assert sum(h["is_interface"] for h in heights) == 2
    assert sum(bool(h["manual_group"]) for h in heights) == 8
    height_by_id = {h["plane_id"]: h for h in heights}
    assert [(plane, height_by_id[plane]["z_mm"]) for plane in FAMILIES["Z1H"]] == [
        (20, -0.025), (1001, 0.025), (8, 0.075),
    ]
    assert sorted(p for planes in FAMILIES.values() for p in planes) == sorted(
        h["plane_id"] for h in heights if not h["manual_group"])

    workspace_hashes = {name: digest(HERE.parents[1] / name) for name in ORIGINAL_HASHES}
    edges = {(i, j) for (i, c1), (j, c2) in combinations(enumerate(CHORDS, 1), 2) if crosses(c1, c2)}
    assert edges == EXPECTED_EDGES
    groupsets = [[set(group) for group in partition] for partition in GROUPS]
    energies = [sum({i, j} <= group for i, j in edges for group in groups) for groups in groupsets]
    assert energies == [2, 0]
    cases = [crosses(*pair) for pair in CASES]
    assert cases == [True, False, False] and CASES[2][0][1] == CASES[2][1][0]

    evidence = {}
    family_matrices, ports = [], []
    for experiment in EXPERIMENTS:
        result, matrix, endpoints = check_experiment(args.experiment, experiment, height_by_id)
        evidence[experiment] = result
        family_matrices.append(matrix)
        ports.append(sorted(endpoints))
    assert ports[0] == ports[1] and family_matrices[0] == family_matrices[1]
    z2 = list(FAMILIES)[2:]
    matrix = [[None if a == b else family_matrices[0][tuple(sorted((a, b)))] for b in z2] for a in z2]
    assert matrix == [[None, 7264, 7264, 0], [7264, None, 0, 7264],
                      [7264, 0, None, 7264], [0, 7264, 7264, None]]
    assert family_matrices[0]["Z1H", "Z1V"] == 16384

    if args.report_repo:
        git_root = args.report_repo / EXPERIMENT
        assert digest(git_root / "01_height_config/height_table_20.json") == digest(height_path)
        for experiment, result in evidence.items():
            for name, hash_value in result["source_sha256"].items():
                if name != "routes_l3d.json":
                    assert digest(git_root / PROGRAMME / EXPERIMENTS[experiment] / name) == hash_value
        patent = args.report_repo / "专利" / HERE.parents[1].name
        assert {name: digest(patent / name) for name in ORIGINAL_HASHES} == ORIGINAL_HASHES

    data = {"source_commit": SOURCE_COMMIT, "source_patent_sha256": ORIGINAL_HASHES,
            "workspace_patent_sha256": workspace_hashes,
            "height_table_sha256": digest(height_path), "glass": model["glass"],
            "heights": heights, "families": FAMILIES, "family_matrix_z2": matrix,
            "z1_cross_family": 16384, "chords": CHORDS, "edges": sorted(edges),
            "groups": GROUPS, "energies": energies, "cases": CASES, "experiments": evidence}
    (HERE / "绘图数据.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    audit = {**data, "experiments": {k: {key: v for key, v in x.items() if key not in {"paths", "events"}}
                                   for k, x in evidence.items()}}
    (HERE.parent / "数据核验.json").write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    for key, e in evidence.items():
        print(f"{key}: intra chords={e['intragroup_chords']}; real crossings={e['crossings_all_heights']}; "
              f"L7 crossings={e['plane_crossings']}; max event/curve distance={e['maximum_event_to_centerline_mm']:.7f} mm")


if __name__ == "__main__":
    main()
