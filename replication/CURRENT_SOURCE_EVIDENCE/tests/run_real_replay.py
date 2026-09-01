#!/usr/bin/env python3
"""Run the frozen 149-unit V4.1 A/B replay twice in fresh child processes."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "V4_1_PROTOCOL_FREEZE"
OUT = ROOT / "V4_1_REAL_REPLAY"
REGISTRY = PROTOCOL / "REFERENCE_V4_1_FRAMEWORK_REGISTRY.json"


def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    temporary.replace(path)


def append_progress(event):
    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / "PROGRESS.jsonl").open("a", encoding="utf-8") as stream:
        stream.write(json.dumps({"timestamp_utc": now(), **event}, sort_keys=True) + "\n")
        stream.flush()


def verify_freeze():
    freeze = load(PROTOCOL / "REFERENCE_V4_1_FREEZE.json")
    assert freeze["status"] == "FROZEN_BEFORE_REAL_REPLAY"
    assert freeze["real_replay_output_count_at_freeze"] == 0
    for record in freeze["frozen_files"]:
        path = ROOT / record["path"]
        assert path.is_file(), path
        assert path.stat().st_size == record["bytes"], path
        assert sha256(path) == record["sha256"], path
    return freeze


def load_by_audit(folder):
    result = {}
    for path in sorted(folder.glob("*.json")):
        row = load(path)
        audit_id = row["audit_id"]
        assert audit_id not in result
        result[audit_id] = row
    return result


def validate_result(row, audit_id):
    required = {"schema", "implementation_id", "audit_id", "archive", "category", "positive_evidence", "decision_blocking_unresolved_reasons", "nondecisive_warnings", "negative_decision_completeness"}
    assert set(row) == required
    assert row["schema"] == "PAPER04_N2_REFERENCE_V4_1_SOURCE_RESULT_1_0"
    assert row["audit_id"] == audit_id
    identities = []
    for witness in row["positive_evidence"]:
        assert set(witness) == {"path", "sha256", "supporting_rules"}
        assert witness["supporting_rules"] == sorted(set(witness["supporting_rules"]))
        identities.append((witness["path"], witness["sha256"]))
    assert identities == sorted(set(identities))
    if row["category"] == "SOURCE_SUPPORTED_TEST_PRESENCE":
        assert row["positive_evidence"] and not row["decision_blocking_unresolved_reasons"]
    elif row["category"] == "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED":
        assert not row["positive_evidence"] and not row["decision_blocking_unresolved_reasons"] and not row["nondecisive_warnings"]
        assert all(row["negative_decision_completeness"].values())
    elif row["category"] == "SOURCE_EVIDENCE_UNRESOLVED":
        assert not row["positive_evidence"] and row["decision_blocking_unresolved_reasons"]
    else:
        raise AssertionError(row["category"])


def projection(row):
    return {key: row[key] for key in ("archive", "audit_id", "category", "positive_evidence", "decision_blocking_unresolved_reasons", "nondecisive_warnings", "negative_decision_completeness")}


def witness_map(row):
    return {(item["path"], item["sha256"]): tuple(item["supporting_rules"]) for item in row["positive_evidence"]}


def run_command(implementation, archive, unit):
    common = ["--archive", str(archive), "--audit-id", unit["audit_id"], "--expected-sha256", unit["archive_receipt"]["expected_archive_sha256"], "--expected-bytes", str(unit["archive_receipt"]["expected_archive_bytes"]), "--registry", str(REGISTRY)]
    if implementation == "A":
        command = [sys.executable, str(ROOT / "V4_1_IMPLEMENTATION_A/bin/classify_v4_1.py"), *common]
    else:
        command = ["ruby", str(ROOT / "V4_1_IMPLEMENTATION_B/bin/classify_v4_1.rb"), *common]
    return json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-cache", required=True, type=Path)
    parser.add_argument("--v4-root", required=True, type=Path)
    args = parser.parse_args()
    freeze = verify_freeze()
    order = load(PROTOCOL / "FROZEN_149_UNIT_ORDER_MANIFEST.json")["units"]
    assert len(order) == 149
    v4 = load_by_audit(args.v4_root / "V4_REAL_REPLAY/RUN_A/run_1")
    assert set(v4) == {row["audit_id"] for row in order}

    input_records = []
    for unit in order:
        path = args.archive_cache / f"{unit['audit_id']}.tar.gz"
        expected_sha = unit["archive_receipt"]["expected_archive_sha256"]
        expected_bytes = unit["archive_receipt"]["expected_archive_bytes"]
        observed = {"audit_id": unit["audit_id"], "source_path": str(path.resolve()), "exists": path.is_file()}
        if path.is_file():
            observed.update({"bytes": path.stat().st_size, "sha256": sha256(path)})
        observed["status"] = "PASS" if path.is_file() and observed["bytes"] == expected_bytes and observed["sha256"] == expected_sha else "FAIL"
        input_records.append(observed)
    input_validation = {"schema": "PAPER04_N2_REFERENCE_V4_1_REAL_INPUT_VALIDATION_1_0", "record_count": len(input_records), "pass_count": sum(row["status"] == "PASS" for row in input_records), "records": input_records}
    atomic_json(OUT / "REAL_INPUT_IDENTITY_VALIDATION.json", input_validation)
    if input_validation["pass_count"] != 149:
        append_progress({"event": "INPUT_BLOCKED", "pass_count": input_validation["pass_count"]})
        raise SystemExit(10)

    append_progress({"event": "REPLAY_START", "freeze_projection_sha256": freeze["freeze_projection_sha256"], "units": 149})
    for implementation in ("A", "B"):
        for run_number in (1, 2):
            folder = OUT / f"RUN_{implementation}/run_{run_number}"
            folder.mkdir(parents=True, exist_ok=True)
            append_progress({"event": "RUN_START", "implementation": implementation, "run": run_number})
            for index, unit in enumerate(order, 1):
                output = folder / f"{index:03d}-{unit['audit_id']}.json"
                if output.is_file():
                    row = load(output)
                    validate_result(row, unit["audit_id"])
                else:
                    archive = args.archive_cache / f"{unit['audit_id']}.tar.gz"
                    row = run_command(implementation, archive, unit)
                    validate_result(row, unit["audit_id"])
                    atomic_json(output, row)
                if row["category"] != v4[unit["audit_id"]]["category"]:
                    atomic_json(OUT / "CATEGORY_INVARIANCE_FAILURE.json", {"schema": "PAPER04_N2_REFERENCE_V4_1_CATEGORY_INVARIANCE_FAILURE_1_0", "implementation": implementation, "run": run_number, "audit_id": unit["audit_id"], "v4_category": v4[unit["audit_id"]]["category"], "v4_1_category": row["category"]})
                    append_progress({"event": "CATEGORY_INVARIANCE_FAILURE", "implementation": implementation, "run": run_number, "index": index, "audit_id": unit["audit_id"]})
                    raise SystemExit(20)
                append_progress({"event": "UNIT_COMPLETE", "implementation": implementation, "run": run_number, "index": index, "audit_id": unit["audit_id"]})
                if index % 10 == 0 or index == 149:
                    print(f"{implementation} run {run_number}: {index}/149", flush=True)
            append_progress({"event": "RUN_COMPLETE", "implementation": implementation, "run": run_number})

    a1 = load_by_audit(OUT / "RUN_A/run_1")
    a2 = load_by_audit(OUT / "RUN_A/run_2")
    b1 = load_by_audit(OUT / "RUN_B/run_1")
    b2 = load_by_audit(OUT / "RUN_B/run_2")
    ids = [unit["audit_id"] for unit in order]
    records = []
    counts = Counter()
    for audit_id in ids:
        assert projection(a1[audit_id]) == projection(a2[audit_id])
        assert projection(b1[audit_id]) == projection(b2[audit_id])
        row = {
            "audit_id": audit_id,
            "category_agreement": a1[audit_id]["category"] == b1[audit_id]["category"],
            "witness_identity_agreement": set(witness_map(a1[audit_id])) == set(witness_map(b1[audit_id])),
            "supporting_rule_set_agreement": witness_map(a1[audit_id]) == witness_map(b1[audit_id]),
            "blocking_reason_agreement": a1[audit_id]["decision_blocking_unresolved_reasons"] == b1[audit_id]["decision_blocking_unresolved_reasons"],
            "warning_agreement": a1[audit_id]["nondecisive_warnings"] == b1[audit_id]["nondecisive_warnings"],
            "negative_completeness_agreement": a1[audit_id]["negative_decision_completeness"] == b1[audit_id]["negative_decision_completeness"],
            "full_projection_agreement": projection(a1[audit_id]) == projection(b1[audit_id]),
        }
        for key, value in row.items():
            if key != "audit_id" and value:
                counts[key] += 1
        records.append(row)
    category_totals = dict(sorted(Counter(row["category"] for row in a1.values()).items()))
    invariance = sum(a1[audit_id]["category"] == v4[audit_id]["category"] for audit_id in ids)
    if counts["category_agreement"] != 149 or invariance != 149:
        terminal = "PAPER04_N2_REFERENCE_V4_1_CATEGORY_AUTHORITY_REQUIRED"
    elif counts["warning_agreement"] != 149:
        terminal = "PAPER04_N2_REFERENCE_V4_1_WARNING_SEMANTICS_DISAGREEMENT"
    elif any(counts[key] != 149 for key in ("witness_identity_agreement", "supporting_rule_set_agreement", "blocking_reason_agreement", "negative_completeness_agreement", "full_projection_agreement")):
        terminal = "PAPER04_N2_REFERENCE_V4_1_EVIDENCE_DISAGREEMENT"
    else:
        terminal = "PASS_REAL_REPLAY"
    summary = {"schema": "PAPER04_N2_REFERENCE_V4_1_REAL_REPLAY_COMPARISON_1_0", "status": terminal, "unit_count": 149, "category_invariance_count": invariance, "implementation_a_category_totals": category_totals, "implementation_b_category_totals": dict(sorted(Counter(row["category"] for row in b1.values()).items())), "implementation_a_determinism_count": 149, "implementation_b_determinism_count": 149, **{key + "_count": counts[key] for key in sorted(counts)}, "records": records}
    atomic_json(OUT / "REAL_REPLAY_COMPARISON.json", summary)
    (OUT / "REAL_REPLAY_COMPARISON.md").write_text(f"# V4.1 real replay comparison\n\nStatus: `{terminal}`\n\n- Category invariance: {invariance} / 149\n- A/B category: {counts['category_agreement']} / 149\n- A/B witness identity: {counts['witness_identity_agreement']} / 149\n- A/B supporting rules: {counts['supporting_rule_set_agreement']} / 149\n- A/B blocking reasons: {counts['blocking_reason_agreement']} / 149\n- A/B warnings: {counts['warning_agreement']} / 149\n- A/B negative completeness: {counts['negative_completeness_agreement']} / 149\n- Category totals: {category_totals}\n", encoding="utf-8")
    append_progress({"event": "REPLAY_TERMINAL", "status": terminal})
    print(json.dumps({key: value for key, value in summary.items() if key != "records"}, indent=2, sort_keys=True))
    if terminal != "PASS_REAL_REPLAY":
        raise SystemExit(21)


if __name__ == "__main__":
    main()
