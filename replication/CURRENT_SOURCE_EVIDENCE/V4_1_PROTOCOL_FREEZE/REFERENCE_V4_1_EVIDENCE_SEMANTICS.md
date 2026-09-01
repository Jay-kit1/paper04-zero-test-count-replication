# Reference V4.1 evidence-projection semantics

## Frozen scientific construct

V4.1 retains exactly the V4 question: whether the frozen archive establishes at least one supported test-source witness. It does not classify runtime behavior, collector failure, Maven behavior, or mechanisms.

The only primary categories are:

- `SOURCE_SUPPORTED_TEST_PRESENCE`
- `NO_SUPPORTED_TEST_SOURCE_IDENTIFIED`
- `SOURCE_EVIDENCE_UNRESOLVED`

Category precedence and all V4 archive, language, test-intent, and negative-completeness rules remain frozen.

## Canonical witness projection

A positive witness is identified by `(path, sha256)`. Its `supporting_rules` value is the sorted, duplicate-free set of every frozen positive pathway independently satisfied by that file. A strong declaration does not suppress a simultaneously satisfied Path-B rule.

## Ambiguity projection

`decision_blocking_unresolved_reasons` contains only ambiguity that prevents the category decision. `nondecisive_warnings` contains observed ambiguity that cannot invalidate an already safe positive witness.

When at least one safe positive witness exists, suspicious test intent, unsupported-language test intent, generated-source ambiguity, decode ambiguity, or decisive nonregular/collision evidence elsewhere is warning-only unless it compromises every available positive witness. When no safe positive exists, any such decisive ambiguity blocks a negative decision and releases `SOURCE_EVIDENCE_UNRESOLVED`.

`NO_SUPPORTED_TEST_SOURCE_IDENTIFIED` requires every frozen negative-completeness boolean to be true. `SOURCE_EVIDENCE_UNRESOLVED` requires at least one decision-blocking reason.

## Framework-implementation safeguard

The generic Clojure framework-implementation signature is either a canonical path ending in `clojure/test.clj` or a decoded source namespace matching `(ns clojure.test ...)`. Such a file is excluded from both Path A and Path B. No project-specific exclusion exists. No additional framework exclusion is frozen because the V4 registry does not provide an equally objective implementation-source signature for the other frameworks.

## Canonical ordering

Witnesses sort by path and SHA-256. Supporting-rule, blocking-reason, and warning sets sort by the frozen registry orders, with lexical ordering as a deterministic fallback. Ordering carries no scientific meaning.
