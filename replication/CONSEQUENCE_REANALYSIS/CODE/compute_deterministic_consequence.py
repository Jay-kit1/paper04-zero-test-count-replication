#!/usr/bin/env python3
"""Primary exact-rational Paper04 deterministic consequence computation."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from fractions import Fraction
from pathlib import Path

SUPPORTED = "SOURCE_SUPPORTED_TEST_PRESENCE"
UNRESOLVED = "SOURCE_EVIDENCE_UNRESOLVED"
NEGATIVE = "NO_SUPPORTED_TEST_SOURCE_IDENTIFIED"
INCLUDED = [
    "Bukkit", "CoreNLP", "DiskLruCache", "alluxio", "android-volley",
    "ansj_seg", "graylog2-server", "guava", "java-design-patterns",
    "javaee7-samples", "javapoet", "nanohttpd", "presto", "webmagic",
]
FAMILY_ALPHA = Fraction(1, 20)
PER_PROJECT_ALPHA = Fraction(1, 280)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_jsonl(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as stream:
        return [json.loads(line) for line in stream if line.strip()]


def frac(value) -> Fraction:
    return value if isinstance(value, Fraction) else Fraction(str(value))


def render(value: Fraction | None) -> dict | None:
    if value is None:
        return None
    return {"fraction": str(value), "decimal": f"{float(value):.12f}"}


def exact_population_interval(N: int, n: int, k: int) -> tuple[int, int]:
    """Equal-tailed hypergeometric inversion with exact rational tails."""
    denominator = math.comb(N, n)
    tail = PER_PROJECT_ALPHA / 2

    def probability(K: int, x: int) -> Fraction:
        if x < 0 or x > n or x > K or n - x > N - K:
            return Fraction(0)
        return Fraction(math.comb(K, x) * math.comb(N - K, n - x), denominator)

    candidates = []
    for K in range(N + 1):
        if K < k or N - K < n - k:
            continue
        lower = sum((probability(K, x) for x in range(0, k + 1)), Fraction(0))
        upper = sum((probability(K, x) for x in range(k, n + 1)), Fraction(0))
        if lower >= tail and upper >= tail:
            candidates.append(K)
    if not candidates:
        raise RuntimeError(f"empty exact confidence set N={N}, n={n}, k={k}")
    return min(candidates), max(candidates)


def scenario(C: int, K: int, A: Fraction, T: Fraction, S: Fraction) -> dict:
    if S < 0 or K + S > C:
        raise ValueError(f"invalid candidate count C={C} K={K} S={S}")
    expanded = Fraction(K, 1) + S
    exclusion = S / expanded if expanded else None
    coverage = expanded / C
    a_upper = A + S / C
    if a_upper > 1:
        raise ValueError(f"all-commits envelope exceeds 1: {a_upper}")
    if expanded:
        t_lower = Fraction(K, 1) * T / expanded
        t_upper = (Fraction(K, 1) * T + S) / expanded
    else:
        t_lower = t_upper = None
    return {
        "S": render(S),
        "expanded_positive_row_coverage": render(coverage),
        "candidate_exclusion_share": render(exclusion),
        "all_commits_rate_envelope": {"lower": render(A), "upper": render(a_upper)},
        "all_commits_maximum_upward_sensitivity": render(S / C),
        "positive_parsed_test_rate_envelope": {
            "lower": render(t_lower), "upper": render(t_upper),
            "defined": expanded > 0,
        },
    }


def mean_defined(values: list[Fraction | None]) -> tuple[Fraction | None, int]:
    defined = [x for x in values if x is not None]
    return (sum(defined, Fraction(0)) / len(defined), len(defined)) if defined else (None, 0)


def aggregate(projects: list[dict], selector) -> dict:
    selected = [(row, frac(selector(row))) for row in projects]
    C = sum(row["C"] for row, _ in selected)
    K = sum(row["K"] for row, _ in selected)
    S = sum((value for _, value in selected), Fraction(0))
    A_num = sum((row["A"] * row["C"] for row, _ in selected), Fraction(0))
    T_num = sum((row["T"] * row["K"] for row, _ in selected), Fraction(0))
    pooled_A = A_num / C
    pooled_T = T_num / K if K else Fraction(0)
    pooled = scenario(C, K, pooled_A, pooled_T, S)
    per = [scenario(row["C"], row["K"], row["A"], row["T"], value) for row, value in selected]
    fields = {
        "additional_count": [value for _, value in selected],
        "expanded_positive_row_coverage": [frac(x["expanded_positive_row_coverage"]["fraction"]) for x in per],
        "candidate_exclusion_share": [
            frac(x["candidate_exclusion_share"]["fraction"]) if x["candidate_exclusion_share"] else None for x in per
        ],
        "all_commits_maximum_upward_sensitivity": [
            frac(x["all_commits_maximum_upward_sensitivity"]["fraction"]) for x in per
        ],
        "positive_parsed_test_rate_lower": [
            frac(x["positive_parsed_test_rate_envelope"]["lower"]["fraction"])
            if x["positive_parsed_test_rate_envelope"]["lower"] else None for x in per
        ],
        "positive_parsed_test_rate_upper": [
            frac(x["positive_parsed_test_rate_envelope"]["upper"]["fraction"])
            if x["positive_parsed_test_rate_envelope"]["upper"] else None for x in per
        ],
    }
    balanced = {}
    for name, values in fields.items():
        value, count = mean_defined(values)
        balanced[name] = {"value": render(value), "contributing_projects": count}
    return {
        "project_balanced": balanced,
        "pooled_commit_weighted": {
            "C": C, "K": K, "S": render(S),
            "published_A": render(pooled_A), "published_T": render(pooled_T),
            **pooled,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--sample", type=Path, required=True)
    parser.add_argument("--labels", type=Path, required=True)
    parser.add_argument("--published-csv", type=Path, required=True)
    parser.add_argument("--protocol", type=Path, required=True)
    parser.add_argument("--reproduction", type=Path, required=True)
    parser.add_argument("--join-audit", type=Path, required=True)
    parser.add_argument("--out-json", type=Path, required=True)
    parser.add_argument("--out-csv", type=Path, required=True)
    parser.add_argument("--out-md", type=Path, required=True)
    args = parser.parse_args()

    protocol = json.loads(args.protocol.read_text(encoding="utf-8"))
    reproduction = json.loads(args.reproduction.read_text(encoding="utf-8"))
    join_audit = json.loads(args.join_audit.read_text(encoding="utf-8"))
    if protocol["status"] != "FROZEN_BEFORE_CONSEQUENCE_COMPUTATION":
        raise SystemExit("protocol not frozen")
    if reproduction["status"] != "PASS" or join_audit["status"] != "PASS":
        raise SystemExit("upstream gate not PASS")
    if protocol["population"]["included_projects"] != INCLUDED:
        raise SystemExit("included-project order differs from freeze")

    sample = json.loads(args.sample.read_text(encoding="utf-8"))["selected"]
    labels = read_jsonl(args.labels)
    labels_by_key = {(x["project"], x["snapshot_key"]): x for x in labels}
    grouped = defaultdict(list)
    for unit in sample:
        label = labels_by_key[(unit["project"], unit["snapshot_key"])]
        grouped[unit["project"]].append({**unit, "category": label["category"]})

    published_raw = list(csv.DictReader(args.published_csv.open(newline="", encoding="utf-8-sig")))
    published = {row["Project"]: row for row in published_raw}
    project_records = []
    internal = []
    for project in INCLUDED:
        group = grouped[project]
        counts = Counter(row["category"] for row in group)
        N = int(group[0]["N_j"])
        n = int(group[0]["n_j"])
        s, u, z = counts[SUPPORTED], counts[UNRESOLVED], counts[NEGATIVE]
        pub = published[project]
        C = int(pub["Total Commits"])
        K = int(pub["Test buildable commits"])
        A = Fraction(pub["TestabilityRate_A"])
        T = Fraction(pub["TestabilityRate_T"])
        if len(group) != n or s + u + z != n or N > C - K:
            raise SystemExit(f"invalid frozen counts for {project}")

        plugin_L = Fraction(N * s, n)
        plugin_U = Fraction(N * (s + u), n)
        ci_L = exact_population_interval(N, n, s)
        ci_U = exact_population_interval(N, n, s + u)
        worst_L = (s, N - n + s)
        worst_U = (s + u, N - z)
        exact_counts = {
            "plugin_L": plugin_L, "plugin_U": plugin_U,
            "ci_L_lower": Fraction(ci_L[0]), "ci_L_upper": Fraction(ci_L[1]),
            "ci_U_lower": Fraction(ci_U[0]), "ci_U_upper": Fraction(ci_U[1]),
            "worst_L_lower": Fraction(worst_L[0]), "worst_L_upper": Fraction(worst_L[1]),
            "worst_U_lower": Fraction(worst_U[0]), "worst_U_upper": Fraction(worst_U[1]),
        }
        scenarios = {name: scenario(C, K, A, T, value) for name, value in exact_counts.items()}
        project_records.append({
            "project": project, "C": C, "K": K, "N": N, "n": n,
            "sample_supported": s, "sample_unresolved": u, "sample_negative": z,
            "published": {"TestabilityRate_A": render(A), "TestabilityRate_T": render(T)},
            "candidate_counts": {name: render(value) for name, value in exact_counts.items()},
            "scenarios": scenarios,
        })
        internal.append({
            "project": project, "C": C, "K": K, "N": N, "n": n,
            "s": s, "u": u, "z": z, "A": A, "T": T, **exact_counts,
        })

    plugin = {
        "L": aggregate(internal, lambda r: r["plugin_L"]),
        "U": aggregate(internal, lambda r: r["plugin_U"]),
    }
    interval_aggregates = {}
    for family in ("ci_L", "ci_U", "worst_L", "worst_U"):
        interval_aggregates[family] = {
            "lower": aggregate(internal, lambda r, f=family: r[f + "_lower"]),
            "upper": aggregate(internal, lambda r, f=family: r[f + "_upper"]),
        }

    payload = {
        "schema": "paper04-deterministic-consequence-results/1.0",
        "status": "PAPER04_N2_DETERMINISTIC_CONSEQUENCE_REANALYSIS_PASS",
        "authority_boundary": {
            "runtime_outcomes_identified": False,
            "source_support_equals_execution": False,
            "corrected_rate_claimed": False,
            "r4_1_authority": "UNCHANGED_PENDING_ADJUDICATION",
        },
        "input_hashes": {
            "protocol": sha256(args.protocol), "sample": sha256(args.sample),
            "labels": sha256(args.labels), "published_csv": sha256(args.published_csv),
            "reproduction": sha256(args.reproduction), "join_audit": sha256(args.join_audit),
        },
        "scope": {
            "projects": len(INCLUDED),
            "collector_zero_frame_rows": sum(row["N"] for row in internal),
            "sample_units": sum(row["n"] for row in internal),
        },
        "design": {
            "plugin_endpoints": plugin,
            "simultaneous_exact_method": {
                "family_alpha": str(FAMILY_ALPHA),
                "per_project_alpha": str(PER_PROJECT_ALPHA),
                "coverage": "separate Bonferroni family-wise coverage for L and U; no joint L/U claim",
            },
            "interval_aggregates": interval_aggregates,
        },
        "projects": project_records,
    }
    args.out_json.parent.mkdir(parents=True, exist_ok=True)
    args.out_json.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    with args.out_csv.open("w", newline="", encoding="utf-8") as stream:
        fields = [
            "project", "C_total_commits", "K_positive_parsed_rows", "N_collector_zero_rows",
            "n_sample", "supported", "unresolved", "negative",
            "published_TestabilityRate_A", "published_TestabilityRate_T",
            "plugin_S_L", "plugin_S_U", "plugin_exclusion_share_L", "plugin_exclusion_share_U",
            "plugin_A_max_shift_L", "plugin_A_max_shift_U",
            "plugin_T_lower_L", "plugin_T_upper_L", "plugin_T_lower_U", "plugin_T_upper_U",
        ]
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for row in project_records:
            scL, scU = row["scenarios"]["plugin_L"], row["scenarios"]["plugin_U"]
            writer.writerow({
                "project": row["project"], "C_total_commits": row["C"],
                "K_positive_parsed_rows": row["K"], "N_collector_zero_rows": row["N"],
                "n_sample": row["n"], "supported": row["sample_supported"],
                "unresolved": row["sample_unresolved"], "negative": row["sample_negative"],
                "published_TestabilityRate_A": row["published"]["TestabilityRate_A"]["decimal"],
                "published_TestabilityRate_T": row["published"]["TestabilityRate_T"]["decimal"],
                "plugin_S_L": scL["S"]["decimal"], "plugin_S_U": scU["S"]["decimal"],
                "plugin_exclusion_share_L": scL["candidate_exclusion_share"]["decimal"] if scL["candidate_exclusion_share"] else "UNDEFINED",
                "plugin_exclusion_share_U": scU["candidate_exclusion_share"]["decimal"] if scU["candidate_exclusion_share"] else "UNDEFINED",
                "plugin_A_max_shift_L": scL["all_commits_maximum_upward_sensitivity"]["decimal"],
                "plugin_A_max_shift_U": scU["all_commits_maximum_upward_sensitivity"]["decimal"],
                "plugin_T_lower_L": scL["positive_parsed_test_rate_envelope"]["lower"]["decimal"] if scL["positive_parsed_test_rate_envelope"]["lower"] else "UNDEFINED",
                "plugin_T_upper_L": scL["positive_parsed_test_rate_envelope"]["upper"]["decimal"] if scL["positive_parsed_test_rate_envelope"]["upper"] else "UNDEFINED",
                "plugin_T_lower_U": scU["positive_parsed_test_rate_envelope"]["lower"]["decimal"] if scU["positive_parsed_test_rate_envelope"]["lower"] else "UNDEFINED",
                "plugin_T_upper_U": scU["positive_parsed_test_rate_envelope"]["upper"]["decimal"] if scU["positive_parsed_test_rate_envelope"]["upper"] else "UNDEFINED",
            })

    def d(path: list[str], endpoint="L") -> str:
        value = plugin[endpoint]
        for part in path:
            value = value[part]
        return value["decimal"]

    md = [
        "# Deterministic consequence reanalysis results",
        "",
        "Status: `PAPER04_N2_DETERMINISTIC_CONSEQUENCE_REANALYSIS_PASS`",
        "",
        "Scope: 14 downstream-retained projects, 1,114 exact collector-zero rows,",
        "and 109 frozen sample units. Runtime outcomes remain unidentified.",
        "",
        "## Primary denominator sensitivity",
        "",
        "Under the frozen design-based plug-in calculation:",
        "",
        f"- Pooled candidate exclusion share, supported-only endpoint: {d(['pooled_commit_weighted','candidate_exclusion_share'], 'L')}",
        f"- Pooled candidate exclusion share, supported-or-unresolved endpoint: {d(['pooled_commit_weighted','candidate_exclusion_share'], 'U')}",
        f"- Project-balanced candidate exclusion share, supported-only endpoint: {d(['project_balanced','candidate_exclusion_share','value'], 'L')}",
        f"- Project-balanced candidate exclusion share, supported-or-unresolved endpoint: {d(['project_balanced','candidate_exclusion_share','value'], 'U')}",
        "",
        "These are assumption-dependent sensitivity summaries of denominator exposure,",
        "not corrected denominator counts and not evidence that any candidate row would run.",
        "",
        "## Secondary all-commits rate envelope",
        "",
        f"- Pooled published all-commits rate: {d(['pooled_commit_weighted','published_A'], 'L')}",
        f"- Pooled maximum upward sensitivity, supported-only: {d(['pooled_commit_weighted','all_commits_maximum_upward_sensitivity'], 'L')}",
        f"- Pooled maximum upward sensitivity, supported-or-unresolved: {d(['pooled_commit_weighted','all_commits_maximum_upward_sensitivity'], 'U')}",
        "",
        "The upper endpoints set the unknown candidate-row mean `q` to 1. They are",
        "mathematical envelopes, not corrected or expected rates.",
        "",
        "## Robustness boundary",
        "",
        "The JSON contains separate 95% family-wise design intervals and no-exchangeability",
        "worst-case partial-identification bounds. These are not merged or relabelled as one",
        "uncertainty interval. All 14 project rows are retained in the CSV and JSON.",
    ]
    args.out_md.write_text("\n".join(md) + "\n", encoding="utf-8")
    print(json.dumps({
        "status": payload["status"], "scope": payload["scope"],
        "pooled_exclusion_L": d(["pooled_commit_weighted", "candidate_exclusion_share"], "L"),
        "pooled_exclusion_U": d(["pooled_commit_weighted", "candidate_exclusion_share"], "U"),
        "pooled_A_max_shift_L": d(["pooled_commit_weighted", "all_commits_maximum_upward_sensitivity"], "L"),
        "pooled_A_max_shift_U": d(["pooled_commit_weighted", "all_commits_maximum_upward_sensitivity"], "U"),
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
