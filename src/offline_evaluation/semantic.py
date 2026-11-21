"""Human readiness và matching preparation; không dùng reviewer verdict làm gold."""

from .contracts import DiscrepancyLink, HumanAnnotation, SemanticCase
from .integrity import checked_copy, json_bytes, sha256_bytes, sha256_text


def _resolve(root, path):
    for part in path:
        if type(root) is dict and type(part) is str and part in root:
            root = root[part]
        elif type(root) is list and type(part) is int and 0 <= part < len(root):
            root = root[part]
        else:
            raise ValueError("Evidence/issue location không tồn tại.")
    return root


def _ground(issue, summary, snapshot, related=()):
    _resolve(snapshot, issue.location)
    for path in related:
        _resolve(snapshot, path)
    for evidence in issue.evidence:
        source = summary if evidence.source == "original_summary" else _resolve(snapshot, evidence.location)
        if not isinstance(source, str) or not evidence.quote.strip() or evidence.quote not in source:
            raise ValueError("Exact evidence quote không nằm tại declared source/location.")


def annotation_readiness(case: SemanticCase) -> dict:
    """Kiểm tra readiness/provenance; không tự xác nhận rubric, gold hoặc semantic truth."""
    case = checked_copy(case, SemanticCase)
    annotation = case.annotation
    if annotation.case_id != case.case_id:
        raise ValueError("Annotation belongs to a different case.")
    if annotation.original_summary_sha256 != sha256_text(case.original_summary):
        raise ValueError("Independent original summary hash mismatch.")
    if annotation.storyboard_sha256 != sha256_bytes(json_bytes(case.storyboard)):
        raise ValueError("Annotation storyboard hash mismatch (canonical evaluation serialization).")
    snapshot = case.storyboard.model_dump(mode="json")
    for finding in annotation.issues:
        _ground(finding.issue, case.original_summary, snapshot, finding.related_locations)
    ready = (annotation.human_review_state == "completed" and annotation.annotation_status == "confirmed"
             and annotation.verdict != "uncertain" and annotation.adjudicated
             and all(f.status == "confirmed" for f in annotation.issues)
             and annotation.rubric_version not in ("draft_not_approved", "pending"))
    return {"human_review_state": annotation.human_review_state, "gold_ready": ready,
            "confirmed_findings": sum(f.status == "confirmed" for f in annotation.issues),
            "uncertain_findings": sum(f.status == "uncertain" for f in annotation.issues),
            "unresolved_findings": sum(f.status == "uncertain" for f in annotation.issues),
            "prior_prediction_exposure": annotation.prior_prediction_exposure,
            "blind_annotation_claimed": False}


def blank_annotation(case_id: str, original_summary: str, storyboard, rubric_version: str) -> HumanAnnotation:
    """Template pending, không điền verdict/findings hoặc human approval."""
    from src.storyboard.schema import Storyboard

    checked = Storyboard.model_validate(storyboard)
    return HumanAnnotation(case_id=case_id, original_summary_sha256=sha256_text(original_summary),
                           storyboard_sha256=sha256_bytes(json_bytes(checked)), rubric_version=rubric_version,
                           human_review_state="pending_human_review")


def prepare_semantic_matches(case: SemanticCase, links: tuple[DiscrepancyLink, ...] = ()) -> dict:
    """One-to-one matching trên approved discrepancy crosswalk; không có semantic scorer.

    Hàm cố ý không tính precision/recall/F1, kể cả official inputs được gate sau này.
    Crosswalk do người review xác nhận; exact evidence chỉ chứng minh traceability.
    """
    case = checked_copy(case, SemanticCase)
    links = tuple(checked_copy(link, DiscrepancyLink) for link in links)
    readiness = annotation_readiness(case)
    if not readiness["gold_ready"]:
        raise ValueError("Human gold gate chưa mở; pending/uncertain không phải PASS.")
    report = case.reviewer_report
    if report.original_summary != case.original_summary or report.storyboard_snapshot != case.storyboard.model_dump(mode="json"):
        raise ValueError("Reviewer provenance không khớp annotation target.")
    if report.review_status != "completed":
        if links:
            raise ValueError("Failed/not_checked reviewer không có accepted prediction links.")
        return {"case_id": case.case_id, "readiness": readiness, "review_status": report.review_status,
                "verdict": None, "matching_status": "not_checked", "reason": "reviewer_unavailable",
                "matches": [], "unmatched_gold": None, "semantic_metrics": None}
    snapshot = case.storyboard.model_dump(mode="json")
    for prediction in report.issues:
        _ground(prediction, case.original_summary, snapshot)
    indices = [link.prediction_index for link in links]
    if len(indices) != len(set(indices)) or any(index >= len(report.issues) for index in indices):
        raise ValueError("Duplicate/out-of-range prediction crosswalk index.")
    crosswalk = {link.prediction_index: link.discrepancy_id for link in links}
    confirmed = [finding for finding in case.annotation.issues if finding.status == "confirmed"]
    uncertain = [finding for finding in case.annotation.issues if finding.status == "uncertain"]
    discrepancies = [finding.discrepancy_id for finding in case.annotation.issues]
    if len(discrepancies) != len(set(discrepancies)):
        raise ValueError("Gold discrepancy trùng; cần adjudicate thay vì đếm nhiều quotes thành nhiều issues.")
    if any(link.discrepancy_id not in discrepancies for link in links):
        raise ValueError("Crosswalk discrepancy không có human finding.")
    used, matches, duplicates, unmatched, excluded = set(), [], [], [], []
    for index, prediction in enumerate(report.issues):
        discrepancy = crosswalk.get(index)
        uncertain_candidates = [f for f in uncertain if f.discrepancy_id == discrepancy and f.issue.code == prediction.code
                                and tuple(prediction.location) in {tuple(f.issue.location), *f.related_locations}]
        if uncertain_candidates:
            excluded.append(index)
            continue
        candidates = [f for f in confirmed if f.discrepancy_id == discrepancy and f.issue.code == prediction.code
                      and tuple(prediction.location) in {tuple(f.issue.location), *f.related_locations}]
        if candidates:
            gold = candidates[0]
            if gold.finding_id in used:
                duplicates.append(index)
            else:
                used.add(gold.finding_id)
                matches.append({"prediction_index": index, "finding_id": gold.finding_id,
                                "discrepancy_id": gold.discrepancy_id,
                                "severity_agrees": prediction.severity == gold.issue.severity})
        else:
            unmatched.append(index)
    return {"case_id": case.case_id, "readiness": readiness, "review_status": "completed",
            "verdict": report.verdict, "matching_status": "prepared", "matches": matches,
            "unmatched_predictions": unmatched, "duplicate_predictions": duplicates,
            "excluded_uncertain_predictions": excluded,
            "unmatched_gold": [f.finding_id for f in confirmed if f.finding_id not in used],
            "excluded_uncertain_gold": [f.finding_id for f in uncertain],
            "unadjudicated_predictions": [i for i in range(len(report.issues)) if i not in crosswalk],
            "semantic_metrics": None}
