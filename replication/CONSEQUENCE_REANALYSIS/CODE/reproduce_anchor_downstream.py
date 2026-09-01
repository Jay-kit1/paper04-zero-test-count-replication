#!/usr/bin/env python3
"""Recompute the fixed anchor's published downstream summary from frozen CSVs.

This is a reproduction gate only.  It does not read the Paper04 audit frame or
compute any post-R4.1 consequence quantity.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd


FLOAT_ABS_TOL = 5e-15
COUNT_COLUMNS = {
    "Total Commits": "total_commits",
    "Source buildable commits": "source_buildable_commits",
    "Test buildable commits": "test_buildable_commits",
    "Fully Testable commits": "fully_testable_commits",
}
RATE_COLUMNS = {
    "FullyTestability_A": "fully_testability_a",
    "FullyTestability_T": "fully_testability_t",
    "TestabilityRate_A": "testability_rate_a",
    "TestabilityRate_T": "testability_rate_t",
}


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def div_zero_f(x: int, y: int) -> float:
    return 0.0 if x == 0 or y == 0 else x / y


def recompute_project(project: str, root: Path) -> dict:
    report_path = root / project / "report.csv"
    summary_path = root / project / "summary.csv"
    report = pd.read_csv(report_path)
    summary = pd.read_csv(summary_path)
    summary_by_commit = summary.set_index("commit").to_dict("index")

    total_commits = int(report["id"].count())
    source_buildable = int((report["build"] == "SUCCESS").sum())
    test_buildable = 0
    fully_testable = 0
    rate_a: list[float] = []
    rate_t: list[float] = []

    for _, commit in report.iterrows():
        if commit["build"] == "SUCCESS":
            test_result = summary_by_commit[commit["commit"]]
            if commit["test_build"] == "SUCCESS" and test_result["n_test"] > 0:
                test_buildable += 1
                value = float(test_result["testable_rate"])
                rate_a.append(value)
                rate_t.append(value)
                if commit["test"] == "SUCCESS":
                    fully_testable += 1
            else:
                rate_a.append(0.0)
        else:
            rate_a.append(0.0)

    return {
        "project": project,
        "input_files": {
            "report.csv": {"rows": len(report), "sha256": sha256(report_path)},
            "summary.csv": {"rows": len(summary), "sha256": sha256(summary_path)},
        },
        "total_commits": total_commits,
        "source_buildable_commits": source_buildable,
        "test_buildable_commits": test_buildable,
        "fully_testable_commits": fully_testable,
        "fully_testability_a": div_zero_f(fully_testable, total_commits),
        "fully_testability_t": div_zero_f(fully_testable, test_buildable),
        "testability_rate_a": float(pd.Series(rate_a, dtype="float64").mean()) if rate_a else 0.0,
        "testability_rate_t": float(pd.Series(rate_t, dtype="float64").mean()) if rate_t else 0.0,
        "collector_zero_success_rows": int(
            sum(
                1
                for _, commit in report.iterrows()
                if commit["build"] == "SUCCESS"
                and commit["test_build"] == "SUCCESS"
                and summary_by_commit[commit["commit"]]["n_test"] == 0
            )
        ),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--processed-root", type=Path, required=True)
    parser.add_argument("--published-csv", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    published = pd.read_csv(args.published_csv)
    rows = []
    count_mismatches = []
    rate_mismatches = []
    maximum_abs_difference = 0.0

    for _, pub in published.iterrows():
        calc = recompute_project(str(pub["Project"]), args.processed_root)
        comparisons = {}
        for column, key in COUNT_COLUMNS.items():
            published_value = int(pub[column])
            difference = calc[key] - published_value
            comparisons[column] = {
                "published": published_value,
                "recomputed": calc[key],
                "difference": difference,
                "pass": difference == 0,
            }
            if difference != 0:
                count_mismatches.append({"project": calc["project"], "column": column, "difference": difference})
        for column, key in RATE_COLUMNS.items():
            published_value = float(pub[column])
            difference = calc[key] - published_value
            abs_difference = abs(difference)
            maximum_abs_difference = max(maximum_abs_difference, abs_difference)
            comparisons[column] = {
                "published": published_value,
                "recomputed": calc[key],
                "difference": difference,
                "absolute_difference": abs_difference,
                "tolerance": FLOAT_ABS_TOL,
                "pass": abs_difference <= FLOAT_ABS_TOL,
            }
            if abs_difference > FLOAT_ABS_TOL:
                rate_mismatches.append({
                    "project": calc["project"], "column": column,
                    "difference": difference, "absolute_difference": abs_difference,
                })
        calc["comparisons"] = comparisons
        rows.append(calc)

    status = "PASS" if not count_mismatches and not rate_mismatches else "FAIL"
    payload = {
        "schema": "paper04-anchor-downstream-reproduction/1.0",
        "status": status,
        "scope": "All 66 projects in the fixed bundled Many4JResults.csv; no Paper04 consequence output was computed.",
        "published_csv": {"rows": len(published), "sha256": sha256(args.published_csv)},
        "processed_root": {
            "project_directories_used": len(rows),
            "files_used": len(rows) * 2,
        },
        "source_contract": {
            "repository_commit": "033be23df608e83621625955171fccc0db553e47",
            "notebook": "notebooks/ProjectAnalysis/TestAnalysis/01-CreateResume.ipynb",
            "cells_zero_based": [4, 5],
            "target_columns": list(COUNT_COLUMNS) + list(RATE_COLUMNS),
        },
        "runtime": {"python": __import__("sys").version.split()[0], "pandas": pd.__version__},
        "comparison_rule": {
            "counts": "exact integer equality",
            "rates": f"absolute difference <= {FLOAT_ABS_TOL:g} (binary floating-point replay tolerance)",
        },
        "summary": {
            "projects": len(rows),
            "count_comparisons": len(rows) * len(COUNT_COLUMNS),
            "rate_comparisons": len(rows) * len(RATE_COLUMNS),
            "count_mismatches": len(count_mismatches),
            "rate_mismatches": len(rate_mismatches),
            "maximum_rate_absolute_difference": maximum_abs_difference,
        },
        "count_mismatches": count_mismatches,
        "rate_mismatches": rate_mismatches,
        "projects": rows,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = [
        "# Anchor downstream reproduction receipt",
        "",
        f"Status: `{status}`",
        "",
        "This gate recomputed the fixed anchor's downstream summary from the official frozen",
        "`report.csv` and `summary.csv` files. It did not read the Paper04 audit frame and",
        "did not compute any post-R4.1 consequence quantity.",
        "",
        "## Result",
        "",
        f"- Projects reconstructed: {len(rows)}/66",
        f"- Exact integer comparisons: {len(rows) * len(COUNT_COLUMNS)}, mismatches: {len(count_mismatches)}",
        f"- Floating-rate comparisons: {len(rows) * len(RATE_COLUMNS)}, mismatches: {len(rate_mismatches)}",
        f"- Maximum absolute rate difference: `{maximum_abs_difference:.17g}`",
        f"- Replay tolerance: `{FLOAT_ABS_TOL:g}` (binary floating point)",
        "",
        "## Interpretation",
        "",
        "PASS means the exact published target and its code path are identified at the",
        "precision of the fixed CSV serialization. It does not validate the construct,",
        "reclassify any zero, or imply that a source-supported snapshot would execute or pass.",
    ]
    args.out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
