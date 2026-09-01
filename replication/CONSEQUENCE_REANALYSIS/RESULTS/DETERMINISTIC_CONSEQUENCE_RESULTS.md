# Deterministic consequence reanalysis results

Status: `PAPER04_N2_DETERMINISTIC_CONSEQUENCE_REANALYSIS_PASS`

Scope: 14 downstream-retained projects, 1,114 exact collector-zero rows,
and 109 frozen sample units. Runtime outcomes remain unidentified.

## Primary denominator sensitivity

Under the frozen design-based plug-in calculation:

- Pooled candidate exclusion share, supported-only endpoint: 0.011450516154
- Pooled candidate exclusion share, supported-or-unresolved endpoint: 0.036998901702
- Project-balanced candidate exclusion share, supported-only endpoint: 0.022756941633
- Project-balanced candidate exclusion share, supported-or-unresolved endpoint: 0.056338162003

These are assumption-dependent sensitivity summaries of denominator exposure,
not corrected denominator counts and not evidence that any candidate row would run.

## Secondary all-commits rate envelope

- Pooled published all-commits rate: 0.132660083045
- Pooled maximum upward sensitivity, supported-only: 0.001579325895
- Pooled maximum upward sensitivity, supported-or-unresolved: 0.005238502507

The upper endpoints set the unknown candidate-row mean `q` to 1. They are
mathematical envelopes, not corrected or expected rates.

## Robustness boundary

The JSON contains separate 95% family-wise design intervals and no-exchangeability
worst-case partial-identification bounds. These are not merged or relabelled as one
uncertainty interval. All 14 project rows are retained in the CSV and JSON.
