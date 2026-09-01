#!/usr/bin/env python3
"""Audit the exact anchor-row to Paper04 frame/sample/label join.

This program is deliberately result-blind with respect to the later consequence
estimand.  It validates keys, row identity, and frozen field equality only.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def index_unique(rows: list[dict], key_fn, name: str) -> dict:
    keys = [key_fn(row) for row in rows]
    duplicates = [key for key, count in Counter(keys).items() if count > 1]
    if duplicates:
        raise ValueError(f"{name} has duplicate keys: {duplicates[:5]}")
    return dict(zip(keys, rows))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--frame", type=Path, required=True)
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--processed-root", type=Path, required=True)
    parser.add_argument("--published-csv", type=Path, required=True)
    parser.add_argument("--out-ledger", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    frame = read_jsonl(args.frame)
    sample_payload = json.loads(args.sample.read_text(encoding="utf-8"))
    sample = sample_payload["selected"]
    labels = read_jsonl(args.labels)
    frame_idx = index_unique(frame, lambda r: (r["project"], r["snapshot"]), "frame")
    sample_idx = index_unique(sample, lambda r: (r["project"], r["snapshot"]), "sample")
    label_idx = index_unique(labels, lambda r: (r["project"], r["snapshot_key"]), "labels")

    published_rows = list(csv.DictReader(args.published_csv.open(newline="", encoding="utf-8-sig")))
    published_projects = {row["Project"] for row in published_rows}
    projects = sorted({row["project"] for row in frame})
    anchor = {}
    anchor_project_receipts = {}
    duplicate_anchor_keys = []

    for project in projects:
        report_path = args.processed_root / project / "report.csv"
        summary_path = args.processed_root / project / "summary.csv"
        report_rows = list(csv.DictReader(report_path.open(newline="", encoding="utf-8-sig")))
        summary_rows = list(csv.DictReader(summary_path.open(newline="", encoding="utf-8-sig")))
        report_counts = Counter(row["commit"] for row in report_rows)
        summary_counts = Counter(row["commit"] for row in summary_rows)
        duplicate_anchor_keys.extend(
            {"project": project, "table": table, "commit": commit, "count": count}
            for table, counts in (("report", report_counts), ("summary", summary_counts))
            for commit, count in counts.items() if count > 1
        )
        report_idx = {row["commit"]: row for row in report_rows}
        summary_idx = {row["commit"]: row for row in summary_rows}
        anchor_project_receipts[project] = {
            "report_rows": len(report_rows),
            "summary_rows": len(summary_rows),
            "report_sha256": sha256(report_path),
            "summary_sha256": sha256(summary_path),
            "published_downstream_project": project in published_projects,
        }
        anchor[project] = (report_idx, summary_idx)

    unmatched_report = []
    unmatched_summary = []
    frozen_field_mismatches = []
    sampled_missing_frame = []
    sampled_label_mismatches = []
    ledger = []

    for key, row in sorted(frame_idx.items()):
        project, snapshot = key
        report_idx, summary_idx = anchor[project]
        report = report_idx.get(snapshot)
        summary = summary_idx.get(snapshot)
        if report is None:
            unmatched_report.append({"project": project, "snapshot": snapshot})
            continue
        if summary is None:
            unmatched_summary.append({"project": project, "snapshot": snapshot})
            continue

        checks = {
            "published_build": (row["published_build"], report["build"]),
            "published_test_build": (row["published_test_build"], report["test_build"]),
            "published_test": (row["published_test"], report["test"]),
            "processed_n_test": (int(row["processed_n_test"]), int(float(summary["n_test"]))),
        }
        for field, (frame_value, anchor_value) in checks.items():
            if frame_value != anchor_value:
                frozen_field_mismatches.append({
                    "project": project, "snapshot": snapshot, "field": field,
                    "frame": frame_value, "anchor": anchor_value,
                })

        sample_row = sample_idx.get(key)
        label = None
        if sample_row is not None:
            label = label_idx.get((project, sample_row["snapshot_key"]))
            if label is None:
                sampled_label_mismatches.append({
                    "project": project, "snapshot": snapshot,
                    "snapshot_key": sample_row["snapshot_key"], "reason": "LABEL_MISSING",
                })
        ledger.append({
            "project": project,
            "snapshot": snapshot,
            "anchor_report_id": report["id"],
            "anchor_summary_id": summary["id"],
            "anchor_report_summary_commit_equal": report["commit"] == summary["commit"] == snapshot,
            "frozen_fields_equal": all(a == b for a, b in checks.values()),
            "published_downstream_project": project in published_projects,
            "sampled": sample_row is not None,
            "sample_snapshot_key": sample_row["snapshot_key"] if sample_row else None,
            "reference_category": label["category"] if label else None,
        })

    for key, sample_row in sorted(sample_idx.items()):
        if key not in frame_idx:
            sampled_missing_frame.append({"project": key[0], "snapshot": key[1]})
        label = label_idx.get((sample_row["project"], sample_row["snapshot_key"]))
        if label is not None and label["project"] != sample_row["project"]:
            sampled_label_mismatches.append({
                "project": sample_row["project"], "snapshot": sample_row["snapshot"],
                "reason": "LABEL_PROJECT_MISMATCH",
            })

    project_matrix = []
    by_project_frame = Counter(row["project"] for row in frame)
    by_project_sample = Counter(row["project"] for row in sample)
    by_project_ledger = defaultdict(list)
    for row in ledger:
        by_project_ledger[row["project"]].append(row)
    for project in projects:
        rows = by_project_ledger[project]
        project_matrix.append({
            "project": project,
            "frame_rows": by_project_frame[project],
            "sample_rows": by_project_sample[project],
            "published_downstream_project": project in published_projects,
            "exactly_joined_rows": len(rows),
            "supported_sample": sum(r["reference_category"] == "SOURCE_SUPPORTED_TEST_PRESENCE" for r in rows),
            "negative_sample": sum(r["reference_category"] == "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED" for r in rows),
            "unresolved_sample": sum(r["reference_category"] == "SOURCE_EVIDENCE_UNRESOLVED" for r in rows),
        })

    failures = {
        "duplicate_anchor_keys": duplicate_anchor_keys,
        "unmatched_report": unmatched_report,
        "unmatched_summary": unmatched_summary,
        "frozen_field_mismatches": frozen_field_mismatches,
        "sampled_missing_frame": sampled_missing_frame,
        "sampled_label_mismatches": sampled_label_mismatches,
    }
    status = "PASS" if all(not value for value in failures.values()) and len(ledger) == len(frame) else "FAIL"
    payload = {
        "schema": "paper04-anchor-frame-join-audit/1.0",
        "status": status,
        "join_key": ["project", "exact commit/snapshot string"],
        "heuristic_matching": False,
        "inputs": {
            "frame": {"rows": len(frame), "sha256": sha256(args.frame)},
            "sample": {"rows": len(sample), "sha256": sha256(args.sample)},
            "labels": {"rows": len(labels), "sha256": sha256(args.labels)},
            "published_csv": {"rows": len(published_rows), "sha256": sha256(args.published_csv)},
            "anchor_projects": anchor_project_receipts,
        },
        "summary": {
            "frame_projects": len(projects),
            "frame_rows": len(frame),
            "exactly_joined_rows": len(ledger),
            "sample_rows": len(sample),
            "label_rows": len(labels),
            "published_downstream_overlap_projects": sum(p in published_projects for p in projects),
            "pre_filter_only_projects": sum(p not in published_projects for p in projects),
            "published_downstream_overlap_frame_rows": sum(
                count for project, count in by_project_frame.items() if project in published_projects
            ),
            "pre_filter_only_frame_rows": sum(
                count for project, count in by_project_frame.items() if project not in published_projects
            ),
        },
        "failures": failures,
        "project_matrix": project_matrix,
    }

    args.out_ledger.parent.mkdir(parents=True, exist_ok=True)
    with args.out_ledger.open("w", encoding="utf-8") as stream:
        for row in ledger:
            stream.write(json.dumps(row, sort_keys=True) + "\n")
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    md = [
        "# Anchor-frame join audit",
        "",
        f"Status: `{status}`",
        "",
        "The join uses exact `(project, commit/snapshot)` strings. No prefix, date, fuzzy,",
        "case-folded, or heuristic matching is permitted.",
        "",
        "## Gate summary",
        "",
        f"- Frame rows joined: {len(ledger)}/{len(frame)}",
        f"- Sample rows linked to frame and V4.1 labels: {len(sample)}/{len(sample)}",
        f"- Frozen field mismatches: {len(frozen_field_mismatches)}",
        f"- Duplicate anchor keys: {len(duplicate_anchor_keys)}",
        f"- Published-downstream overlap: {sum(p in published_projects for p in projects)} projects, "
        f"{sum(count for project, count in by_project_frame.items() if project in published_projects)} frame rows",
        f"- Pre-filter-only subset: {sum(p not in published_projects for p in projects)} projects, "
        f"{sum(count for project, count in by_project_frame.items() if project not in published_projects)} frame rows",
        "",
        "PASS identifies the row mapping only. It does not equate source support with runtime",
        "success and does not itself define or calculate a consequence estimand.",
    ]
    args.out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps(payload["summary"], indent=2))
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
