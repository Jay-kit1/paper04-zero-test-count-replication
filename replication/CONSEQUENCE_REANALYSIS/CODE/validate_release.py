#!/usr/bin/env python3
"""Validate the corrected R4.2 consequence module from a clean extraction."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from decimal import Decimal
from pathlib import Path, PurePosixPath

OBSOLETE = "SUPPORTED_TEST_" + "SOURCE_PRESENT"
ALLOWED_LITERAL_PARTS = {"SUPERSEDED_PROTOCOL_V1_0"}
ALLOWED_LITERAL_FILES = {"FAILURE_RECORD.md", "PROTOCOL_DEVIATION_LEDGER.md"}
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".py", ".sha256", ".txt", ".typ"}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path("."))
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = root / "MANIFEST.sha256"
    listed: dict[str, str] = {}
    for line in manifest.read_text(encoding="utf-8").splitlines():
        digest, rel = line.split("  ", 1)
        posix = PurePosixPath(rel)
        if posix.is_absolute() or ".." in posix.parts or rel in listed:
            raise AssertionError(f"unsafe or duplicate manifest path: {rel}")
        listed[rel] = digest
    actual = {p.relative_to(root).as_posix() for p in root.rglob("*") if p.is_file() and p != manifest}
    if set(listed) != actual:
        raise AssertionError({"missing": sorted(set(listed) - actual), "extra": sorted(actual - set(listed))})
    for rel, expected in listed.items():
        if sha(root / rel) != expected:
            raise AssertionError(f"manifest hash mismatch: {rel}")

    forbidden_hits: list[str] = []
    private_hits: list[str] = []
    secret_hits: list[str] = []
    json_errors: list[str] = []
    for path in sorted(p for p in root.rglob("*") if p.is_file()):
        rel = path.relative_to(root)
        if path.suffix.lower() == ".tsv":
            raise AssertionError(f"TSV forbidden: {rel}")
        if path.suffix.lower() in TEXT_SUFFIXES:
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if OBSOLETE in text and not (ALLOWED_LITERAL_PARTS.intersection(rel.parts) or path.name in ALLOWED_LITERAL_FILES):
                forbidden_hits.append(rel.as_posix())
            if path.name != "validate_release.py" and re.search(r"/Users/[^/\s]+/", text):
                private_hits.append(rel.as_posix())
            if re.search(r"(?:sk-[A-Za-z0-9_-]{20,}|ghp_[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16})", text):
                secret_hits.append(rel.as_posix())
        try:
            if path.suffix.lower() == ".json":
                json.loads(path.read_text(encoding="utf-8"))
            elif path.suffix.lower() == ".jsonl":
                for line in path.read_text(encoding="utf-8").splitlines():
                    if line.strip():
                        json.loads(line)
        except Exception as exc:
            json_errors.append(f"{rel}: {exc}")
    if forbidden_hits or private_hits or secret_hits or json_errors:
        raise AssertionError({"literal": forbidden_hits, "private": private_hits, "secret": secret_hits, "json": json_errors})

    repro = json.loads((root / "ANCHOR_DOWNSTREAM_REPRODUCTION_RECEIPT.json").read_text(encoding="utf-8"))
    join = json.loads((root / "ANCHOR_FRAME_JOIN_AUDIT.json").read_text(encoding="utf-8"))
    result = json.loads((root / "RESULTS" / "FULL_CONSEQUENCE_RESULTS.json").read_text(encoding="utf-8"))
    independent = json.loads((root / "INDEPENDENT_COMPACT_RECOMPUTE.json").read_text(encoding="utf-8"))
    summary = repro["summary"]
    if repro["status"] != "PASS" or summary["projects"] != 66 or summary["count_comparisons"] != 264 or summary["rate_comparisons"] != 264 or summary["count_mismatches"] != 0 or summary["rate_mismatches"] != 0 or summary["maximum_rate_absolute_difference"] != 3.3306690738754696e-16:
        raise AssertionError("anchor reproduction regression")
    matrix = join["project_matrix"]
    fields = ("supported_sample", "unresolved_sample", "negative_sample")
    totals = tuple(sum(row[field] for row in matrix) for field in fields)
    retained = [row for row in matrix if row["published_downstream_project"]]
    excluded = [row for row in matrix if not row["published_downstream_project"]]
    retained_totals = tuple(sum(row[field] for row in retained) for field in fields)
    excluded_totals = tuple(sum(row[field] for row in excluded) for field in fields)
    if join["status"] != "PASS" or join["summary"]["exactly_joined_rows"] != 3393 or totals != (82, 24, 43) or retained_totals != (51, 24, 34) or excluded_totals != (31, 0, 9):
        raise AssertionError("join/category regression")
    plugin = result["design"]["plugin_endpoints"]
    values = (
        plugin["L"]["pooled_commit_weighted"]["S"]["decimal"],
        plugin["U"]["pooled_commit_weighted"]["S"]["decimal"],
        plugin["L"]["pooled_commit_weighted"]["candidate_exclusion_share"]["decimal"],
        plugin["U"]["pooled_commit_weighted"]["candidate_exclusion_share"]["decimal"],
        plugin["L"]["pooled_commit_weighted"]["all_commits_maximum_upward_sensitivity"]["decimal"],
        plugin["U"]["pooled_commit_weighted"]["all_commits_maximum_upward_sensitivity"]["decimal"],
    )
    expected = ("162.500000000000", "539.000000000000", "0.011450516154", "0.036998901702", "0.001579325895", "0.005238502507")
    if tuple(Decimal(v) for v in values) != tuple(Decimal(v) for v in expected):
        raise AssertionError(f"consequence headline regression: {values}")
    if independent["status"] != "PASS" or independent["exact_leaves_compared"] != 1706 or independent["mismatches"]:
        raise AssertionError("independent recomputation regression")
    print(json.dumps({
        "status": "PASS", "manifest_files": len(listed), "obsolete_literal_current_hits": [],
        "category_totals_18": {"supported": 82, "unresolved": 24, "negative": 43},
        "category_totals_retained_14": {"supported": 51, "unresolved": 24, "negative": 34},
        "category_totals_excluded_4": {"supported": 31, "unresolved": 0, "negative": 9},
        "reproduction_projects": 66, "joined_frame_rows": 3393, "independent_exact_leaves": 1706,
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
