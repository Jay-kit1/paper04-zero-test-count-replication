# Protocol deviation ledger

## PD-001 — category-literal correction before result exposure

- Stage: first consequence-computation launch.
- Trigger: invariant failure `invalid frozen counts for CoreNLP`.
- Cause: V1.0 named the positive category `SUPPORTED_TEST_SOURCE_PRESENT`; the
  frozen label bytes use `SOURCE_SUPPORTED_TEST_PRESENCE`.
- Exposure state: no result file was created; the result directory was empty;
  no consequence value was printed or inspected.
- Action: preserved V1.0 and its hashes under
  `SUPERSEDED_V1_0_CATEGORY_LITERAL_TYPO`; corrected only the category literal;
  froze and hashed V1.1 before re-execution.
- Formula/population/aggregation change: none.
- Outcome-based adaptation: none.

## PD-002 — current join-audit summary literal repair

- Stage: R4.2 final bounded integration.
- Trigger: required current-code literal scan.
- Cause: the project-matrix summary branch of current
  `CODE/audit_anchor_frame_join.py` retained the obsolete positive-category
  literal even though the row ledger already carried current labels.
- Action: replaced the one current-code literal, rebuilt the project matrix,
  and added a fail-closed operational scan.
- Corrected totals: `82/24/43` across all 18 projects, `51/24/34` across the
  retained 14, and `31/0/9` across the excluded four.
- Scientific consequence: none. The exact 3,393-row join and all consequence
  headlines remained unchanged.
