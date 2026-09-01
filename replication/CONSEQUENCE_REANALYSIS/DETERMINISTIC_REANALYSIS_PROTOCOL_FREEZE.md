# Deterministic consequence reanalysis protocol freeze

Status: `FROZEN_BEFORE_CONSEQUENCE_COMPUTATION`

This protocol was written after the anchor reproduction and exact row-join gates
passed, but before any post-R4.1 consequence quantity was computed or inspected.

## Scientific question and population

The analysis asks how sensitive the fixed anchor's published downstream rate
calculation is to collector-zero snapshots that have protocol-supported source
evidence, while runtime outcomes remain unidentified.

The primary population is the exact 14-project downstream-retained overlap:
`Bukkit`, `CoreNLP`, `DiskLruCache`, `alluxio`, `android-volley`, `ansj_seg`,
`graylog2-server`, `guava`, `java-design-patterns`, `javaee7-samples`,
`javapoet`, `nanohttpd`, `presto`, and `webmagic`. The four pre-filter-only
projects (`canal`, `clojure`, `wildfly`, and `zheng`) are excluded from every
published-downstream consequence estimand and appear only in scope accounting.

No repository, Maven build, test, notebook, classifier, or source fetch is run.
The unit is the fixed anchor `(project, commit)` row, joined exactly to the
frozen Paper04 frame and, for sampled rows, to the frozen V4.1 label.

## Frozen symbols

For project `j`:

- `C_j`: published `Total Commits`.
- `K_j`: published `Test buildable commits`, i.e. rows admitted by
  `test_build == SUCCESS` and `n_test > 0`.
- `A_j`: published `TestabilityRate_A`.
- `T_j`: published `TestabilityRate_T`.
- `N_j`: collector-zero frame rows in the retained overlap.
- `n_j`: frozen within-project sample size.
- `s_j`, `u_j`, `z_j`: sampled counts labelled respectively
  `SOURCE_SUPPORTED_TEST_PRESENCE`, `SOURCE_EVIDENCE_UNRESOLVED`, and
  `NO_SUPPORTED_TEST_SOURCE_IDENTIFIED`; `s_j + u_j + z_j = n_j`.
- `S_j`: a sensitivity count of collector-zero rows hypothetically admitted to
  an expanded positive-parsed-test denominator. `S_j` is not an estimate of
  executable, passing, reachable, or semantically valid tests.
- `q_j in [0,1]`: the unknown mean testability rate assigned to those
  hypothetical rows. Runtime evidence does not identify `q_j`.

## Evidence-status endpoints

Two endpoint families are reported separately:

1. `L` (supported only): indicator 1 only for
   `SOURCE_SUPPORTED_TEST_PRESENCE`.
2. `U` (supported-or-unresolved): indicator 1 for either
   `SOURCE_SUPPORTED_TEST_PRESENCE` or `SOURCE_EVIDENCE_UNRESOLVED`.

`U` is a classification-uncertainty sensitivity endpoint, not a claim that an
unresolved unit contains tests. The negative category is also protocol-bounded
and is not semantic proof of absence.

## Primary: denominator/exclusion sensitivity

Under the existing uniform-hash/exchangeability reference design, the plug-in
counts are

`S_hat_j,L = N_j * s_j / n_j`

and

`S_hat_j,U = N_j * (s_j + u_j) / n_j`.

For each endpoint, report:

- potential additional denominator count `S_hat_j,e`;
- hypothetical expanded positive-row coverage `(K_j + S_hat_j,e) / C_j`;
- candidate exclusion share `S_hat_j,e / (K_j + S_hat_j,e)` when the
  denominator is positive.

These quantities are assumption-dependent sensitivity summaries. They are not
corrected counts or corrected rates.

## Design-based finite-population intervals

For each endpoint family separately, invert equal-tailed hypergeometric tests
within each of the 14 fixed projects. Allocate family alpha `0.05/14` by
Bonferroni. Propagate the resulting integer population-count interval through
the monotone denominator formulas. Coverage is claimed separately for each
endpoint family; no joint coverage across `L` and `U` is claimed, and no
superpopulation interpretation is allowed.

## No-exchangeability worst-case bounds

Report a separate finite-population partial-identification analysis:

- `S_j,L in [s_j, N_j - n_j + s_j]`;
- `S_j,U in [s_j + u_j, N_j - z_j]`.

These bounds treat every unsampled row as unidentified. They do not use the
uniform-hash/exchangeability assumption and must not be merged with or described
as confidence intervals.

## Secondary: rate envelopes

Rate consequences are scenarios conditional on `S_j` and `q_j`, not corrected
truth.

For the all-commits series:

`A_j(S_j, q_j) = A_j + q_j * S_j / C_j`.

Therefore, with `q_j in [0,1]`, report the envelope
`[A_j, A_j + S_j/C_j]` and the maximum upward sensitivity `S_j/C_j`.

For the positive-parsed-test series, if `K_j + S_j > 0`:

`T_j(S_j, q_j) = (K_j*T_j + q_j*S_j) / (K_j + S_j)`.

Report its `q_j in [0,1]` envelope. If `K_j = S_j = 0`, mark the expanded rate
undefined rather than substituting the anchor's zero-return helper value. If
`K_j = 0` and `S_j > 0`, the envelope is `[0,1]`.

The primary narrative remains denominator sensitivity; rate envelopes are
secondary because source evidence does not identify runtime eligibility or
`q_j`.

## Aggregation frozen in advance

Project rows are sorted lexicographically and none may be omitted after results
are seen. Report both:

1. project-balanced means of defined project-level quantities, with the number
   of contributing projects shown; and
2. pooled commit-weighted quantities formed from exact sums (`sum C_j`,
   `sum K_j`, `sum S_j`, `sum C_j*A_j`, and `sum K_j*T_j`).

The main-text proposal may report only the 14-project scope, the pooled and
project-balanced denominator sensitivity, and bounded rate movement. The SI
proposal must retain all 14 project rows, both endpoint families, both design
and worst-case analyses, and undefined states.

## Arithmetic and independent replay

Counts and plug-in estimates use exact rational arithmetic. Decimal renderings
are presentation only. One primary implementation and one independently written
compact recomputation must agree on every exact fraction and categorical state.

## Stop rules

Stop with `KILL_DETERMINISTIC_REANALYSIS_INVALID_CONSEQUENCE_ESTIMAND` if any
formula requires treating source support as observed runtime success, if a
candidate count exceeds the available non-positive branch, if aggregation
cannot be reconstructed from the fixed published columns, or if primary and
independent results disagree.

## Frozen language boundary

Allowed: sensitivity, potential denominator exclusion, measurement consequence,
partial identification, runtime unidentified, assumption-dependent, descriptive.

Forbidden: corrected or true testability rate; tests would run or pass; the
anchor is false; V4.1 recovers missed tests; source support equals executability,
reachability, positive `n_test`, or semantic correctness.
