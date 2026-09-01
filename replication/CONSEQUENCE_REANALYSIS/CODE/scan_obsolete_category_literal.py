#!/usr/bin/env python3
"""Fail if the retired positive-category literal survives in current material."""

from __future__ import annotations

import argparse
import json
from pathlib import Path


OBSOLETE = "SUPPORTED_TEST_" + "SOURCE_PRESENT"
TEXT_SUFFIXES = {".csv", ".json", ".jsonl", ".md", ".py", ".sha256", ".txt", ".typ"}
ALLOWED_PARTS = {"SUPERSEDED_PROTOCOL_V1_0", "SUPERSEDED_V1_0_CATEGORY_LITERAL_TYPO"}
ALLOWED_FILES = {"FAILURE_RECORD.md", "PROTOCOL_DEVIATION_LEDGER.md"}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    args = parser.parse_args()
    hits: list[str] = []
    allowed_hits: list[str] = []
    for root in args.roots:
        candidates = [root] if root.is_file() else sorted(root.rglob("*"))
        for path in candidates:
            if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if OBSOLETE not in text:
                continue
            shown = str(path.resolve())
            if ALLOWED_PARTS.intersection(path.parts) or path.name in ALLOWED_FILES:
                allowed_hits.append(shown)
            else:
                hits.append(shown)
    payload = {
        "status": "PASS" if not hits else "FAIL",
        "obsolete_literal": OBSOLETE,
        "forbidden_current_hits": hits,
        "allowed_failure_history_hits": allowed_hits,
    }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0 if not hits else 2


if __name__ == "__main__":
    raise SystemExit(main())
