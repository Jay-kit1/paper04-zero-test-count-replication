#!/usr/bin/env python3
"""Command-line entry point for one exact archive."""

import argparse
import json
import sys
from pathlib import Path


IMPLEMENTATION_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(IMPLEMENTATION_ROOT))

from v4a.classifier import classify_archive  # noqa: E402


def canonical_json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode(
        "utf-8"
    )


def parse_args():
    parser = argparse.ArgumentParser(description="Classify one exact V4 source archive without extraction")
    parser.add_argument("--archive", required=True, type=Path)
    parser.add_argument("--audit-id", required=True)
    parser.add_argument("--expected-sha256", required=True)
    parser.add_argument("--expected-bytes", required=True, type=int)
    parser.add_argument("--registry", required=True, type=Path)
    return parser.parse_args()


def main():
    args = parse_args()
    registry = json.loads(args.registry.read_text(encoding="utf-8"))
    result = classify_archive(
        archive_path=args.archive,
        audit_id=args.audit_id,
        expected_sha256=args.expected_sha256,
        expected_bytes=args.expected_bytes,
        registry=registry,
    )
    sys.stdout.buffer.write(canonical_json_bytes(result))


if __name__ == "__main__":
    main()
