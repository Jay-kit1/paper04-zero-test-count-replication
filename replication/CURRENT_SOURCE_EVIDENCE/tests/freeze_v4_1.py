#!/usr/bin/env python3
"""Freeze V4.1 protocol, implementations, fixtures, and real-input identity before replay."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PROTOCOL = ROOT / "V4_1_PROTOCOL_FREEZE"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def records(paths):
    return [{"path": str(path.relative_to(ROOT)), "bytes": path.stat().st_size, "sha256": digest(path)} for path in sorted(paths)]


def source_files(folder):
    return [path for path in folder.rglob("*") if path.is_file() and "__pycache__" not in path.parts and path.suffix in {".py", ".rb"}]


def main():
    real_files = [path for path in (ROOT / "V4_1_REAL_REPLAY").rglob("*") if path.is_file()]
    if real_files:
        raise SystemExit("refuse freeze: V4.1 real replay outputs already exist")

    order = json.loads((PROTOCOL / "FROZEN_149_UNIT_ORDER_MANIFEST.json").read_text(encoding="utf-8"))
    registry = json.loads((PROTOCOL / "REFERENCE_V4_1_FRAMEWORK_REGISTRY.json").read_text(encoding="utf-8"))
    framework_vocabulary = {name.casefold() for name in registry["frameworks"]}
    project_names = sorted(
        {row["project"] for row in order["units"] if row["project"].casefold() not in framework_vocabulary},
        key=lambda value: (-len(value), value),
    )
    scan_targets = source_files(ROOT / "V4_1_IMPLEMENTATION_A") + source_files(ROOT / "V4_1_IMPLEMENTATION_B") + [
        PROTOCOL / "REFERENCE_V4_1_FRAMEWORK_REGISTRY.json",
        PROTOCOL / "REFERENCE_V4_1_EVIDENCE_SCHEMA.json",
        PROTOCOL / "REFERENCE_V4_1_COMPARISON_CONTRACT.json",
    ]
    prohibited_literals = ["V3_1", "V3.1", "Stage03", "STAGE03", "82 / 43 / 24", "82/43/24"]
    findings = []
    for path in scan_targets:
        text = path.read_text(encoding="utf-8")
        for literal in prohibited_literals:
            if literal in text:
                findings.append({"path": str(path.relative_to(ROOT)), "kind": "PROHIBITED_LITERAL", "literal": literal})
        for project in project_names:
            if project.casefold() in text.casefold():
                findings.append({"path": str(path.relative_to(ROOT)), "kind": "PROJECT_NAME", "literal": project})
    scan = {"schema": "PAPER04_N2_REFERENCE_V4_1_PROHIBITED_CONTEXT_SCAN_1_0", "status": "PASS" if not findings else "FAIL", "target_count": len(scan_targets), "project_name_dictionary_count": len(project_names), "forbidden_classes": ["project-specific rules", "expected category counts", "V3.1 labels", "manuscript results", "Stage03 outcomes"], "findings": findings}
    (PROTOCOL / "PROHIBITED_CONTEXT_SCAN.json").write_text(json.dumps(scan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if findings:
        raise SystemExit("prohibited-context scan failed")

    for label in ("A", "B"):
        folder = ROOT / f"V4_1_IMPLEMENTATION_{label}"
        manifest = {"schema": f"PAPER04_N2_REFERENCE_V4_1_IMPLEMENTATION_{label}_FREEZE_1_0", "implementation": f"V4.1-{label}", "files": records(source_files(folder))}
        manifest["source_tree_sha256"] = hashlib.sha256((json.dumps(manifest["files"], sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
        (folder / "IMPLEMENTATION_FREEZE.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    protocol_files = [
        PROTOCOL / "REFERENCE_V4_1_EVIDENCE_SCHEMA.json",
        PROTOCOL / "REFERENCE_V4_1_EVIDENCE_SEMANTICS.md",
        PROTOCOL / "REFERENCE_V4_1_FRAMEWORK_REGISTRY.json",
        PROTOCOL / "REFERENCE_V4_1_COMPARISON_CONTRACT.json",
        PROTOCOL / "FROZEN_149_UNIT_ORDER_MANIFEST.json",
        PROTOCOL / "FROZEN_149_ARCHIVE_IDENTITY_LEDGER.json",
        PROTOCOL / "PAPER04_N2_REFERENCE_V4_1_AUTHORITY_PROMPT.md",
        PROTOCOL / "PROHIBITED_CONTEXT_SCAN.json",
        ROOT / "V4_1_IMPLEMENTATION_A/IMPLEMENTATION_FREEZE.json",
        ROOT / "V4_1_IMPLEMENTATION_B/IMPLEMENTATION_FREEZE.json",
        ROOT / "V4_1_SYNTHETIC_GATE/FIXTURE_MANIFEST.json",
        ROOT / "V4_1_SYNTHETIC_GATE/SYNTHETIC_GATE_REPORT.json",
    ]
    fixture_files = [path for path in (ROOT / "V4_1_SYNTHETIC_GATE/fixtures").glob("*.tar.gz")]
    frozen = records(protocol_files + fixture_files)
    freeze = {
        "schema": "PAPER04_N2_REFERENCE_V4_1_FREEZE_1_0",
        "status": "FROZEN_BEFORE_REAL_REPLAY",
        "created_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
        "frozen_file_count": len(frozen),
        "frozen_files": frozen,
        "unit_count": len(order["units"]),
        "synthetic_fixture_count": len(fixture_files),
        "real_replay_output_count_at_freeze": 0,
        "prohibited_context_scan": "PASS",
    }
    freeze["freeze_projection_sha256"] = hashlib.sha256((json.dumps(frozen, sort_keys=True, separators=(",", ":")) + "\n").encode()).hexdigest()
    (PROTOCOL / "REFERENCE_V4_1_FREEZE.json").write_text(json.dumps(freeze, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({key: value for key, value in freeze.items() if key != "frozen_files"}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
