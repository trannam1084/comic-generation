# TV1–TV3 Offline Evaluation Matching Policy v1.0 — Draft for joint approval

**Policy ID:** tv1-issue-matching-v1.0  
**Contract baseline:** main commit 141eed38cbfd7b5306227e18750f48b3dc58deb3 (checked 2026-11-21)  
**Contract files:** src/offline_evaluation/contracts.py, src/offline_evaluation/semantic.py, tests/test_offline_evaluation.py  
**Status:** contract-aligned draft; requires explicit TV1/TV3 joint approval. This document introduces no matching implementation or new metric.

## 1. Mandatory full-case gold-ready gate

The Offline Evaluation Harness uses a full-case gate, not partial-gold matching. A case may enter prepare_semantic_matches only when annotation_readiness(case) returns gold_ready=true. Under the current main implementation, all conditions below must hold:

1. human_review_state is completed;
2. annotation_status is confirmed;
3. verdict is pass or fail, not uncertain;
4. adjudicated is true;
5. every finding in the case has status confirmed; no unresolved/uncertain finding remains;
6. rubric_version is not draft_not_approved or pending and is the formally approved rubric version for this evaluation;
7. the case ID, original-summary SHA-256 and storyboard SHA-256 match the evaluation case, and all issue locations/evidence quotes pass exact path and substring validation.

**No partial-gold exception:** if even one finding is unresolved/uncertain, the entire case is not gold-ready and prepare_semantic_matches must not be called. Do not match only a confirmed subset, count unresolved findings as negatives, or treat an empty pending issue list as PASS. Resolve/adjudicate the entire case or exclude the whole case from the matching batch.

A clean case is gold-ready only after actual human review and adjudication with verdict=pass, annotation_status=confirmed, issues=[], completed reviewer metadata, an approved rubric version and matching provenance hashes. An empty pending template is never a gold-negative.

## 2. Strict contract states

- HumanAnnotation state values are pending_human_review, in_progress and completed.
- Pending/in-progress annotations must not contain a final verdict, final annotation status or adjudicated=true.
- Completed annotations require annotator, review_date, verdict and annotation_status.
- PASS requires no issues. FAIL requires at least one confirmed error. UNCERTAIN cannot contain a confirmed error.
- AnnotatedFinding with status=uncertain must have severity=warning. Do not silently downgrade an error hypothesis. Keep a potentially severe but unverified concern in adjudication notes outside the strict runtime issues list until evidence resolves it.
- Any unresolved uncertain finding prevents full-case gold readiness.
- prior_prediction_exposure is none, yes or unknown. The harness reports blind_annotation_claimed=false. Do not claim blind review where suggestions/predictions were exposed.

## 3. Matching preparation after full-case readiness

prepare_semantic_matches prepares a human-approved one-to-one discrepancy crosswalk. It is not an automatic semantic scorer.

1. The reviewer report provenance must match the exact original_summary and storyboard snapshot.
2. A reviewer report whose review_status is not completed is returned as not_checked; it has no accepted prediction links and is not a semantic FAIL.
3. Every prediction location/evidence is validated against the exact summary/storyboard snapshot.
4. TV1/TV3-approved DiscrepancyLink entries connect a unique prediction_index to an adjudicated human discrepancy_id. Prediction indexes must be unique and in range; discrepancy IDs must exist in the human annotation.
5. A match requires the same discrepancy_id, exact canonical issue code, and a location equal to the human anchor or an explicitly declared related_location. Parent paths, prefixes and [] are not wildcards. Evidence must independently be valid and support the same underlying discrepancy.
6. One prediction can match at most one human finding and one human finding can be matched at most once. Duplicate predictions are reported separately. Duplicate human discrepancy IDs must be adjudicated before matching.

## 4. Output and metric boundary

The current Harness returns preparation diagnostics: matched pairs, unmatched predictions, duplicate predictions, unmatched confirmed gold findings, unadjudicated predictions, and semantic_metrics=null.

Do not add or calculate precision, recall, F1, TP/FP/FN, severity aggregate scores, partial-case denominators, or another scoring scheme under this policy. The current contract intentionally does not calculate those semantic metrics. Any future scoring proposal requires a separate TV1/TV3 decision and a new versioned specification before implementation.

Severity agreement remains the per-match boolean severity_agrees already emitted by the helper. This policy does not define a new aggregate severity metric.

## 5. Official dataset gates

When a plan includes an official_dev or official_test origin, EvaluationPlan requires split_frozen, review_approved, rights_approved and a dataset_reference SHA-256. An official_test case additionally requires official_test_authorized=true. The current contract does not treat origin=development as an official_* origin for this gate. Each planned case must have exactly one B0 and one B1 run.

A source URL, selection-review status or passing structural validator does not automatically set review_approved or rights_approved. Those approvals must be backed by project evidence tied to the frozen dataset snapshot.

## 6. Freeze and governance

Before official evaluation, freeze together: contract baseline commit, dataset snapshot and checksums, Dev/Test split, rights/attribution register and approval scope, human rubric version, this matching-policy version, case inventory, approved human annotation package, discrepancy IDs/crosswalk, reviewer outputs and prediction-exposure metadata.

Do not tune against official Test labels. Keep the 10-case annotation package private and separate from the public repository. Do not edit human labels to agree with model predictions. Any change after predictions are viewed requires a new annotation/policy version and an adjudication audit trail.

**Joint approval — pending:**
- TV1 contract owner: pending
- TV3 annotation/rubric owner: pending
- Approval date: pending
- Approved rubric version: pending
- Approved dataset reference SHA-256: pending
