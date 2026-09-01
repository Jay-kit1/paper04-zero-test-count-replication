#!/usr/bin/env python3
"""Build the unique V4.1 ZIP/sidecar and perform clean-extraction portability QA."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parents[1]
PARENT = ROOT.parent
ZIP_NAME = "PAPER04_N2_REFERENCE_V4_1_EVIDENCE_RECONCILIATION_HANDOFF.zip"
ZIP_PATH = PARENT / ZIP_NAME
SIDECAR = PARENT / f"{ZIP_NAME}.sha256"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def files():
    return sorted(path for path in ROOT.rglob("*") if path.is_file() and path.name != ".DS_Store" and path.name != "MANIFEST.sha256")


def main():
    if ZIP_PATH.exists() or SIDECAR.exists():
        raise SystemExit("refuse overwrite: final ZIP or sidecar already exists")
    manifest_lines = [f"{sha256(path)}  {path.relative_to(ROOT).as_posix()}" for path in files()]
    (ROOT / "MANIFEST.sha256").write_text("\n".join(manifest_lines) + "\n", encoding="utf-8")
    subprocess.run([sys.executable, str(ROOT / "validate_v4_1.py"), "--root", str(ROOT)], check=True)

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for path in sorted(path for path in ROOT.rglob("*") if path.is_file() and path.name != ".DS_Store"):
            archive.write(path, path.relative_to(ROOT).as_posix())
    digest = sha256(ZIP_PATH)
    SIDECAR.write_text(f"{digest}  {ZIP_NAME}\n", encoding="utf-8")

    clean_root = Path(tempfile.mkdtemp(prefix=".v4_1_portability_", dir=PARENT))
    try:
        with zipfile.ZipFile(ZIP_PATH) as archive:
            names = archive.namelist()
            unsafe = [name for name in names if PurePosixPath(name).is_absolute() or ".." in PurePosixPath(name).parts or "\\" in name]
            assert not unsafe
            assert archive.testzip() is None
            archive.extractall(clean_root)
        validation = subprocess.run([sys.executable, str(clean_root / "validate_v4_1.py"), "--root", str(clean_root)], check=True, capture_output=True, text=True)
        report = {
            "status": "PASS",
            "zip": str(ZIP_PATH),
            "sidecar": str(SIDECAR),
            "sha256": digest,
            "zip_entries": len(names),
            "unsafe_paths": 0,
            "crc": "PASS",
            "clean_extraction_validator": json.loads(validation.stdout),
        }
        print(json.dumps(report, indent=2, sort_keys=True))
    finally:
        shutil.rmtree(clean_root)


if __name__ == "__main__":
    main()
