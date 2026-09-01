# Claim-to-evidence map

| ID | Bounded claim | Direct evidence | Status |
|---|---|---|---|
| DC-01 | The fixed downstream target is exactly reproducible. | `ANCHOR_DOWNSTREAM_REPRODUCTION_RECEIPT.json`: 66 projects, 528 comparisons, maximum rate difference 3.33e-16. | PASS |
| DC-02 | The audit frame is exactly linkable to the anchor tables. | `ANCHOR_FRAME_JOIN_AUDIT.json` and `ANCHOR_FRAME_JOIN_LEDGER.jsonl`: 3,393/3,393 rows; no duplicate, heuristic, or unmatched key. | PASS |
| DC-03 | Only 14 projects and 1,114 frame rows enter the published downstream overlap. | Join audit project matrix; 109 linked sample units. | PASS |
| DC-04 | Plug-in pooled candidate-exclusion share is 1.145% (L) to 3.700% (U). | `FULL_CONSEQUENCE_RESULTS.json`, `design.plugin_endpoints.*.pooled_commit_weighted.candidate_exclusion_share`. | PASS, assumption-dependent |
| DC-05 | Pooled all-commits maximum upward envelope is 0.158–0.524 percentage points. | Same result, `all_commits_maximum_upward_sensitivity`. | PASS, q=1 envelope |
| DC-06 | Project-balanced candidate-exclusion share is 2.276–5.634%. | Same result, project-balanced endpoint values. | PASS, assumption-dependent |
| DC-07 | Supported-only project-level maximum all-commits shift is 3.20 points; U maximum is 14.51 points. | `PROJECT_CONSEQUENCE_SUMMARY.csv`; `ansj_seg` and `Bukkit`. | PASS, q=1 envelopes |
| DC-08 | Simultaneous design intervals and worst-case bounds are wider and remain separately identified. | `FULL_CONSEQUENCE_RESULTS.json`, `interval_aggregates`. | PASS |
| DC-09 | The primary and independent implementations agree. | `INDEPENDENT_COMPACT_RECOMPUTE.json`: 1,706 exact leaves, zero mismatches. | PASS |
| DC-10 | Runtime behavior and corrected truth remain unidentified. | Protocol freeze, formulas with `q in [0,1]`, and final nonclaims. | BOUNDARY |

