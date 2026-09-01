#!/usr/bin/env python3
"""Build deterministic raw archives and execute the non-vacuous V4.1 A/B gate."""

from __future__ import annotations

import gzip
import hashlib
import io
import json
import subprocess
import sys
import tarfile
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GATE = ROOT / "V4_1_SYNTHETIC_GATE"
FIXTURES = GATE / "fixtures"
REGISTRY_PATH = ROOT / "V4_1_PROTOCOL_FREEZE/REFERENCE_V4_1_FRAMEWORK_REGISTRY.json"
sys.path.insert(0, str(ROOT / "V4_1_IMPLEMENTATION_A"))
from v4a.classifier import classify_archive  # noqa: E402


PATH_B_JUNIT = "PATH_B_JUNIT_TEST_INTENT_FRAMEWORK_EVIDENCE"
PATH_B_CLOJURE = "PATH_B_CLOJURE_TEST_INTENT_FRAMEWORK_EVIDENCE"


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def add_entry(archive, root, record):
    path = f"{root}/{record['path']}"
    info = tarfile.TarInfo(path)
    info.mtime = 0
    info.uid = info.gid = 0
    info.uname = info.gname = ""
    if record.get("type") == "symlink":
        info.type = tarfile.SYMTYPE
        info.linkname = record.get("linkname", "target")
        info.mode = 0o777
        archive.addfile(info)
        return
    payload = record.get("content", "").encode("utf-8")
    info.size = len(payload)
    info.mode = 0o644
    archive.addfile(info, io.BytesIO(payload))


def write_archive(path, records):
    root = "fixture-0000000"
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.GNU_FORMAT) as archive:
        root_info = tarfile.TarInfo(root)
        root_info.type = tarfile.DIRTYPE
        root_info.mtime = 0
        root_info.mode = 0o755
        archive.addfile(root_info)
        for record in records:
            add_entry(archive, root, record)
    with path.open("wb") as stream:
        with gzip.GzipFile(filename="", mode="wb", fileobj=stream, mtime=0) as compressed:
            compressed.write(raw.getvalue())


def witness_rules(path, *rules):
    return {path: sorted(rules)}


CASES = [
    ("F01", [{"path": "src/test/java/ExampleTest.java", "content": "import org.junit.Test; class ExampleTest { @Test public void ok() {} }"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/ExampleTest.java", "STRONG_JUNIT_DECLARATION", PATH_B_JUNIT), [], []),
    ("F02", [{"path": "src/test/java/ImportOnly.java", "content": "import org.junit.Test; class ImportOnly {}"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/ImportOnly.java", PATH_B_JUNIT), [], []),
    ("F03", [{"path": "src/test/java/GoodTest.java", "content": "import org.junit.Test; class GoodTest { @Test void ok() {} }"}, {"path": "src/test/java/SuspiciousTest.java", "content": "class SuspiciousTest { void helper() {} }"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/GoodTest.java", "STRONG_JUNIT_DECLARATION", PATH_B_JUNIT), [], ["SUSPICIOUS_TEST_INTENT_WITHOUT_SUPPORTED_FRAMEWORK"]),
    ("F04", [{"path": "src/test/java/GoodTest.java", "content": "import org.junit.Test; class GoodTest { @Test void ok() {} }"}, {"path": "tests/test_extra.py", "content": "def test_extra(): pass"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/GoodTest.java", "STRONG_JUNIT_DECLARATION", PATH_B_JUNIT), [], ["UNSUPPORTED_LANGUAGE_TEST_INTENT"]),
    ("F05", [{"path": "src/test/java/GoodTest.java", "content": "import org.junit.Test; class GoodTest { @Test void ok() {} }"}, {"path": "src/test/java/SuspiciousTest.java", "content": "class SuspiciousTest {}"}, {"path": "tests/test_extra.py", "content": "def test_extra(): pass"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/GoodTest.java", "STRONG_JUNIT_DECLARATION", PATH_B_JUNIT), [], ["SUSPICIOUS_TEST_INTENT_WITHOUT_SUPPORTED_FRAMEWORK", "UNSUPPORTED_LANGUAGE_TEST_INTENT"]),
    ("F06", [{"path": "test/sample/core_test.clj", "content": "(ns sample.core-test (:require [clojure.test :refer [deftest]]))\n(deftest works (is true))"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("test/sample/core_test.clj", "STRONG_CLOJURE_DECLARATION", PATH_B_CLOJURE), [], []),
    ("F07", [{"path": "test/sample/token_only.clj", "content": "(ns sample.token-only (:require [clojure.test :as t]))\n(defn helper [] true)"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("test/sample/token_only.clj", PATH_B_CLOJURE), [], []),
    ("F08", [{"path": "src/test/clojure/clojure/test.clj", "content": "(ns clojure.test)\n(defmacro deftest [name & body] nil)"}], "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED", {}, [], []),
    ("F09", [{"path": "src/test/clojure/clojure/test.clj", "content": "(ns clojure.test)\n(defmacro deftest [name & body] nil)"}, {"path": "test/sample/real_test.clj", "content": "(ns sample.real-test (:require [clojure.test :refer [deftest]]))\n(deftest works (is true))"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("test/sample/real_test.clj", "STRONG_CLOJURE_DECLARATION", PATH_B_CLOJURE), [], []),
    ("F10", [{"path": "src/test/java/LegacyTest.java", "content": "import junit.framework.TestCase; class LegacyTest extends TestCase {}"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/LegacyTest.java", "STRONG_JUNIT_TESTCASE_INHERITANCE", PATH_B_JUNIT), [], []),
    ("F11", [{"path": "src/test/java/GoodTest.java", "content": "import org.junit.Test; class GoodTest { @Test void ok() {} }"}, {"path": "docs/current-guide", "type": "symlink", "linkname": "guide.md"}], "SOURCE_SUPPORTED_TEST_PRESENCE", witness_rules("src/test/java/GoodTest.java", "STRONG_JUNIT_DECLARATION", PATH_B_JUNIT), [], []),
    ("F12", [{"path": "src/test/java/CollisionTest.java", "content": "import org.junit.Test; class CollisionTest { @Test void a() {} }"}, {"path": "src/test/java/collisiontest.java", "content": "import org.junit.Test; class collisiontest { @Test void b() {} }"}], "SOURCE_EVIDENCE_UNRESOLVED", {}, ["DECISIVE_CASE_UNICODE_COLLISION"], []),
    ("F13", [{"path": "src/main/java/Production.java", "content": "class Production { int value = 1; }"}], "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED", {}, [], []),
    ("F14", [{"path": "src/test/java/SuspiciousTest.java", "content": "class SuspiciousTest { void helper() {} }"}], "SOURCE_EVIDENCE_UNRESOLVED", {}, ["SUSPICIOUS_TEST_INTENT_WITHOUT_SUPPORTED_FRAMEWORK"], []),
    ("F15", [{"path": "tests/test_only.py", "content": "def test_only(): pass"}], "SOURCE_EVIDENCE_UNRESOLVED", {}, ["UNSUPPORTED_LANGUAGE_TEST_INTENT"], []),
]


def validate_shape(result):
    required = {"schema", "implementation_id", "audit_id", "archive", "category", "positive_evidence", "decision_blocking_unresolved_reasons", "nondecisive_warnings", "negative_decision_completeness"}
    assert set(result) == required
    assert result["schema"] == "PAPER04_N2_REFERENCE_V4_1_SOURCE_RESULT_1_0"
    seen = set()
    for witness in result["positive_evidence"]:
        assert set(witness) == {"path", "sha256", "supporting_rules"}
        assert witness["supporting_rules"] == sorted(set(witness["supporting_rules"]))
        identity = (witness["path"], witness["sha256"])
        assert identity not in seen
        seen.add(identity)
    if result["category"] == "SOURCE_SUPPORTED_TEST_PRESENCE":
        assert result["positive_evidence"] and not result["decision_blocking_unresolved_reasons"]
    elif result["category"] == "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED":
        assert not result["positive_evidence"] and not result["decision_blocking_unresolved_reasons"] and not result["nondecisive_warnings"]
        assert all(result["negative_decision_completeness"].values())
    else:
        assert not result["positive_evidence"] and result["decision_blocking_unresolved_reasons"]


def projection(result):
    return {key: result[key] for key in ("archive", "audit_id", "category", "positive_evidence", "decision_blocking_unresolved_reasons", "nondecisive_warnings", "negative_decision_completeness")}


def main():
    FIXTURES.mkdir(parents=True, exist_ok=True)
    registry = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    manifest = []
    totals = Counter()
    for index, (case_id, members, expected_category, expected_rules, expected_blocking, expected_warnings) in enumerate(CASES, 1):
        archive = FIXTURES / f"{case_id}.tar.gz"
        write_archive(archive, members)
        payload = archive.read_bytes()
        sha256 = hashlib.sha256(payload).hexdigest()
        audit_id = f"f{index:015x}"
        args = dict(archive_path=archive, audit_id=audit_id, expected_sha256=sha256, expected_bytes=len(payload), registry=registry)
        a = classify_archive(**args)
        command = ["ruby", str(ROOT / "V4_1_IMPLEMENTATION_B/bin/classify_v4_1.rb"), "--archive", str(archive), "--audit-id", audit_id, "--expected-sha256", sha256, "--expected-bytes", str(len(payload)), "--registry", str(REGISTRY_PATH)]
        b = json.loads(subprocess.run(command, check=True, capture_output=True, text=True).stdout)
        for result in (a, b):
            validate_shape(result)
            assert result["category"] == expected_category, (case_id, result)
            assert result["decision_blocking_unresolved_reasons"] == expected_blocking, (case_id, result)
            assert result["nondecisive_warnings"] == expected_warnings, (case_id, result)
            observed_rules = {row["path"]: row["supporting_rules"] for row in result["positive_evidence"]}
            assert observed_rules == expected_rules, (case_id, observed_rules, expected_rules)
        assert projection(a) == projection(b), (case_id, a, b)
        (GATE / f"{case_id}_A.json").write_text(json.dumps(a, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        (GATE / f"{case_id}_B.json").write_text(json.dumps(b, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        totals[expected_category] += 1
        manifest.append({"case_id": case_id, "audit_id": audit_id, "archive": f"fixtures/{archive.name}", "bytes": len(payload), "sha256": sha256, "expected_category": expected_category, "expected_supporting_rules_by_path": expected_rules, "expected_blocking_reasons": expected_blocking, "expected_warnings": expected_warnings})
    report = {"schema": "PAPER04_N2_REFERENCE_V4_1_SYNTHETIC_GATE_1_0", "status": "PASS", "fixture_count": len(manifest), "implementations": ["V4.1-A", "V4.1-B"], "archive_bytes_processed": True, "a_b_exact_agreement": len(manifest), "category_totals": dict(sorted(totals.items())), "all_three_categories_exercised": len(totals) == 3, "multi_rule_witness_exercised": True, "nondecisive_warnings_exercised": True, "decision_blocking_unresolved_exercised": True, "framework_implementation_control_exercised": True, "cases": manifest}
    (GATE / "FIXTURE_MANIFEST.json").write_text(json.dumps({"schema": "PAPER04_N2_REFERENCE_V4_1_FIXTURE_MANIFEST_1_0", "fixtures": manifest}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (GATE / "SYNTHETIC_GATE_REPORT.json").write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    (GATE / "SYNTHETIC_GATE_REPORT.md").write_text(f"# V4.1 synthetic gate\n\nStatus: `PASS`\n\n- Raw fixtures: {len(manifest)}\n- A/B exact agreement: {len(manifest)} / {len(manifest)}\n- Category totals: {dict(sorted(totals.items()))}\n- Multi-rule witness, warnings, blocking ambiguity, and framework-implementation safeguards: exercised\n", encoding="utf-8")
    print(canonical({key: value for key, value in report.items() if key != "cases"}))


if __name__ == "__main__":
    main()
