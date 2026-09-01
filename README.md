# When a Zero Test Count Does Not Establish Test-Source Absence

Public replication materials for the manuscript:

> Jiebao Zeng, *When a Zero Test Count Does Not Establish Test-Source Absence: A Project-Separated Measurement Audit of Historical Maven Snapshots*.

## Contents

- `Public_Replication_Archive.zip`: public-safe replication archive. Manuscript and SI patch prose are intentionally excluded.
- `replication/CURRENT_SOURCE_EVIDENCE`: released classifications, path-and-hash evidence records, protocols, validators, and independent implementation outputs.
- `replication/CONSEQUENCE_REANALYSIS`: frozen consequence protocol, inputs, code, exact outputs, independent recomputation, scope audit, and nonclaims.
- `SHA256SUMS`: integrity receipt for the immutable archive.

## Scientific boundaries

The public materials preserve a three-state source-evidence classification and keep unresolved cases explicit. Source evidence is not a claim of runtime test execution. The downstream consequence analysis applies only to its documented 14-project overlap and is not a corrected rate for the full frame.

Third-party repository snapshots and the third-party anchor artifact are not redistributed. Fixed repository references, provenance, and hashes are supplied so that eligible third-party inputs can be retrieved from their original sources under their own terms.

Historical handoff files inside `replication/` may record that public release was not authorized at the time those frozen artifacts were produced. The author subsequently authorized this public release on 1 September 2026; the retained historical files remain unchanged to preserve provenance. The journal manuscript, cover letter, portal materials, and historical proposed manuscript/SI patch files are not part of this repository.

## Replay

Start with:

1. `replication/CURRENT_SOURCE_EVIDENCE/V4_1_PROTOCOL_FREEZE/REFERENCE_V4_1_FREEZE.json`
2. `replication/CURRENT_SOURCE_EVIDENCE/V4_1_REAL_REPLAY/REAL_REPLAY_COMPARISON.md`
3. `replication/CONSEQUENCE_REANALYSIS/README_HANDOFF.md`
4. `replication/CONSEQUENCE_REANALYSIS/FINAL_STATUS.md`
5. `replication/CONSEQUENCE_REANALYSIS/CODE/validate_release.py`

The exact environment, input identities, limitations, and replay boundaries are recorded in the archive. A successful integrity or replay check establishes computational consistency only; it does not by itself establish external scientific validation.

## Licensing

Author-created source code is licensed under the MIT License in `LICENSE`. Author-created documentation and derived audit records are licensed under CC BY 4.0 as described in `DATA_LICENSE.md`. Third-party names, metadata, repository contents, and referenced artifacts remain subject to their original rights and licenses.

## Contact

Jiebao Zeng, School of Information Science and Technology, Yunnan Normal University. ORCID: 0009-0009-2931-7232.
