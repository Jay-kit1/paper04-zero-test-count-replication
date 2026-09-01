#!/usr/bin/env python3
"""Release V4.1 labels, canonical evidence, and the historical V3.1 transition ledger."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load(path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def by_audit(folder):
    result = {}
    for path in sorted(folder.glob("*.json")):
        row = load(path)
        result[row["audit_id"]] = row
    return result


def write_jsonl(path, rows):
    path.write_text("".join(json.dumps(row, sort_keys=True) + "\n" for row in rows), encoding="utf-8")


def main():
    comparison = load(ROOT / "V4_1_REAL_REPLAY/REAL_REPLAY_COMPARISON.json")
    assert comparison["status"] == "PASS_REAL_REPLAY"
    assert comparison["full_projection_agreement_count"] == 149
    order = load(ROOT / "V4_1_PROTOCOL_FREEZE/FROZEN_149_UNIT_ORDER_MANIFEST.json")["units"]
    a = by_audit(ROOT / "V4_1_REAL_REPLAY/RUN_A/run_1")
    b = by_audit(ROOT / "V4_1_REAL_REPLAY/RUN_B/run_1")
    old_rows = {row["audit_id"]: row for row in load_jsonl(ROOT / "V4_1_TRANSITION/N2_REFERENCE_V3_LABELS.jsonl")}
    ids = [row["audit_id"] for row in order]
    assert set(ids) == set(a) == set(b) == set(old_rows)

    evidence_folder = ROOT / "REFERENCE_V4_1_SOURCE_EVIDENCE"
    evidence_folder.mkdir(exist_ok=True)
    labels = []
    transitions = []
    matrix = Counter()
    for unit in order:
        audit_id = unit["audit_id"]
        result = a[audit_id]
        assert {key: a[audit_id][key] for key in a[audit_id] if key != "implementation_id"} == {key: b[audit_id][key] for key in b[audit_id] if key != "implementation_id"}
        evidence = {
            "schema": "PAPER04_N2_REFERENCE_V4_1_CANONICAL_EVIDENCE_1_0",
            "audit_id": audit_id,
            "snapshot_key": unit["snapshot_key"],
            "project": unit["project"],
            "category": result["category"],
            "archive": result["archive"],
            "positive_evidence": result["positive_evidence"],
            "decision_blocking_unresolved_reasons": result["decision_blocking_unresolved_reasons"],
            "nondecisive_warnings": result["nondecisive_warnings"],
            "negative_decision_completeness": result["negative_decision_completeness"],
            "implementation_a_b_exact_agreement": True,
            "v4_category_invariant": True,
        }
        (evidence_folder / f"{audit_id}.json").write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        labels.append({
            "schema": "PAPER04_N2_REFERENCE_V4_1_SOURCE_LABEL_1_0",
            "replay_index": unit["replay_index"],
            "audit_id": audit_id,
            "snapshot_key": unit["snapshot_key"],
            "project": unit["project"],
            "category": result["category"],
            "archive_sha256": result["archive"]["sha256"],
            "positive_witness_count": len(result["positive_evidence"]),
            "blocking_reason_count": len(result["decision_blocking_unresolved_reasons"]),
            "warning_count": len(result["nondecisive_warnings"]),
            "evidence_pointer": f"REFERENCE_V4_1_SOURCE_EVIDENCE/{audit_id}.json",
        })
        old = old_rows[audit_id]
        transitions.append({
            "schema": "PAPER04_N2_V3_1_TO_V4_1_SOURCE_TRANSITION_1_0",
            "replay_index": unit["replay_index"],
            "audit_id": audit_id,
            "snapshot_key": unit["snapshot_key"],
            "project": unit["project"],
            "historical_v3_1_category": old["reference_category_v3"],
            "historical_v3_1_bucket": old["reference_bucket_v3"],
            "historical_v3_1_mechanism": old.get("mechanism_v3"),
            "v4_1_source_evidence_category": result["category"],
            "transition_disposition": "PRIMARY_CONSTRUCT_SUPERSEDED_NOT_DIRECTLY_COMPARABLE",
            "mechanism_taxonomy_status": "RETIRED_FROM_PRIMARY_QUANTITATIVE_AUTHORITY",
            "historical_label_preserved": True,
            "v4_1_evidence_pointer": f"REFERENCE_V4_1_SOURCE_EVIDENCE/{audit_id}.json",
        })
        matrix[(old["reference_category_v3"], result["category"])] += 1

    write_jsonl(ROOT / "REFERENCE_V4_1_SOURCE_LABELS.jsonl", labels)
    write_jsonl(ROOT / "V3_1_TO_V4_1_SOURCE_TRANSITION_LEDGER.jsonl", transitions)
    summary = {
        "schema": "PAPER04_N2_REFERENCE_V4_1_EVIDENCE_RELEASE_SUMMARY_1_0",
        "status": "PASS",
        "label_count": len(labels),
        "evidence_count": len(list(evidence_folder.glob("*.json"))),
        "transition_count": len(transitions),
        "category_totals": dict(sorted(Counter(row["category"] for row in labels).items())),
        "historical_to_v4_1_matrix": [{"historical_v3_1_category": old, "v4_1_category": new, "units": count} for (old, new), count in sorted(matrix.items())],
        "construct_comparability": "NOT_DIRECTLY_COMPARABLE",
    }
    (ROOT / "V4_1_EVIDENCE/EVIDENCE_RELEASE_SUMMARY.json").write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (ROOT / "V4_1_EVIDENCE/EVIDENCE_RELEASE_SUMMARY.md").write_text(f"# V4.1 evidence release\n\nStatus: `PASS`\n\n- Labels: {len(labels)}\n- Evidence files: {summary['evidence_count']}\n- Transition rows: {len(transitions)}\n- Category totals: {summary['category_totals']}\n- Historical V3.1 mechanism labels are preserved but not directly comparable to the V4.1 source-evidence construct.\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
