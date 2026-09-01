#!/usr/bin/env python3
"""Independent statistics recomputation A using exact rational arithmetic."""

from __future__ import annotations

import json
import math
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SUPPORTED = "SOURCE_SUPPORTED_TEST_PRESENCE"
NEGATIVE = "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED"


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fraction_text(value):
    return f"{value.numerator}/{value.denominator}"


def decimal(value):
    return f"{float(value):.12f}"


def point(value):
    return {"fraction": fraction_text(value), "decimal": decimal(value)}


def project_groups(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[row["project"]].append(row)
    return dict(sorted(groups.items()))


def binary(row, upper):
    return int(row["category"] == SUPPORTED or (upper and row["category"] != NEGATIVE))


def metric(rows):
    groups = project_groups(rows)
    project_count = len(groups)
    frame_total = sum(group[0]["N_j"] for group in groups.values())
    estimates = {}
    for name, upper in (("lower", False), ("upper", True)):
        pb = sum((Fraction(sum(binary(row, upper) for row in group), len(group)) for group in groups.values()), Fraction()) / project_count
        weighted_total = sum(Fraction(group[0]["N_j"], len(group)) * sum(binary(row, upper) for row in group) for group in groups.values())
        sw = weighted_total / frame_total
        pb_variance = Fraction()
        sw_total_variance = Fraction()
        for group in groups.values():
            n = len(group)
            N = group[0]["N_j"]
            count = sum(binary(row, upper) for row in group)
            p = Fraction(count, n)
            sample_variance = Fraction(n, n - 1) * p * (1 - p) if n > 1 else Fraction()
            fpc = 1 - Fraction(n, N)
            pb_variance += Fraction(1, project_count * project_count) * fpc * sample_variance / n
            sw_total_variance += N * N * fpc * sample_variance / n
        sw_variance = sw_total_variance / (frame_total * frame_total)
        estimates[name] = {
            "project_balanced": uncertainty(pb, pb_variance),
            "snapshot_weighted": uncertainty(sw, sw_variance),
        }
    return {
        "project_count": project_count,
        "sample_units": len(rows),
        "frame_rows": frame_total,
        "category_counts": dict(sorted(Counter(row["category"] for row in rows).items())),
        **estimates,
    }


def uncertainty(estimate, variance):
    se = math.sqrt(float(variance))
    low = max(0.0, float(estimate) - 1.96 * se)
    high = min(1.0, float(estimate) + 1.96 * se)
    return {
        **point(estimate),
        "design_variance_fraction": fraction_text(variance),
        "standard_error_decimal": f"{se:.12f}",
        "wald_95_decimal": [f"{low:.12f}", f"{high:.12f}"],
        "uncertainty_scope": "FINITE_POPULATION_STRATIFIED_SRS_DESIGN_BASED",
    }


def simple_points(rows):
    value = metric(rows)
    return {
        "project_count": value["project_count"],
        "sample_units": value["sample_units"],
        "frame_rows": value["frame_rows"],
        "project_balanced_lower": {key: value["lower"]["project_balanced"][key] for key in ("fraction", "decimal")},
        "project_balanced_upper": {key: value["upper"]["project_balanced"][key] for key in ("fraction", "decimal")},
        "snapshot_weighted_lower": {key: value["lower"]["snapshot_weighted"][key] for key in ("fraction", "decimal")},
        "snapshot_weighted_upper": {key: value["upper"]["snapshot_weighted"][key] for key in ("fraction", "decimal")},
    }


def main():
    manifest = json.loads((ROOT / "V4_1_PROTOCOL_FREEZE/FROZEN_149_UNIT_ORDER_MANIFEST.json").read_text(encoding="utf-8"))["units"]
    labels = {row["audit_id"]: row for row in load_jsonl(ROOT / "REFERENCE_V4_1_SOURCE_LABELS.jsonl")}
    rows = [{**unit, "category": labels[unit["audit_id"]]["category"]} for unit in manifest]
    assert len(rows) == 149
    overall = metric(rows)
    projects = sorted({row["project"] for row in rows})
    lopo = [{"omitted_project": project, **simple_points([row for row in rows if row["project"] != project])} for project in projects]
    sensitivity = []
    for name, excluded in (("EXCLUDE_CLOJURE", {"clojure"}), ("EXCLUDE_CANAL", {"canal"}), ("EXCLUDE_CLOJURE_AND_CANAL", {"clojure", "canal"})):
        sensitivity.append({"scenario": name, "excluded_projects": sorted(excluded), **simple_points([row for row in rows if row["project"].casefold() not in excluded])})
    anchor = {scope: metric([row for row in rows if row["anchor_downstream_scope"] == scope]) for scope in ("INCLUDED", "EXCLUDED")}
    groups = project_groups(rows)
    supported_counts = {project: sum(row["category"] == SUPPORTED for row in group) for project, group in groups.items()}
    supported_total = sum(supported_counts.values())
    sample_hhi = Fraction(sum(count * count for count in supported_counts.values()), supported_total * supported_total)
    ht_contributions = {project: Fraction(group[0]["N_j"], len(group)) * supported_counts[project] for project, group in groups.items()}
    ht_total = sum(ht_contributions.values(), Fraction())
    ht_hhi = sum((value / ht_total) ** 2 for value in ht_contributions.values())
    concentration = {
        "sample_supported_total": supported_total,
        "sample_supported_by_project": supported_counts,
        "sample_max_project": max(supported_counts, key=lambda project: (supported_counts[project], project)),
        "sample_max_share": point(Fraction(max(supported_counts.values()), supported_total)),
        "sample_hhi": point(sample_hhi),
        "snapshot_weighted_supported_contribution_by_project": {project: point(value) for project, value in ht_contributions.items()},
        "snapshot_weighted_max_project": max(ht_contributions, key=lambda project: (ht_contributions[project], project)),
        "snapshot_weighted_max_share": point(max(ht_contributions.values()) / ht_total),
        "snapshot_weighted_hhi": point(ht_hhi),
    }
    result = {
        "schema": "PAPER04_N2_REFERENCE_V4_1_STATISTICS_1_0",
        "implementation": "STATISTICS_A_PYTHON_EXACT_RATIONAL",
        "estimand": "fraction for which collector-zero is contradicted by supported repository test-source evidence",
        "unresolved_interval_rule": "lower=unresolved_as_0; upper=unresolved_as_1",
        "overall": overall,
        "lopo": lopo,
        "project_concentration": concentration,
        "clojure_canal_sensitivity": sensitivity,
        "anchor_partition": anchor,
    }
    output = ROOT / "V4_1_STATISTICS/STATISTICS_A.json"
    output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"overall": overall, "lopo_projects": len(lopo), "sensitivity_scenarios": len(sensitivity)}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
