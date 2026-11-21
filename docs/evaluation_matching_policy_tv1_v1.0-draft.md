# TV1 Human Annotation — Evaluation Matching Policy v1.0

**Policy ID:** `tv1-issue-matching-v1.0`  
**Status:** frozen candidate for team review; not official until approved by TV3/team lead.  
**Rubric dependency:** `tv1-eight-codes-handoff-v1` (TV3 Human Annotation Rubric v1.0 draft).  
**Purpose:** define the comparison procedure before any Qwen predictions are inspected.

## 1. Gold eligibility

1. A case enters the primary human-gold scope only after a person has actually reviewed it and its record has `human_review_state=completed`, annotator identity, review date, rubric version and an adjudicated case verdict.
2. `annotation_status=confirmed` is required for a confirmed case conclusion. A confirmed-clean case must explicitly have `verdict=pass` and a human-confirmed empty `issues` list. An empty template, missing issue list or pending record is never a negative label.
3. Only issues with `status=confirmed` enter primary confirmed-gold issue matching. Issues with `status=uncertain` are reported separately and are neither positive nor negative gold.
4. Where a case has both confirmed and uncertain issues, confirmed issues remain eligible for issue-level matching; uncertain issues are excluded and reported separately. The case verdict must still follow the rubric contract: an unresolved issue cannot be silently converted into a clean `pass`.
5. Prior AI-suggestion exposure is retained per case and reported. This package does not claim blind review.

## 2. Canonical issue match

A prediction matches a human gold issue only when every condition holds:

1. Same case ID.
2. Exact same canonical code from the eight-code taxonomy; no alias or near-code mapping.
3. Same underlying semantic discrepancy (entity, actor/role, object, key event or ending), judged from the explanation/message and evidence rather than keyword overlap.
4. Prediction `location` equals the human issue's anchor `location` or one explicitly declared `related_locations`. Parent paths, prefixes and `[]` are not wildcards.
5. Both sides have valid, traceable evidence. Every quote must be an exact substring at its declared source/path. Quotes need not be byte-identical across sides if each independently supports the same underlying issue.

If more than one candidate pairing is plausible, an adjudicator resolves the pairing before aggregate metrics are calculated. The matching procedure must not be adjusted after inspecting a model's results.

## 3. One-to-one matching and duplicates

- One prediction can match at most one gold issue; one gold issue can match at most one prediction.
- A second or later duplicate prediction does not create another true positive. It remains an unmatched prediction for primary accounting and is also counted in a separate duplicate-prediction diagnostic.
- Duplicate human gold issues must be adjudicated before the gold set is frozen; do not silently deduplicate them after seeing predictions.
- Multiple locations/quotes for one underlying error are represented as one human issue with one anchor plus explicit `related_locations` and evidence.

## 4. Severity and uncertainty

- Semantic matching is based on code, underlying discrepancy, location and evidence. A severity mismatch does not erase an otherwise valid semantic match.
- Report severity agreement separately (exact `error`/`warning` agreement and confusion counts). Do not hard-map a code to a severity.
- A human `uncertain` issue is excluded from primary TP/FP/FN matching and reported in an uncertainty table.
- A model `uncertain`/abstention is not a positive semantic prediction and is not automatically a false negative; report it separately in coverage/abstention results.

## 5. Execution failures and denominators

Report the full planned call inventory: completed, failed, not checked, not run and abstained/uncertain. Invalid JSON, schema failures, evidence-validation failures and backend errors are execution/contract failures, not semantic `fail` verdicts.

- **Case-level gold denominator:** all eligible human-reviewed cases, including those for which a reviewer call fails or abstains. Report decision coverage on this denominator.
- **Issue-level gold denominator:** all confirmed human gold issues in the eligible frozen scope, including issues in cases where the reviewer failed or abstained; such issues remain unmatched unless an accepted prediction exists.
- **Prediction denominator:** all accepted, contract-valid predictions in the same eligible scope. Invalid or malformed raw proposals are diagnostics, not accepted predictions.
- Report matched pairs, unmatched gold issues, unmatched predictions, duplicate predictions, uncertain human issues, reviewer abstentions and execution failures separately. Do not drop failures/abstentions to improve apparent performance.

## 6. Freeze and change control

Before comparing with Qwen, freeze: rubric version, this policy version, case inventory, case-group mapping (if stratified reporting is required), human-confirmed gold scope, issue IDs, anchor/related locations, evidence, exposure metadata and denominator rules. Keep original annotation files and adjudication history. A post-prediction change requires a new policy/rubric version and an audit note; never edit labels to match model predictions.

**Not approved:** this document is a complete proposal for review, not a claim of TV3/team-lead approval. No evaluation metrics are calculated in this file.
