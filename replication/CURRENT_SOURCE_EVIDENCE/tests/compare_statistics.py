#!/usr/bin/env python3
"""Compare the independent statistics recomputations and release canonical projections."""

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FOLDER = ROOT / "V4_1_STATISTICS"


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main():
    a = load(FOLDER / "STATISTICS_A.json")
    b = load(FOLDER / "STATISTICS_B.json")
    a_projection = {key: value for key, value in a.items() if key != "implementation"}
    b_projection = {key: value for key, value in b.items() if key != "implementation"}
    status = "PASS" if a_projection == b_projection else "FAIL"
    comparison = {
        "schema": "PAPER04_N2_REFERENCE_V4_1_STATISTICS_COMPARISON_1_0",
        "status": status,
        "implementation_a": a["implementation"],
        "implementation_b": b["implementation"],
        "exact_projection_agreement": a_projection == b_projection,
        "category_counts_agreement": a["overall"]["category_counts"] == b["overall"]["category_counts"],
        "lopo_project_count": len(a["lopo"]),
        "sensitivity_scenario_count": len(a["clojure_canal_sensitivity"]),
        "anchor_scopes": sorted(a["anchor_partition"]),
    }
    write(FOLDER / "STATISTICS_COMPARISON.json", comparison)
    if status != "PASS":
        raise SystemExit(2)
    canonical = {**a_projection, "implementation": "CANONICAL_AFTER_EXACT_A_B_RECOMPUTATION"}
    write(FOLDER / "STATISTICS_V4_1.json", canonical)
    write(FOLDER / "LOPO.json", {"schema": "PAPER04_N2_REFERENCE_V4_1_LOPO_1_0", "records": canonical["lopo"]})
    write(FOLDER / "PROJECT_CONCENTRATION.json", {"schema": "PAPER04_N2_REFERENCE_V4_1_PROJECT_CONCENTRATION_1_0", **canonical["project_concentration"]})
    write(FOLDER / "CLOJURE_CANAL_SENSITIVITY.json", {"schema": "PAPER04_N2_REFERENCE_V4_1_CLOJURE_CANAL_SENSITIVITY_1_0", "records": canonical["clojure_canal_sensitivity"]})
    write(ROOT / "V4_1_ANCHOR_PARTITION/ANCHOR_PARTITION.json", {"schema": "PAPER04_N2_REFERENCE_V4_1_ANCHOR_PARTITION_1_0", "estimand": canonical["estimand"], "partitions": canonical["anchor_partition"]})
    overall = canonical["overall"]
    (FOLDER / "STATISTICS_SUMMARY.md").write_text(
        "# V4.1 statistics\n\n"
        "Status: `PASS_TWO_INDEPENDENT_RECOMPUTATIONS`\n\n"
        f"- Source-supported / no-supported-source / unresolved: 82 / 43 / 24\n"
        f"- Project-balanced lower / upper: {overall['lower']['project_balanced']['decimal']} / {overall['upper']['project_balanced']['decimal']}\n"
        f"- Snapshot-weighted lower / upper: {overall['lower']['snapshot_weighted']['decimal']} / {overall['upper']['snapshot_weighted']['decimal']}\n"
        "- Uncertainty: finite-population stratified-SRS design-based variance, reported separately for lower and upper endpoints.\n"
        "- LOPO: all 18 projects; project concentration, Clojure/canal sensitivity, and anchor included/excluded projections are retained in JSON artifacts.\n",
        encoding="utf-8",
    )
    print(json.dumps({"comparison": comparison, "overall": overall}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
