# Semantic Storyboard Validator — Human Annotation Rubric

**Version:** TV3 Semantic Storyboard Rubric v1.0 (draft for team-lead approval)  
**Contract baseline:** `main` — `src/storyboard/semantic_schema.py`, `src/storyboard/semantic_validator.py`, `src/storyboard/schema.py`, `docs/semantic_validation.md`  
**Scope:** Human annotation of development outputs and control/exploratory cases supplied in the handoff ZIP.  
**Not a runtime model prompt.** Human labels must remain separate from Qwen reviewer prompts and predictions.

## 1. Purpose and source hierarchy

Evaluate semantic faithfulness by comparing:

1. **Independent `original_summary`** — source of truth for story events, actors, causal links and ending.
2. **Storyboard `characters[]` catalog** — shared visual descriptions and identity records.
3. **Storyboard `scenes[].characters[]`** — references to catalog IDs for each scene.
4. **Storyboard `scenes[].caption_vi`** — Vietnamese scene-level action and narrative.
5. **Storyboard `scenes[].image_prompt_en`** — English visual interpretation of the scene.

`storyboard.summary` is not a replacement for `original_summary`. Record exact summary mismatch separately in `structural_or_summary_notes` because the canonical eight-code taxonomy has no `SUMMARY_MISMATCH` code. A summary mismatch is not, by itself, proof that the scene sequence is semantically wrong. Review the scenes against the independent source.

Structural validity, summary matching and semantic validity are separate dimensions. A structurally valid four-scene object can still be semantically incorrect. Conversely, structural validity failures are not to be forced into one of the eight semantic codes.

## 2. Canonical taxonomy (exact TV1 codes)

Use only these eight canonical codes. Do not invent aliases or add semantic scene-redundancy codes.

| Canonical code | Annotation criterion | Positive evidence required | Common false positive to avoid |
|---|---|---|---|
| `CHARACTER_IDENTITY_MISMATCH` | A scene reference, catalog visual, caption or prompt attributes content to the wrong story entity. | A concrete source/scene/catalog contradiction identifying which entity is represented incorrectly. | ID spelling alone; same-looking people; a character wearing different clothes; a generic prompt that does not identify a person. |
| `CHARACTER_ROLE_MISMATCH` | The person performing, receiving or causing an action differs from the source or from the corresponding caption/prompt. | An identifiable actor/action conflict, not just an omitted name in an image prompt. | A prompt that shows a supporting visual action while the caption describes the scene's principal event, where both can coexist. |
| `CHARACTER_FRAGMENTATION` | One source entity is split into multiple catalog records because of a change in action, emotion or scene state, causing duplicate identities/references. | The source supports one entity and the catalog/references create multiple state-named records for that same entity; simultaneous duplicate references are strong evidence. | Duplicate visual descriptions by themselves; unused records by themselves; two distinct people with similar appearance. |
| `OBJECT_TRANSLATION_MISMATCH` | A concrete object is mistranslated or replaced by a semantically different object across source/caption and English image prompt. | Exact source object text and the conflicting image-prompt text. | Different color/material/viewpoint; plausible visual elaboration that preserves object identity/function. |
| `VISUAL_LANGUAGE_MISMATCH` | A shared `Character.visual` description violates the contract's English-language requirement. | The exact `characters[i].visual` string is clearly written in another language, not merely a proper name or ambiguous short token. | Vietnamese captions; proper names; short mixed-language terms; image prompts or captions (this code is specifically for shared `Character.visual`). |
| `MISSING_KEY_EVENT` | A consequential source event needed to preserve causality, motivation or outcome is absent from the whole scene sequence. | A specific original-summary event plus review of all four scenes showing no equivalent visual/narrative representation. | Minor detail omission; compression; an event represented visually without matching words; an event omitted from `storyboard.summary` but present in scenes. |
| `ENDING_CONTRADICTION` | The final scene/result conflicts with the ending in the independent source. | Exact source outcome and an incompatible final caption/image prompt. | A compressed but compatible ending; a different visual depiction of the same outcome. |
| `UNSUPPORTED_STORY_EVENT` | A new event/action/relationship materially changes the plot without support in the source. | Exact storyboard text that asserts the added event and a source review establishing the unsupported plot change. | Harmless poses, camera angle, lighting, setting, clothing, background props, or a plausible connective action that does not alter the story. |

### Identity and fragmentation safeguards

- A `Character.id` is a reference key, not sufficient semantic proof by itself. Read its catalog `visual`, scene captions, image prompts and original summary together.
- Identical or near-identical visual descriptions do not automatically mean two records are the same individual. Two distinct people may deliberately look alike.
- Different visual descriptions do not automatically mean different individuals: clothing, pose, age depiction or emotional state can vary unless the story says otherwise.
- Do not call a catalog fragmentation error merely because it contains unused records. Explain whether the same source entity is split across state/action-labelled records and whether references actually use those records.

## 3. Severity: `error` or `warning`

Severity is an impact axis, independent of `status` certainty. Do not hard-map a code to one severity.

- **`error`** — the issue materially changes or contradicts a source entity, actor/action, object identity, consequential event or ending; or it creates separate catalog identities for the same actor in a way that can render duplicate characters and disrupt continuity.
- **`warning`** — a contract/style discrepancy is real but the underlying story meaning remains recoverable, or the observed evidence is limited and the impact is not yet established. A confirmed non-English `Character.visual` is normally a warning if it remains unambiguous to a bilingual reader; upgrade only when the language mismatch causes a substantive identity/meaning failure.

Severity is not confidence. An issue can be `status=uncertain` only with a cautious severity (`warning`) in a provisional response. If later adjudication establishes a material contradiction, update both status and severity with a recorded rationale.

## 4. Issue status, case verdict and review state

### Issue `status`

- **`confirmed`** — evidence is sufficient to conclude that the specified semantic discrepancy exists.
- **`uncertain`** — a plausible discrepancy exists but the payload does not resolve the competing interpretation. State exactly what is ambiguous.

### Case verdict (canonical `pass` / `fail` / `uncertain`)

| Verdict | Rule |
|---|---|
| `pass` | A full review found no supported issue; `issues` must be empty. Blank/unreviewed templates are never pass. |
| `fail` | At least one confirmed issue with `severity=error`. Additional warning issues may coexist. |
| `uncertain` | No confirmed error exists, but one or more warnings/uncertain findings remain, or the evidence is insufficient for a clean/fail decision. |

This matches the strict `SemanticReviewResponse` contract on `main`: `pass` cannot contain any issues; `fail` requires at least one error; `uncertain` cannot contain an error. Do not put tentative error hypotheses into a production response. Preserve them in the human annotation draft as `status=uncertain` until adjudicated.

### Case review metadata

- `human_review_state`: `pending_human_review` before review; `in_progress` while reviewing; `completed` only after a person actually completes the case.
- `annotation_status`: `confirmed` when the case-level decision is supported and no unresolved semantic ambiguity remains; `uncertain` when ambiguity remains after review.
- `review_date`, annotator and `rubric_version` must be recorded.
- An AI/pre-annotation draft must never set `human_review_state=completed`, nor present its proposed verdict as a human gold label.

### Runtime review status is not a semantic verdict

The production `SemanticValidationReport.review_status` has `completed`, `failed` and `not_checked`; this is separate from `SemanticReviewResponse.verdict`:

- `completed` means a response passed parsing, strict schema and location/evidence contract checks. Only then is `verdict` populated.
- `failed` means the reviewer call/output/contract failed. It is **not** a semantic `fail` and has no semantic verdict.
- `not_checked` means the source/arguments were not eligible for review (for example, invalid source storyboard). It is not `pass` or `fail`.

Human annotations are stored separately. The main report currently exposes `human_annotation_status="not_checked"`; do not insert human labels into a Qwen prompt or pretend they are part of the runtime report. A human case verdict is an evaluation annotation, not a runtime execution status.

## 5. Locations and exact evidence (TV1 contract)

### Zero-based paths

A location is a JSON path list of field names and zero-based list positions. Use list positions, not `Scene.index` values (which are 1–4) and not character IDs as substitutes for positions.

Examples:

- `characters[2].visual` → `[`"characters"`, 2, `"visual"`]`
- second scene caption → `[`"scenes"`, 1, `"caption_vi"`]`
- third scene's first character reference → `[`"scenes"`, 2, `"characters"`, 0`]`
- whole storyboard / global missing-event search → `[]` (or `[`"scenes"`]` when anchoring to the scene collection is more useful).

Rules: path components are non-empty strings or non-negative integer positions. Booleans are not integer positions. The issue location must resolve against the storyboard snapshot. For one underlying issue spanning several fields, use one primary `location` and list the other paths in the human-format `related_locations` extension; do not duplicate the issue.

### Evidence object

Canonical evidence is:

```json
{"source":"original_summary","location":[],"quote":"exact source substring"}
```

or

```json
{"source":"storyboard","location":["scenes",1,"caption_vi"],"quote":"exact field substring"}
```

- `source` is exactly `original_summary` or `storyboard`.
- `original_summary` is a single string; its evidence `location` must be `[]`.
- `storyboard` evidence must point to an existing **string field**, including an individual character reference string if needed. Do not quote a whole object/list or stringify an integer.
- `quote` must be a non-empty exact substring of that declared string. Do not translate, paraphrase, change case, trim, or normalize Unicode (NFC/NFD variants are not interchangeable).
- For contradictions, quote both sides when available. For an omission, quote the missing event from the original summary and anchor the issue to the scene collection/whole storyboard; never invent a quote for absent text.
- Exact quote/path validity proves traceability only. It does not prove the explanation or semantic inference is correct.

When exporting to `SemanticIssue`, map human `explanation` to canonical `message`; export only `code`, `severity`, `location`, `message`, `evidence`. The human-only `issue_id`, `status`, and `related_locations` are extensions and must not be inserted into the strict production `SemanticReviewResponse` without a separately versioned schema change.

## 6. Issue unit and matching policy (freeze before Qwen comparison)

### Unit of analysis

One issue is one distinct underlying semantic discrepancy within one case. Multiple quotes or scene locations proving the same discrepancy belong to one issue (`location` anchor + `related_locations` + evidence list). Do not create one issue per quote or repeat the same object/actor mismatch in every scene when it is one consistent mapping error. Separate issues are appropriate when the causal claim is genuinely different (for example, two different source characters each fragmented into their own multiple records).

### One-to-one matching

A Qwen prediction matches a human confirmed issue only when all conditions hold:

1. Same case.
2. Exact same canonical issue code (no alias/fuzzy code mapping).
3. Same underlying entity/action/object/event/outcome discrepancy after reviewing the explanation and evidence.
4. Prediction location equals the human anchor or one of the human `related_locations`; no automatic parent-path, prefix or `[]` wildcard.
5. Both sides have traceable evidence supporting the same discrepancy. Quotes need not be byte-identical, but each quote must independently be an exact substring at its own declared source/path.

Use one-to-one matching: one prediction can match at most one gold issue, and one gold issue can match at most one prediction. Unmatched duplicate predictions count as unmatched predictions (potential false positives) and are also reported in a duplicate-prediction diagnostic; do not silently deduplicate them. Duplicate human gold issues must be adjudicated before freeze.

### Severity and uncertainty in matching

- Primary semantic match is based on code + underlying discrepancy + location + evidence. Compare severity separately as severity agreement; a severity disagreement does not erase an otherwise valid semantic match.
- Only human issues with `status=confirmed` enter primary confirmed-gold matching.
- Uncertain human findings are reported separately; do not count them as confirmed positives or negatives and do not score a prediction against them as a definitive FP/FN.
- A case with a confirmed error can have case verdict `fail` even if it also contains uncertain/warning findings. A case with no confirmed error but unresolved findings is `uncertain`, not `pass`.

### Denominators and failure handling

Before comparison, publish the eligible case list, confirmed issue list, matching policy and planned call inventory. Report separately: reviewer calls completed/failed/not-run, valid decisions, abstentions/uncertain cases, confirmed-gold issue count, accepted prediction count, matched pairs, unmatched predictions and unmatched gold issues. Never remove reviewer failures/abstentions from the inventory without reporting coverage. Do not calculate metrics from pending/uncertain annotations as if they were negatives.

## 7. Creative variation: default not an issue

Accept harmless visual/narrative staging that preserves source identity, action, causal sequence and ending: composition, angle, pose, expression, lighting, clothing, background, non-consequential props, and plausible connective details. A preparatory action (for example, gathering a tool before a stated repair) is not automatically a plot-changing unsupported event. Record accepted variations when useful for adjudication, not as errors.

## 8. Scope and independence

- Annotate the supplied four development outputs, four control cases and two exploratory cases only. The neutral manifest does not map `case_001`…`case_010` to these strata; do not infer group membership from order or content. The coordinator must supply the mapping separately if stratified reporting is required.
- Do not use the official 30-story Test dataset for rubric tuning or reviewer development.
- Do not inspect expected labels, mutation descriptions, AI suggestions or Qwen predictions before annotation is frozen.
- Human annotations remain separate from Qwen reviewer prompts and inputs. No human label is inserted into the reviewer prompt.
- Keep the original frozen cases, manifest, checksums and blank templates immutable. Save annotations as a new package. Record prior exposure honestly; do not claim blinded review if prior predictions/design labels were seen.
- This rubric is a **TV3 v1.0 draft** until accepted by the team lead. Changes after predictions are seen require a new version and an adjudication/audit note.

## 9. Out-of-scope observations

If an observation does not satisfy any of the eight canonical codes (for example, catalog type hygiene, unused catalog rows without semantic proof, exact `storyboard.summary` mismatch, or non-semantic structural issues), record it in `structural_or_summary_notes` or `additional_notes`. Do not force it into a nearby code.
