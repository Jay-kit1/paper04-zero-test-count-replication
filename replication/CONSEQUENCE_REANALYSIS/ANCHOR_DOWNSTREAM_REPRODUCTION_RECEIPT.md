# Anchor downstream reproduction receipt

Status: `PASS`

This gate recomputed the fixed anchor's downstream summary from the official frozen
`report.csv` and `summary.csv` files. It did not read the Paper04 audit frame and
did not compute any post-R4.1 consequence quantity.

## Result

- Projects reconstructed: 66/66
- Exact integer comparisons: 264, mismatches: 0
- Floating-rate comparisons: 264, mismatches: 0
- Maximum absolute rate difference: `3.3306690738754696e-16`
- Replay tolerance: `5e-15` (binary floating point)

## Interpretation

PASS means the exact published target and its code path are identified at the
precision of the fixed CSV serialization. It does not validate the construct,
reclassify any zero, or imply that a source-supported snapshot would execute or pass.
