# Dataset Semantic Fidelity Audit — final reconciliation of 30 Dev/Test stories

**Review date:** 2026-11-21  
**Repository:** trannam1084/comic-generation, PR #20, feature/evaluation  
**Contract baseline:** main commit 141eed38cbfd7b5306227e18750f48b3dc58deb3  
**Scope:** provenance, split integrity, selection-review metadata, the 11 lexical-screen flags, story_016 attribution and evidence limitations. This is not a certification of all story semantics or rights clearance.

## 1. Frozen dataset snapshot

| File | Records | SHA-256 |
|---|---:|---|
| data/dev_cases.jsonl | 20 | f54dcab4c835969c9fbd46f4eda3af9d9dfe3502d85de1686d9202c1c7c33602 |
| data/test_cases.jsonl | 10 | 76ee7ef7a9ca57e7511928faf5e1a61364f269f4187aa8e8a14fdaa04bae09f8 |

Difficulty: Dev 12 easy / 3 medium / 5 hard; Test 6 easy / 4 medium / 0 hard; total 18 easy / 7 medium / 5 hard. IDs and URLs remain unique across splits. The raw candidate corpus is not copied into this repository.

Hashes were calculated from the exact JSONL snapshots committed at this PR revision. Any further edit to either file requires recalculating the hashes and rerunning validation.

## 2. Provenance reconciliation

Cross-reference against the 306-row raw corpus and selection metadata:

- 30/30 source URLs have exactly one matching raw-corpus row.
- 30/30 source URLs have exactly one matching selection-metadata row.
- 30/30 are final_selected=Yes and the recorded Dev/Test split agrees.
- 28/30 titles match the raw title verbatim; two are normalized title strings.
- 26/30 dataset source strings match raw author_or_source verbatim; four have attribution/provenance differences: story_016, story_066, story_072 and story_077.

### story_016 — host-page attribution verified

The raw corpus author_or_source field is empty and selection metadata uses Unknown. However, the live source page https://truyendangian.com/su-tich-cai-sung/ displays the story attribution block with “Truyện cổ tích Việt Nam” and “Hồ Lãng kể”. The Dev JSONL therefore has a traceable basis for displaying “Hồ Lãng kể” as the byline shown by the host webpage.

This does not independently verify the original printed edition, underlying rights holder, or permission to reuse. Preserve this distinction in the private register; do not describe it as independently verified original authorship or copyright ownership.

### Other normalized source fields

- story_066: dataset source is shortened/normalized relative to raw webpage attribution wording; both include Vũ Duy Thông.
- story_072: dataset title/source wording is normalized; raw metadata contains additional site/category wording and Vũ Duy Thông.
- story_077: dataset title/source wording is normalized relative to raw metadata; Grimm and the cited 1976 Vietnamese reading-book reference remain recorded.

The private rights_attribution_register_30.csv preserves raw metadata and final JSONL source strings side by side. It is not committed to the public repository.

## 3. Human-review status and limits

Selection metadata contains a non-empty review status for 306/306 candidates: 296 Reviewed, 5 Reviewed - approved for Dev, and 5 Reviewed - not selected for updated Dev. The 30 selected records comprise 25 Reviewed and 5 Reviewed - approved for Dev entries.

These fields document selection-stage review status. They do not, on their own, provide reviewer ID, review date, detailed adjudication notes, or proof that every summary/character/key-event field completed semantic-fidelity review. The JSONL normalization_note still records AI-assisted normalization and requests human comparison against source. The 30-story dataset is therefore not described as human gold or fully semantic-certified.

## 4. Final disposition of the 11 key-event alignment flags

The original 11 flags were a lexical-overlap triage screen, not confirmed semantic defects. They were reviewed against the exact summary string supplied to Story Generator. Resolution changed only listed key_events; summaries, IDs, URLs, split membership, difficulty and selection scores were not changed. Event numbers below refer to one-based positions in the pre-revision snapshot.

| Split | Story ID | Original event no. | Final status | Final disposition |
|---|---|---:|---|---|
| Dev | story_010 | 1 | removed | Initial terrain/water condition was present in raw full text but absent from input summary. Removed instead of expanding the summary. |
| Dev | story_013 | 1 | revised | Reduced to “Ngô Thì Sĩ ham học dù nhà nghèo.” |
| Dev | story_013 | 3 | removed | “Ngọn đèn lớn” anecdote was in raw text but not in input summary. Removed. |
| Dev | story_030 | 1 | revised | Reduced to the competition between Mekong and Ping; removed raw-source-only taunt detail. |
| Dev | story_030 | 2 | revised | Reduced to “Ping hợp với các sông khác rồi đi chậm”; removed tributary names/journey details absent from summary. |
| Dev | story_033 | 2 | revised | Reduced to the summary-grounded point that the buyer repeatedly complains because he is holding the calendar upside down. |
| Dev | story_033 | 4 | retained | Lexical-screen false positive; semantically equivalent to the summary statement that he admits he would not need glasses if he could read. |
| Dev | story_041 | 1 | removed | The king's visit to West Lake and guards keeping the crowd back were raw-source details absent from input summary. Removed. |
| Dev | story_047 | 1 | removed | Final correction: after unsupported sworn-brother/examination details are removed, this duplicates event 2 and adds no distinct summary-grounded event. It is removed, not retained/revised. |
| Test | story_040 | 1 | revised | Reduced to the summary-grounded idea that Ngựa Con focuses on appearance and is confident of winning. |
| Test | story_053 | 4 | revised | Reworded to the summary-grounded causal sequence: the acquaintance understands his nature, uses “cầm tay tôi”, and he grasps the hand and is rescued. |

**Final counts:** 6 event texts revised, 4 events removed, 1 lexical false-positive retained. Earlier wording that story_047 was revised or that all 11 rows were still pending is superseded.

**Scope limitation:** the 109 events not flagged by the lexical screen were not individually certified through a full human semantic review in this task. A lexical-screen pass is not proof of semantic fidelity. Test event edits are data-quality alignment fixes only; they are not a basis for tuning the generator/reviewer on held-out Test.

## 5. Rights and attribution status

A private register covers all 30 source URLs. All 30 point to truyendangian.com and remain recorded for traceability.

The story_016 source-page footer states that the site has registered copyright with DMCA and asks that copied content credit TruyenDanGian.Com. This host-site notice is not an explicit license to reuse, store, train on or publicly redistribute stories. No per-source license, permission email, rights-holder approval or captured terms granting the intended use scope were present in the inspected local package.

- Internal project use: not cleared by documentary evidence in the inspected package. Keep materials in restricted/private storage pending a documented project/institution and, where necessary, rights-holder decision.
- Public GitHub/public distribution: not cleared by the evidence available. Do not publish full-text corpus, substantial extracts or the derived 30-story dataset as an openly reusable corpus until permission/rights review is complete.
- URL and attribution are provenance, not a license. Do not infer public-domain status for modern retellings, translations, textbook versions or editorial page content merely because the underlying story is folkloric.

The detailed register is handed over separately and remains outside this public PR.

## 6. Validation and remaining gates

Run and record actual output for:
- python scripts/validate_dataset.py
- python scripts/test.py
- python -m pytest tests/test_dataset.py tests/test_metadata_output_safety.py -v
- python -m pytest -v (full CPU regression on a checkout with latest main plus PR changes)

A passing structural validator does not set the Offline Evaluation Harness gates review_approved or rights_approved. Official evaluation also requires frozen split, a dataset artifact reference with SHA-256, and official-test authorization before using held-out Test.

**Current status:** dataset snapshot and 11 flagged key-event rows reconciled; 30-source rights register handed over privately but rights clearance remains pending; human-gold acceptance remains separate. Do not merge or start official evaluation until full CPU regression on latest main and rights/review gates are evidenced.
