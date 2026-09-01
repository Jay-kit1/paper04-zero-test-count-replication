"""Static, no-extraction tar.gz source-evidence classifier.

The implementation uses only Python's standard library, never materializes archive
members on disk, and never follows links. Scientific decisions are derived from the
frozen V4 registry supplied by the caller.
"""

import fnmatch
import hashlib
import io
import re
import tarfile
import unicodedata
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple


IMPLEMENTATION_ID = "REFERENCE_V4_1_IMPLEMENTATION_A_PYTHON_1_0"

REASON_ORDER = (
    "ARCHIVE_IDENTITY_FAILURE",
    "ARCHIVE_READ_FAILURE",
    "ARCHIVE_PATH_INTEGRITY_FAILURE",
    "DECISIVE_CASE_UNICODE_COLLISION",
    "DECISIVE_NONREGULAR_MEMBER",
    "SUPPORTED_SOURCE_DECODE_FAILURE",
    "SUSPICIOUS_TEST_INTENT_WITHOUT_SUPPORTED_FRAMEWORK",
    "GENERATED_TEST_SOURCE_NOT_STATICALLY_PRESENT",
    "UNSUPPORTED_LANGUAGE_TEST_INTENT",
)

GENERATION_CONFIG_NAMES = {
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "settings.gradle",
    "settings.gradle.kts",
}
GENERATION_CONFIG_SUFFIXES = {
    ".xml",
    ".gradle",
    ".sh",
    ".bash",
    ".yml",
    ".yaml",
    ".properties",
}


@dataclass(frozen=True)
class MemberRecord:
    raw_name: str
    canonical_path: str
    kind: str
    payload: Optional[bytes]
    linkname: str


def _blank_completeness() -> Dict[str, bool]:
    return {
        "archive_identity": True,
        "path_boundary": True,
        "supported_sources_decoded": True,
        "no_positive": True,
        "no_suspicious_test_intent": True,
        "no_decisive_nonregular": True,
        "no_decisive_collision": True,
        "no_generated_marker": True,
        "no_unsupported_test_intent": True,
    }


def _result(audit_id: str, digest: str, byte_count: int) -> Dict[str, Any]:
    return {
        "schema": "PAPER04_N2_REFERENCE_V4_1_SOURCE_RESULT_1_0",
        "implementation_id": IMPLEMENTATION_ID,
        "audit_id": audit_id,
        "archive": {"sha256": digest, "bytes": byte_count, "validity": "VALID"},
        "category": "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED",
        "positive_evidence": [],
        "decision_blocking_unresolved_reasons": [],
        "nondecisive_warnings": [],
        "negative_decision_completeness": _blank_completeness(),
    }


def _ordered_reasons(reasons: Iterable[str]) -> List[str]:
    order = {reason: index for index, reason in enumerate(REASON_ORDER)}
    return sorted(set(reasons), key=lambda reason: (order.get(reason, len(order)), reason))


def _strip_c_like_comments_and_literals(text: str) -> str:
    pattern = re.compile(
        r"//[^\n]*|/\*.*?\*/|\"\"\".*?\"\"\"|'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"",
        re.DOTALL,
    )
    return pattern.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def _strip_clojure_comments_and_literals(text: str) -> str:
    pattern = re.compile(r";[^\n]*|\"(?:\\.|[^\"\\])*\"")
    return pattern.sub(lambda match: "\n" * match.group(0).count("\n"), text)


def _sanitize_source(text: str, suffix: str) -> str:
    return _strip_clojure_comments_and_literals(text) if suffix == ".clj" else _strip_c_like_comments_and_literals(text)


def _has_framework(code: str, framework: str, registry: Dict[str, Any]) -> bool:
    return any(token in code for token in registry["frameworks"][framework]["tokens"])


def _frameworks_in(code: str, registry: Dict[str, Any]) -> List[str]:
    return sorted(name for name in registry["frameworks"] if _has_framework(code, name, registry))


def _strong_declaration_rules(
    canonical_path: str, suffix: str, code: str, registry: Dict[str, Any]
) -> List[str]:
    rules: List[str] = []
    canonical = registry["canonical_rule_ids"]
    if suffix == ".clj":
        own_framework_source = canonical_path.casefold().endswith("clojure/test.clj") or bool(
            re.search(r"\(ns\s+clojure\.test(?:\s|\))", code)
        )
        if own_framework_source or not _has_framework(code, "clojure", registry):
            return rules
        if re.search(r"\(\s*clojure\.test/deftest\b", code):
            rules.append(canonical["clojure_qualified_deftest"])
        elif re.search(r"\(\s*deftest\b", code):
            rules.append(canonical["clojure_deftest"])
        return rules

    if _has_framework(code, "junit", registry):
        if re.search(r"(?<![\w.])@Test\b|@org\.junit\.Test\b", code):
            rules.append(canonical["junit_at_test"])
        if re.search(r"\bextends\s+TestCase\b", code):
            rules.append(canonical["junit_testcase_inheritance"])
    if _has_framework(code, "testng", registry) and re.search(r"(?<![\w.])@Test\b", code):
        rules.append(canonical["testng_at_test"])
    if _has_framework(code, "spock", registry) and re.search(r"\bextends\s+Specification\b", code):
        rules.append(canonical["spock_specification"])
    if _has_framework(code, "scalatest", registry):
        if re.search(r"\bextends\s+AnyFunSuite\b", code):
            rules.append(canonical["scalatest_anyfunsuite_or_suite"])
        if re.search(r"\bextends\s+FunSuite\b", code):
            rules.append(canonical["scalatest_funsuite"])
        if re.search(r"\bextends\s+Suite\b", code):
            rules.append(canonical["scalatest_anyfunsuite_or_suite"])
    if _has_framework(code, "cucumber", registry):
        if re.search(r"@RunWith\s*\(\s*Cucumber\.class\s*\)", code):
            rules.append(canonical["cucumber_runner"])
        if re.search(r"@CucumberOptions\b", code):
            rules.append(canonical["cucumber_options"])
    return rules


def _canonicalize_raw_name(name: str) -> Tuple[Optional[str], bool]:
    if "\x00" in name:
        return None, False
    normalized = name.replace("\\", "/")
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:/", normalized):
        return None, False
    while normalized.startswith("./"):
        normalized = normalized[2:]
    parts: List[str] = []
    for part in normalized.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            return None, False
        parts.append(part)
    if not parts:
        return "", True
    return "/".join(parts), True


def _common_wrapper_root(raw_paths: Sequence[Tuple[str, str]]) -> Optional[str]:
    nonempty = [path for path, _kind in raw_paths if path]
    if not nonempty:
        return None
    first_segments = {path.split("/", 1)[0] for path in nonempty}
    if len(first_segments) != 1:
        return None
    root = next(iter(first_segments))
    nested = [path for path in nonempty if "/" in path]
    if not nested:
        return None
    explicit_root_directory = any(path == root and kind == "directory" for path, kind in raw_paths)
    github_style_root = bool(re.fullmatch(r".+-[0-9a-fA-F]{7,64}", root))
    return root if explicit_root_directory or github_style_root else None


def _remove_wrapper(path: str, wrapper: Optional[str]) -> str:
    if not wrapper:
        return path
    if path == wrapper:
        return ""
    prefix = wrapper + "/"
    return path[len(prefix) :] if path.startswith(prefix) else path


def _member_kind(member: tarfile.TarInfo) -> str:
    if member.isfile():
        return "regular"
    if member.isdir():
        return "directory"
    if member.issym():
        return "symlink"
    if member.islnk():
        return "hardlink"
    if member.ischr():
        return "character_device"
    if member.isblk():
        return "block_device"
    if member.isfifo():
        return "fifo"
    return "special"


def _read_members(archive_bytes: bytes) -> Tuple[List[MemberRecord], Optional[str]]:
    staged: List[Tuple[tarfile.TarInfo, str, str, Optional[bytes]]] = []
    try:
        with tarfile.open(fileobj=io.BytesIO(archive_bytes), mode="r:gz") as archive:
            for member in archive:
                raw_path, safe = _canonicalize_raw_name(member.name)
                if not safe or raw_path is None:
                    return [], "ARCHIVE_PATH_INTEGRITY_FAILURE"
                kind = _member_kind(member)
                payload: Optional[bytes] = None
                if kind == "regular":
                    stream = archive.extractfile(member)
                    payload = stream.read() if stream is not None else b""
                staged.append((member, raw_path, kind, payload))
    except (tarfile.TarError, OSError, EOFError):
        return [], "ARCHIVE_READ_FAILURE"

    wrapper = _common_wrapper_root([(path, kind) for _member, path, kind, _payload in staged])
    records: List[MemberRecord] = []
    for member, raw_path, kind, payload in staged:
        canonical = _remove_wrapper(raw_path, wrapper)
        if not canonical and kind == "directory":
            continue
        records.append(
            MemberRecord(
                raw_name=member.name,
                canonical_path=canonical,
                kind=kind,
                payload=payload,
                linkname=member.linkname or "",
            )
        )

    by_path: Dict[str, MemberRecord] = {}
    deduplicated: List[MemberRecord] = []
    for record in records:
        prior = by_path.get(record.canonical_path)
        if prior is None:
            by_path[record.canonical_path] = record
            deduplicated.append(record)
            continue
        same = prior.kind == record.kind and prior.payload == record.payload and prior.linkname == record.linkname
        if not same:
            return [], "ARCHIVE_PATH_INTEGRITY_FAILURE"
    return deduplicated, None


def _suffix(path: str) -> str:
    return PurePosixPath(path).suffix.casefold()


def _is_test_intent(path: str, registry: Dict[str, Any]) -> bool:
    parts = [part.casefold() for part in PurePosixPath(path).parts]
    if any(segment.casefold() in parts[:-1] for segment in registry["test_path_segments"]):
        return True
    filename = parts[-1] if parts else ""
    stem = PurePosixPath(filename).stem
    return any(
        fnmatch.fnmatchcase(stem, pattern.casefold()) for pattern in registry["test_filename_patterns"]
    )


def _is_generation_config(path: str) -> bool:
    filename = PurePosixPath(path).name.casefold()
    return filename in GENERATION_CONFIG_NAMES or _suffix(path) in GENERATION_CONFIG_SUFFIXES


def _is_static_generated_test_source(path: str, supported_extensions: Set[str]) -> bool:
    if _suffix(path) not in supported_extensions:
        return False
    lowered = path.casefold()
    return "generated" in lowered and "test" in lowered


def _is_decisive_path(path: str, registry: Dict[str, Any]) -> bool:
    suffix = _suffix(path)
    return (
        suffix in set(registry["supported_extensions"])
        or (suffix in set(registry["unsupported_test_extensions"]) and _is_test_intent(path, registry))
        or _is_test_intent(path, registry)
        or _is_generation_config(path)
    )


def _collision_paths(records: Sequence[MemberRecord], registry: Dict[str, Any]) -> Set[str]:
    buckets: Dict[str, Set[str]] = {}
    for record in records:
        key = unicodedata.normalize("NFC", record.canonical_path).casefold()
        buckets.setdefault(key, set()).add(record.canonical_path)
    collided: Set[str] = set()
    for paths in buckets.values():
        if len(paths) > 1 and any(_is_decisive_path(path, registry) for path in paths):
            collided.update(paths)
    return collided


def _path_b_rule(framework: str, registry: Dict[str, Any]) -> str:
    key = registry["frameworks"][framework]["path_b_rule_key"]
    return registry["canonical_rule_ids"][key]


def _is_framework_implementation_source(
    canonical_path: str, suffix: str, code: str, registry: Dict[str, Any]
) -> bool:
    if suffix != ".clj":
        return False
    safeguard = registry.get("framework_implementation_safeguards", {}).get("clojure", {})
    lowered = canonical_path.casefold()
    if any(lowered.endswith(item.casefold()) for item in safeguard.get("path_suffixes", [])):
        return True
    namespace_regex = safeguard.get("namespace_regex")
    return bool(namespace_regex and re.search(namespace_regex, code))


def classify_archive(
    archive_path: Path,
    audit_id: str,
    expected_sha256: str,
    expected_bytes: int,
    registry: Dict[str, Any],
) -> Dict[str, Any]:
    """Classify exact tar.gz bytes without extraction or link traversal."""

    archive_bytes = Path(archive_path).read_bytes()
    digest = hashlib.sha256(archive_bytes).hexdigest()
    result = _result(audit_id, digest, len(archive_bytes))
    completeness = result["negative_decision_completeness"]

    if digest != expected_sha256 or len(archive_bytes) != expected_bytes:
        result["archive"]["validity"] = "INVALID"
        result["category"] = "SOURCE_EVIDENCE_UNRESOLVED"
        result["decision_blocking_unresolved_reasons"] = ["ARCHIVE_IDENTITY_FAILURE"]
        completeness["archive_identity"] = False
        return result

    records, path_error = _read_members(archive_bytes)
    if path_error:
        result["archive"]["validity"] = "INVALID"
        result["category"] = "SOURCE_EVIDENCE_UNRESOLVED"
        result["decision_blocking_unresolved_reasons"] = [path_error]
        completeness["path_boundary"] = False
        return result

    reasons: Set[str] = set()
    collided_paths = _collision_paths(records, registry)
    if collided_paths:
        reasons.add("DECISIVE_CASE_UNICODE_COLLISION")
        completeness["no_decisive_collision"] = False
        result["archive"]["validity"] = "UNRESOLVED"

    supported_extensions = {item.casefold() for item in registry["supported_extensions"]}
    unsupported_extensions = {item.casefold() for item in registry["unsupported_test_extensions"]}
    positives_by_identity: Dict[Tuple[str, str], Set[str]] = {}
    supported_sources: List[Tuple[MemberRecord, str]] = []
    generated_marker_seen = False
    static_generated_source_seen = any(
        record.kind == "regular"
        and _is_static_generated_test_source(record.canonical_path, supported_extensions)
        for record in records
    )

    for record in records:
        if record.kind not in {"regular", "directory"}:
            if _is_decisive_path(record.canonical_path, registry):
                reasons.add("DECISIVE_NONREGULAR_MEMBER")
                completeness["no_decisive_nonregular"] = False
                result["archive"]["validity"] = "UNRESOLVED"
            continue
        if record.kind != "regular" or record.payload is None:
            continue

        suffix = _suffix(record.canonical_path)
        intent = _is_test_intent(record.canonical_path, registry)
        if suffix in unsupported_extensions and intent:
            reasons.add("UNSUPPORTED_LANGUAGE_TEST_INTENT")
            completeness["no_unsupported_test_intent"] = False

        if _is_generation_config(record.canonical_path):
            try:
                config_text = record.payload.decode("utf-8-sig")
            except UnicodeDecodeError:
                config_text = ""
            if any(marker in config_text for marker in registry["generated_markers"]):
                generated_marker_seen = True

        if suffix not in supported_extensions:
            continue
        try:
            text = record.payload.decode("utf-8-sig")
        except UnicodeDecodeError:
            reasons.add("SUPPORTED_SOURCE_DECODE_FAILURE")
            completeness["supported_sources_decoded"] = False
            continue
        code = _sanitize_source(text, suffix)
        supported_sources.append((record, code))

    if generated_marker_seen and not static_generated_source_seen:
        reasons.add("GENERATED_TEST_SOURCE_NOT_STATICALLY_PRESENT")
        completeness["no_generated_marker"] = False

    for record, code in supported_sources:
        if record.canonical_path in collided_paths:
            continue
        suffix = _suffix(record.canonical_path)
        implementation_source = _is_framework_implementation_source(
            record.canonical_path, suffix, code, registry
        )
        rules = [] if implementation_source else _strong_declaration_rules(
            record.canonical_path, suffix, code, registry
        )
        if _is_test_intent(record.canonical_path, registry) and not implementation_source:
            frameworks = _frameworks_in(code, registry)
            rules.extend(_path_b_rule(framework, registry) for framework in frameworks)
            if not rules:
                reasons.add("SUSPICIOUS_TEST_INTENT_WITHOUT_SUPPORTED_FRAMEWORK")
                completeness["no_suspicious_test_intent"] = False
        for rule in rules:
            identity = (
                unicodedata.normalize("NFC", record.canonical_path),
                hashlib.sha256(record.payload or b"").hexdigest(),
            )
            positives_by_identity.setdefault(identity, set()).add(rule)

    positives = [
        {"path": path, "sha256": sha256, "supporting_rules": sorted(rules)}
        for (path, sha256), rules in sorted(positives_by_identity.items())
    ]
    result["positive_evidence"] = positives
    completeness["no_positive"] = not bool(positives)
    ordered_reasons = _ordered_reasons(reasons)

    if positives:
        result["category"] = "SOURCE_SUPPORTED_TEST_PRESENCE"
        result["nondecisive_warnings"] = ordered_reasons
    elif reasons:
        result["category"] = "SOURCE_EVIDENCE_UNRESOLVED"
        result["decision_blocking_unresolved_reasons"] = ordered_reasons
    elif all(completeness.values()):
        result["category"] = "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED"
    else:
        result["category"] = "SOURCE_EVIDENCE_UNRESOLVED"
        result["decision_blocking_unresolved_reasons"] = ["NEGATIVE_COMPLETENESS_FAILURE"]

    return result
