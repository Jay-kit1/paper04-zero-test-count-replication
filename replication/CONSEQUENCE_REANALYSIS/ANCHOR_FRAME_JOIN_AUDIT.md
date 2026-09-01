# Anchor-frame join audit

Status: `PASS`

The join uses exact `(project, commit/snapshot)` strings. No prefix, date, fuzzy,
case-folded, or heuristic matching is permitted.

## Gate summary

- Frame rows joined: 3393/3393
- Sample rows linked to frame and V4.1 labels: 149/149
- Frozen field mismatches: 0
- Duplicate anchor keys: 0
- Published-downstream overlap: 14 projects, 1114 frame rows
- Pre-filter-only subset: 4 projects, 2279 frame rows

PASS identifies the row mapping only. It does not equate source support with runtime
success and does not itself define or calculate a consequence estimand.
