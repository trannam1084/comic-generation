"""Synthetic CPU fixtures ONLY: labels do test author khai báo, không official gold/inference."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from src.offline_evaluation import (
    EvaluationInput, EvaluationPlan, HumanAnnotation, InferenceCost, PairedCaseResult, annotation_readiness,
    blank_annotation, evaluate_pairs, json_bytes, parse_record, prepare_semantic_matches, sha256_bytes,
    sha256_text, verify_reference, write_session,
)
from src.offline_evaluation.contracts import (
    ArtifactReference, AnnotatedFinding, DatasetGates, DiscrepancyLink, PlannedCase, PlannedRun,
    SemanticCase, VariantResult,
)
from src.story_generator.repair import BoundedRepairController
from src.storyboard.schema import Storyboard
from src.storyboard.semantic_schema import SemanticEvidence, SemanticIssue, SemanticReviewResponse, SemanticValidationReport


@pytest.fixture
def board():
    # Independent invented source; không load examples hoặc dataset của TV3.
    return Storyboard.model_validate({
        "summary": "Lan gieo hạt, tưới cây, cây ra quả và Lan thu hoạch.",
        "characters": [{"id": "gardener", "visual": "A gardener wearing a blue hat."}],
        "scenes": [{"index": index, "caption_vi": caption, "image_prompt_en": prompt,
                    "characters": ["gardener"]} for index, caption, prompt in [
                        (1, "Lan gieo hạt.", "A gardener planting seeds."),
                        (2, "Lan tưới cây.", "A gardener watering plants."),
                        (3, "Cây ra quả.", "A gardener watching fruit grow."),
                        (4, "Lan thu hoạch.", "A gardener harvesting fruit."),
                    ]],
    })


class Scripted:
    def __init__(self, outputs):
        self.outputs = iter(outputs)

    def next(self):
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return value

    def generate(self, summary):
        return self.next()

    def generate_repair(self, feedback):
        return self.next()


def plan_for(*summaries):
    return EvaluationPlan(
        status="frozen", source_commit="a" * 40, model_revision="b" * 40,
        story_prompt_sha256="c" * 64, repair_prompt_sha256="d" * 64, policy_sha256="e" * 64,
        cases=tuple(PlannedCase(case_id=f"synthetic_{i}", original_summary_sha256=sha256_text(summary),
                                origin="synthetic_cpu_fixture") for i, summary in enumerate(summaries)),
        planned_runs=tuple(PlannedRun(case_id=f"synthetic_{i}", variant=variant)
                           for i in range(len(summaries)) for variant in ("B0", "B1")),
    )


def pair_for(board, initial, repairs=(), case_id="synthetic_0"):
    b0 = BoundedRepairController(Scripted([initial]), max_retries=0).generate(board.summary)
    backend = Scripted([initial, *repairs])
    b1 = BoundedRepairController(backend, backend, max_retries=2).generate(board.summary)
    pair = PairedCaseResult(
        case_id=case_id, original_summary=board.summary, initial_raw=initial,
        b0=VariantResult(variant="B0", state="completed", initial_raw_sha256=sha256_text(initial), result=b0),
        b1=VariantResult(variant="B1", state="failed" if b1.status == "backend_failure" else "completed",
                         initial_raw_sha256=sha256_text(initial), result=b1,
                         failure_category=b1.failure_category if b1.status == "backend_failure" else None),
    )
    costs = []
    for attempt in b1.attempts:
        costs.append(InferenceCost(
            case_id=case_id, call_id=f"{case_id}:{attempt.attempt_index}",
            attempt_index=attempt.attempt_index,
            purpose="story_generation" if attempt.attempt_index == 0 else "story_repair",
            state="failed" if attempt.failure_category == "backend_exception" else "completed",
            raw_sha256=sha256_text(attempt.raw_output) if attempt.raw_output is not None else None,
            prompt_sha256="f" * 64, input_tokens=10, generated_tokens=5,
            model_generation_seconds=1.0, backend_wall_seconds=2.0,
            peak_allocated_vram_bytes=100, hit_max_new_tokens=False,
        ))
    return pair, tuple(costs)


def replaced(record, **changes):
    """Allow deliberate invalid mutation for boundary validation tests."""
    return record.model_copy(update=changes, deep=True)


def test_initial_success_and_nonmutation(board):
    plan = plan_for(board.summary)
    pair, costs = pair_for(board, board.model_dump_json())
    before = json_bytes([plan, pair, costs])
    out = evaluate_pairs(plan, (pair,), costs)
    assert out["variants"]["B0"]["acceptance_planned"] == 1
    assert out["conditional_repair_success"] is None
    assert out["acceptance_improvement_pp"] == 0
    assert out["costs"]["physical"]["backend_invocations"] == 1
    assert out["semantic_evaluation"] == "not_checked"
    assert json_bytes([plan, pair, costs]) == before


@pytest.mark.parametrize("initial_kind", ["json", "schema", "summary"])
@pytest.mark.parametrize("repair_count", [1, 2])
def test_first_second_repair_accounting(board, initial_kind, repair_count):
    data = board.model_dump()
    if initial_kind == "schema":
        data["scenes"].pop()
    if initial_kind == "summary":
        data["summary"] = "Different summary."
    initial = "malformed" if initial_kind == "json" else json.dumps(data)
    pair, costs = pair_for(board, initial, ["still invalid"] * (repair_count - 1) + [board.model_dump_json()])
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs)
    assert out["first_repair_successes"] == (repair_count == 1)
    assert out["second_repair_successes"] == (repair_count == 2)
    assert out["conditional_repair_success"] == 1
    assert out["eligible_initial_failures"] == out["repair_cases_attempted"] == 1
    assert out["acceptance_improvement_pp"] == 100
    assert out["costs"]["physical"]["input_tokens"] == 10 * (1 + repair_count)
    assert out["costs"]["B0_logical"]["input_tokens"] == 10
    assert out["costs"]["B1_logical"]["input_tokens"] == 10 * (1 + repair_count)


def test_budget_exhausted(board):
    pair, costs = pair_for(board, "bad", ["bad again", "still bad"])
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs)
    assert out["variants"]["B1"]["statuses"]["budget_exhausted"] == 1
    assert out["conditional_repair_success"] == 0
    assert out["costs"]["physical"]["backend_invocations"] == 3


def test_failure_not_run_planned_denominators(board):
    first, costs = pair_for(board, "bad", [RuntimeError("synthetic infrastructure failure")])
    def absent(i, failed=False):
        return PairedCaseResult(case_id=f"synthetic_{i}", original_summary=board.summary,
                                initial_failure_category="loading_failure" if failed else None,
                                initial_failure_stage="backend" if failed else None,
                                b0=VariantResult(variant="B0", state="not_run", failure_category="stop_policy"),
                                b1=VariantResult(variant="B1", state="not_run", failure_category="stop_policy"))
    initial_failure = InferenceCost(call_id="failed-load", case_id="synthetic_2", attempt_index=0,
                                   purpose="story_generation", state="failed", prompt_sha256="f" * 64)
    out = evaluate_pairs(plan_for(*([board.summary] * 3)), (first, absent(1), absent(2, True)), (*costs, initial_failure))
    assert out["planned"] == 3 and out["attempted"] == 2
    assert out["completed_paired"] == 0
    assert out["failed_cases"] == 2 and out["not_run"] == 1 and out["partial_cases"] == 0
    assert out["paired_coverage"] == 0
    assert out["initial_infrastructure_failures"] == 1
    assert out["variants"]["B0"]["coverage"] == 1 / 3
    assert out["variants"]["B1"]["failed"] == 1
    assert out["variants"]["B1"]["not_run"] == 2
    assert out["conditional_repair_success"] == 0
    assert out["costs"]["physical"]["input_tokens"] is None
    assert out["costs"]["physical"]["input_tokens_known_subtotal"] == 20


def test_zero_planned_denominator():
    out = evaluate_pairs(plan_for(), (), ())
    assert out["variants"]["B0"]["coverage"] is None
    assert out["acceptance_improvement_pp"] is None
    assert out["conditional_repair_success"] is None
    assert out["costs"]["physical"]["backend_invocations"] == 0


def test_eligible_but_not_attempted(board):
    pair, costs = pair_for(board, "bad", [board.model_dump_json()])
    pair = replaced(pair, b1=VariantResult(variant="B1", state="not_run", failure_category="stop_policy"))
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs[:1])
    assert out["eligible_not_attempted"] == 1
    assert out["conditional_repair_success"] is None
    assert out["partial_cases"] == 1 and out["not_run"] == 0


@pytest.mark.parametrize("variant", ["b0", "b1"])
def test_same_raw_hash_enforced(board, variant):
    pair, costs = pair_for(board, board.model_dump_json())
    pair = replaced(pair, **{variant: replaced(getattr(pair, variant), initial_raw_sha256="0" * 64)})
    with pytest.raises(ValueError, match="initial raw"):
        evaluate_pairs(plan_for(board.summary), (pair,), costs)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "extra"])
def test_pair_inventory(board, kind):
    pair, costs = pair_for(board, board.model_dump_json())
    records = {"missing": (), "duplicate": (pair, pair), "extra": (pair, replaced(pair, case_id="unknown"))}[kind]
    with pytest.raises(ValueError, match="paired cases"):
        evaluate_pairs(plan_for(board.summary), records, costs)


@pytest.mark.parametrize("kind", ["duplicate_call_id", "duplicate_attempt", "missing", "extra", "wrong_raw", "wrong_purpose", "nonfinite"])
def test_malformed_cost_ledger(board, kind):
    pair, costs = pair_for(board, "bad", [board.model_dump_json()])
    if kind == "duplicate_call_id":
        costs = (costs[0], replaced(costs[1], call_id=costs[0].call_id))
    elif kind == "duplicate_attempt":
        costs = (*costs, costs[0])
    elif kind == "missing":
        costs = costs[:1]
    elif kind == "extra":
        costs = (*costs, replaced(costs[1], attempt_index=2, call_id="extra"))
    elif kind == "wrong_raw":
        costs = (costs[0], replaced(costs[1], raw_sha256="0" * 64))
    elif kind == "wrong_purpose":
        costs = (replaced(costs[0], purpose="story_repair"), costs[1])
    else:
        costs = (replaced(costs[0], model_generation_seconds=float("nan")), costs[1])
    with pytest.raises(ValueError):
        evaluate_pairs(plan_for(board.summary), (pair,), costs)


@pytest.mark.parametrize("kind", ["raw", "board", "report", "feedback", "attempt_index", "budget", "summary", "elapsed", "failure"])
def test_history_tampering_rejected(board, kind):
    pair, costs = pair_for(board, "bad", [board.model_dump_json()])
    result = pair.b1.result
    if kind == "board":
        changed = result.storyboard.model_copy(deep=True)
        changed.scenes[0].caption_vi = "A different candidate."
        result = replaced(result, storyboard=changed)
    elif kind == "budget":
        result = replaced(result, max_retries=1)
    elif kind == "summary":
        result = replaced(result, original_summary="Wrong source")
    elif kind == "elapsed":
        result = replaced(result, elapsed_seconds=-1.0)
    else:
        attempts = list(result.attempts)
        if kind == "raw":
            attempts[0] = replaced(attempts[0], raw_output="different initial")
        if kind == "report":
            attempts[0] = replaced(attempts[0], validation_report=attempts[1].validation_report)
        if kind == "feedback":
            attempts[1] = replaced(attempts[1], feedback=replaced(attempts[1].feedback, previous_raw_output="not latest"))
        if kind == "attempt_index":
            attempts[1] = replaced(attempts[1], attempt_index=2)
        if kind == "failure":
            attempts[1] = replaced(attempts[1], failure_category="backend_exception")
        result = replaced(result, attempts=tuple(attempts))
    pair = replaced(pair, b1=replaced(pair.b1, result=result))
    with pytest.raises(ValueError):
        evaluate_pairs(plan_for(board.summary), (pair,), costs)


def test_partial_validator_failure_is_not_exhaustion(board):
    pair, costs = pair_for(board, "bad", [board.model_dump_json()])
    history = (replaced(pair.b1.result.attempts[0], failure_category="validation_failure", validation_report=None),)
    pair = replaced(pair, b1=VariantResult(variant="B1", state="failed", failure_category="validation_failure",
                                         initial_raw_sha256=sha256_text("bad"), partial_history=history))
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs[:1])
    assert out["variants"]["B1"]["failed"] == 1
    assert out["eligible_not_attempted"] == 1


@pytest.mark.parametrize("kind", ["duplicate_cases", "missing_inventory", "duplicate_inventory", "official_test", "official_dev", "source_hash", "unknown_field", "bool_budget"])
def test_malformed_plan_and_records(board, kind):
    plan = plan_for(board.summary)
    data = json.loads(json_bytes(plan))
    if kind == "duplicate_cases":
        data["cases"] *= 2
    elif kind == "missing_inventory":
        data["planned_runs"].pop()
    elif kind == "duplicate_inventory":
        data["planned_runs"].append(data["planned_runs"][0])
    elif kind.startswith("official"):
        data["cases"][0]["origin"] = kind
    elif kind == "source_hash":
        data["source_commit"] = "not a commit"
    elif kind == "unknown_field":
        data["unexpected"] = 1
    else:
        with pytest.raises(ValidationError):
            InferenceCost(case_id="x", call_id="c", purpose="story_generation", attempt_index=True,
                          state="completed", prompt_sha256="0" * 64)
        return
    with pytest.raises(ValidationError):
        parse_record(json.dumps(data).encode("utf-8"), EvaluationPlan)


@pytest.mark.parametrize("raw", [b'{"x":1,"x":2}', b'{"nested":{"x":1,"x":2}}', b'{"x":NaN}', b'{"x":Infinity}', b'{"x":1e999}', b'{"x":"\\ud800"}', b'{', b'\xff'])
def test_strict_record_json(raw):
    with pytest.raises((ValueError, UnicodeError)):
        parse_record(raw, EvaluationPlan)


@pytest.mark.parametrize("hash_value", ["", "a" * 63, "A" * 64, "g" * 64, True])
def test_invalid_sha_references(hash_value):
    with pytest.raises(ValidationError):
        ArtifactReference(artifact_id="fixture", sha256=hash_value)


def test_reference_bytes_and_write_once(tmp_path):
    payload = "Dữ liệu kiểm thử 😀".encode("utf-8")
    reference = ArtifactReference(artifact_id="synthetic-fixture", sha256=sha256_bytes(payload))
    verify_reference(reference, payload)
    with pytest.raises(ValueError):
        verify_reference(reference, payload + b" ")
    first = write_session(tmp_path, {"result.json": payload})
    second = write_session(tmp_path, {"result.json": b"new"})
    assert first != second and (first / "result.json").read_bytes() == payload
    assert json.loads((first / "checksums.json").read_text(encoding="utf-8")) == {"result.json": reference.sha256}


@pytest.mark.parametrize("name", ["../escape", "/tmp/escape", "a/b", "a\\b", "C:escape", "checksums.json", "..", ""])
def test_unsafe_artifact_paths(tmp_path, name):
    with pytest.raises(ValueError):
        write_session(tmp_path / "unused", {name: b"data"})
    assert not (tmp_path / "unused").exists()


def issue_for(board, **kwargs):
    return SemanticIssue(code="MISSING_KEY_EVENT", severity="error", location=["scenes", 1, "caption_vi"],
                         message="Synthetic matching claim; not human gold.",
                         evidence=[SemanticEvidence(source="original_summary", location=[], quote=board.summary)], **kwargs)


def semantic_case(board, *, state="completed", status="confirmed", adjudicated=True, review_status="completed", findings=None, predictions=None):
    finding = AnnotatedFinding(finding_id="f1", discrepancy_id="d1", issue=issue_for(board), status="confirmed",
                               related_locations=(("scenes", 2, "caption_vi"),))
    findings = (finding,) if findings is None else findings
    predictions = [issue_for(board)] if predictions is None else predictions
    annotation = HumanAnnotation(case_id="synthetic_semantic", original_summary_sha256=sha256_text(board.summary),
                                 storyboard_sha256=sha256_bytes(json_bytes(board)), rubric_version="synthetic-test-rubric-v1",
                                 annotator="test-author", review_date="2026-11-21", human_review_state=state,
                                 annotation_status=status if state == "completed" else None,
                                 adjudicated=adjudicated if state == "completed" else False,
                                 verdict="fail" if state == "completed" else None, issues=findings)
    response = SemanticReviewResponse(verdict="fail", explanation="Synthetic claim.", issues=predictions) if review_status == "completed" else None
    report = SemanticValidationReport(review_status=review_status, response=response,
                                      error_category="reviewer_backend_failure" if review_status == "failed" else None,
                                      original_summary=board.summary, storyboard_snapshot=board.model_dump(mode="json"))
    return SemanticCase(case_id="synthetic_semantic", original_summary=board.summary, storyboard=board,
                        annotation=annotation, reviewer_report=report)


def link(index=0, discrepancy="d1"):
    return DiscrepancyLink(prediction_index=index, discrepancy_id=discrepancy, confirmed_by="synthetic-adjudicator")


@pytest.mark.parametrize("state", ["pending_human_review", "in_progress"])
def test_pending_never_becomes_pass(board, state):
    case = semantic_case(board, state=state)
    assert not annotation_readiness(case)["gold_ready"]
    with pytest.raises(ValueError, match="gold gate"):
        prepare_semantic_matches(case)
    with pytest.raises(ValidationError):
        parse_record(json_bytes(replaced(case.annotation, verdict="pass")), HumanAnnotation)


def test_one_to_one_duplicates_and_severity_separate(board):
    prediction = issue_for(board)
    warning = replaced(prediction, severity="warning")
    case = semantic_case(board, predictions=[prediction, warning])
    out = prepare_semantic_matches(case, (link(), link(1)))
    assert len(out["matches"]) == 1
    assert out["duplicate_predictions"] == [1] and not out["unmatched_gold"]
    assert out["semantic_metrics"] is None
    case = semantic_case(board, predictions=[warning, prediction])
    assert prepare_semantic_matches(case, (link(), link(1)))["matches"][0]["severity_agrees"] is False


@pytest.mark.parametrize("kind", ["case", "code", "discrepancy", "location", "parent", "root"])
def test_semantic_match_identity_not_quote_only(board, kind):
    case = semantic_case(board)
    if kind == "case":
        case = replaced(case, annotation=replaced(case.annotation, case_id="other"))
        with pytest.raises(ValueError):
            prepare_semantic_matches(case, (link(),))
        return
    prediction = case.reviewer_report.issues[0]
    if kind == "code":
        prediction = replaced(prediction, code="ENDING_CONTRADICTION")
    elif kind in ("location", "parent", "root"):
        path = {"location": ["scenes", 0, "caption_vi"], "parent": ["scenes"], "root": []}[kind]
        prediction = replaced(prediction, location=path)
    elif kind == "discrepancy":
        out = prepare_semantic_matches(case)  # No human crosswalk: no automatic semantic identity.
        assert not out["matches"] and out["unadjudicated_predictions"] == [0]
        return
    case = semantic_case(board, predictions=[prediction])
    assert not prepare_semantic_matches(case, (link(),))["matches"]


def test_related_location_can_match(board):
    prediction = replaced(issue_for(board), location=["scenes", 2, "caption_vi"])
    out = prepare_semantic_matches(semantic_case(board, predictions=[prediction]), (link(),))
    assert len(out["matches"]) == 1


@pytest.mark.parametrize("kind", ["wrong_field", "wrong_source", "blank", "invalid_path", "bool_index", "nfc_nfd"])
def test_traceable_exact_evidence_required(board, kind):
    issue = issue_for(board)
    if kind == "wrong_field":
        ev = SemanticEvidence(source="storyboard", location=["scenes", 1, "caption_vi"], quote=board.scenes[0].caption_vi)
    elif kind == "wrong_source":
        ev = SemanticEvidence(source="storyboard", location=["summary"], quote="Different independent source")
    elif kind == "blank":
        ev = replaced(issue.evidence[0], quote="  ")
    elif kind == "invalid_path":
        ev = SemanticEvidence(source="storyboard", location=["scenes", 100, "caption_vi"], quote="text")
    elif kind == "bool_index":
        ev = replaced(issue.evidence[0], source="storyboard", location=["scenes", True, "caption_vi"])
    else:
        import unicodedata
        ev = SemanticEvidence(source="original_summary", location=[], quote=unicodedata.normalize("NFD", board.summary))
    case = semantic_case(board, predictions=[replaced(issue, evidence=[ev])])
    with pytest.raises(ValueError):
        prepare_semantic_matches(case, (link(),))


def test_uncertain_findings_not_confirmed_gold(board):
    certain = AnnotatedFinding(finding_id="f1", discrepancy_id="d1", issue=issue_for(board), status="confirmed")
    uncertain = replaced(certain, finding_id="f2", discrepancy_id="d2", status="uncertain",
                         issue=replaced(certain.issue, severity="warning"))
    # Task11A.3 requires a full-case gold gate, replacing the earlier subset policy.
    case = semantic_case(board, findings=(certain, uncertain), status="uncertain", adjudicated=False,
                         predictions=[issue_for(board), issue_for(board)])
    assert annotation_readiness(case)["gold_ready"] is False
    assert annotation_readiness(case)["uncertain_findings"] == 1
    with pytest.raises(ValueError, match="gold gate"):
        prepare_semantic_matches(case, (link(), link(1, "d2")))
    assert case.annotation.issues[1].status == "uncertain"


@pytest.mark.parametrize("status", ["failed", "not_checked"])
def test_reviewer_failure_never_semantic_fail(board, status):
    out = prepare_semantic_matches(semantic_case(board, review_status=status))
    assert out["verdict"] is None and out["matching_status"] == "not_checked"
    assert out["unmatched_gold"] is None and out["semantic_metrics"] is None


def test_unknown_semantic_code_and_no_automatic_model_loading(board):
    with pytest.raises(ValidationError):
        parse_record(json_bytes(replaced(issue_for(board), code="SUMMARY_MISMATCH")), SemanticIssue)
    script = '''
import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','transformers','diffusers','gradio','yaml'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
def audit(event,args):
    if event in {'socket.connect','socket.getaddrinfo'}:raise AssertionError(event)
sys.addaudithook(audit)
import src.offline_evaluation
'''
    result = subprocess.run([sys.executable, "-X", "utf8=0", "-c", script],
                            cwd=Path(__file__).resolve().parents[1], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_blank_annotation_roundtrip_is_pending(board):
    annotation = blank_annotation("synthetic_semantic", board.summary, board, "draft_not_approved")
    assert annotation.verdict is None and annotation.issues == () and not annotation.adjudicated
    assert annotation.annotator is None and annotation.review_date is None
    assert parse_record(json_bytes(annotation), HumanAnnotation) == annotation


@pytest.mark.parametrize("kind", ["original_hash", "storyboard_hash", "report_summary", "report_snapshot", "human_location"])
def test_semantic_provenance_mismatch(board, kind):
    case = semantic_case(board)
    if kind in ("original_hash", "storyboard_hash"):
        key = "original_summary_sha256" if kind == "original_hash" else "storyboard_sha256"
        case = replaced(case, annotation=replaced(case.annotation, **{key: "0" * 64}))
    elif kind == "report_summary":
        case = replaced(case, reviewer_report=replaced(case.reviewer_report, original_summary="Wrong independent input"))
    elif kind == "report_snapshot":
        case = replaced(case, reviewer_report=replaced(case.reviewer_report, storyboard_snapshot={}))
    else:
        finding = case.annotation.issues[0]
        finding = replaced(finding, related_locations=(("scenes", 9, "caption_vi"),))
        case = replaced(case, annotation=replaced(case.annotation, issues=(finding,)))
    with pytest.raises(ValueError):
        prepare_semantic_matches(case, (link(),))


def test_independent_summary_evidence_with_storyboard_mismatch(board):
    board = board.model_copy(deep=True)
    board.summary = "An unrelated storyboard summary."
    source = "Đây là independent source và không bị overwrite."
    case = semantic_case(board)
    issue = replaced(issue_for(board), evidence=[SemanticEvidence(source="original_summary", location=[], quote=source)])
    finding = replaced(case.annotation.issues[0], issue=issue)
    annotation = replaced(case.annotation, original_summary_sha256=sha256_text(source), issues=(finding,))
    response = SemanticReviewResponse(verdict="fail", explanation="Synthetic claim.", issues=[issue])
    case = replaced(case, original_summary=source, annotation=annotation,
                    reviewer_report=replaced(case.reviewer_report, original_summary=source, response=response))
    assert len(prepare_semantic_matches(case, (link(),))["matches"]) == 1
    wrong = replaced(issue, evidence=[SemanticEvidence(source="original_summary", location=[], quote=board.summary)])
    case = replaced(case, reviewer_report=replaced(case.reviewer_report, response=replaced(response, issues=[wrong])))
    with pytest.raises(ValueError):
        prepare_semantic_matches(case, (link(),))


@pytest.mark.parametrize("kind", ["unadjudicated", "uncertain_case", "draft_rubric", "uncertain_verdict"])
def test_gold_gates_are_not_implicit(board, kind):
    case = semantic_case(board)
    changes = {"unadjudicated": {"adjudicated": False},
               "uncertain_case": {"annotation_status": "uncertain", "adjudicated": False},
               "draft_rubric": {"rubric_version": "draft_not_approved"},
               "uncertain_verdict": {"verdict": "uncertain", "issues": ()}}[kind]
    case = replaced(case, annotation=replaced(case.annotation, **changes))
    assert not annotation_readiness(case)["gold_ready"]
    with pytest.raises(ValueError):
        prepare_semantic_matches(case)


@pytest.mark.parametrize("links", [(link(100),), (link(), link()), (link(0, "unknown"),)])
def test_invalid_discrepancy_crosswalk(board, links):
    with pytest.raises(ValueError):
        prepare_semantic_matches(semantic_case(board), links)


def test_empty_prediction_and_confirmed_clean_are_distinct(board):
    case = semantic_case(board)
    response = SemanticReviewResponse(verdict="pass", explanation="Synthetic empty result.", issues=[])
    case = replaced(case, reviewer_report=replaced(case.reviewer_report, response=response))
    out = prepare_semantic_matches(case)
    assert out["unmatched_gold"] == ["f1"] and out["verdict"] == "pass"
    # A clean confirmed human case requires explicit completed + adjudicated PASS.
    case = replaced(case, annotation=replaced(case.annotation, verdict="pass", issues=()))
    out = prepare_semantic_matches(case)
    assert out["readiness"]["gold_ready"] and out["unmatched_gold"] == []
    assert out["semantic_metrics"] is None


def test_exact_nfd_and_emoji_evidence_supported(board):
    import unicodedata

    board = board.model_copy(deep=True)
    board.summary = unicodedata.normalize("NFD", board.summary) + " 😀"
    case = semantic_case(board)
    assert len(prepare_semantic_matches(case, (link(),))["matches"]) == 1


def test_warning_only_initial_does_not_repair(board):
    board = board.model_copy(deep=True)
    board.characters.append(board.characters[0].model_copy(update={"id": "unused"}))
    pair, costs = pair_for(board, board.model_dump_json())
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs)
    assert out["variants"]["B1"]["accepted_initial"] == 1
    assert out["eligible_initial_failures"] == 0
    assert out["costs"]["physical"]["backend_invocations"] == 1


def test_json_schema_pass_separate_from_summary_gate(board):
    data = board.model_dump()
    data["summary"] = "Different summary"
    pair, costs = pair_for(board, json.dumps(data), [board.model_dump_json()])
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs)
    assert out["initial_json_schema_pass"] == 1 and out["initial_accepted"] == 0
    assert out["per_case_final"][0]["variants"]["B1"]["final_summary_matching"] == "passed"


def test_official_gate_requires_complete_approvals_but_never_opens_data(board, monkeypatch):
    plan = plan_for(board.summary)
    data = json.loads(json_bytes(plan))
    data["cases"][0]["origin"] = "official_test"
    data["gates"] = {"split_frozen": True, "review_approved": True, "rights_approved": True,
                     "official_test_authorized": True,
                     "dataset_reference": {"artifact_id": "future-approved-split", "sha256": "a" * 64}}
    def forbidden(*args, **kwargs):
        raise AssertionError("Dataset filesystem reads forbidden")
    monkeypatch.setattr(Path, "open", forbidden)
    validated = parse_record(json_bytes(data), EvaluationPlan)
    assert validated.gates.official_test_authorized


def test_literal_surrogate_record_rejected_and_fixture_utf8_roundtrip(board):
    with pytest.raises(UnicodeError):
        json_bytes({"input": "\ud800"})
    plan = plan_for(board.summary)
    assert parse_record(json_bytes(plan), EvaluationPlan) == plan


def test_actual_offline_cli_synthetic_batch(tmp_path, board):
    pair, costs = pair_for(board, "invalid JSON", [board.model_dump_json()])
    batch = EvaluationInput(plan=plan_for(board.summary), pairs=(pair,), costs=costs)
    payload = json_bytes(batch)
    source = tmp_path / "synthetic_batch.json"
    source.write_bytes(payload)
    root = Path(__file__).resolve().parents[1]
    command = [sys.executable, "-X", "utf8=0", "-m", "src.offline_evaluation", "--input", str(source),
               "--expected-sha256", sha256_bytes(payload), "--output-root", str(tmp_path / "outputs")]
    completed = subprocess.run(command, cwd=root, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr
    session = Path(completed.stdout.strip())
    aggregate = json.loads((session / "aggregates.json").read_text(encoding="utf-8"))
    assert aggregate["variants"]["B0"]["accepted"] == 0
    assert aggregate["variants"]["B1"]["accepted"] == 1
    assert aggregate["costs"]["physical"]["backend_invocations"] == 2
    manifest = json.loads((session / "checksums.json").read_text(encoding="utf-8"))
    assert set(manifest) == {"aggregates.json", "plan.json", "input_reference.json"}
    for name, digest in manifest.items():
        assert sha256_bytes((session / name).read_bytes()) == digest
    command[command.index("--expected-sha256") + 1] = "0" * 64
    failed = subprocess.run(command, cwd=root, capture_output=True, text=True)
    assert failed.returncode != 0
    assert len(list((tmp_path / "outputs").iterdir())) == 1
    assert source.read_bytes() == payload


def test_deterministic_failure_cannot_be_reclassified_as_backend_failure(board):
    pair, costs = pair_for(board, "bad", ["bad", "bad"])
    result = replaced(pair.b1.result, status="backend_failure", failure_category="deterministic_validation_failure")
    pair = replaced(pair, b1=replaced(pair.b1, state="failed", result=result,
                                     failure_category="deterministic_validation_failure"))
    with pytest.raises(ValueError, match="Backend failure"):
        evaluate_pairs(plan_for(board.summary), (pair,), costs)


def test_failure_wrapper_must_match_result_category(board):
    pair, costs = pair_for(board, "bad", [RuntimeError("synthetic loading failure")])
    pair = replaced(pair, b1=replaced(pair.b1, failure_category="validation_failure"))
    with pytest.raises(ValueError, match="category"):
        evaluate_pairs(plan_for(board.summary), (pair,), costs)


def test_backend_failure_before_model_generate_has_zero_observed_model_calls(board):
    pair = PairedCaseResult(case_id="synthetic_0", original_summary=board.summary,
                            initial_failure_category="loading_failure", initial_failure_stage="backend",
                            b0=VariantResult(variant="B0", state="not_run", failure_category="initial_failure"),
                            b1=VariantResult(variant="B1", state="not_run", failure_category="initial_failure"))
    cost = InferenceCost(call_id="synthetic-load-failure", case_id="synthetic_0", purpose="story_generation",
                         attempt_index=0, state="failed", prompt_sha256="a" * 64,
                         model_generate_calls=0, model_generate_count_source="observed")
    out = evaluate_pairs(plan_for(board.summary), (pair,), (cost,))
    assert out["attempted"] == 1 and out["initial_infrastructure_failures"] == 1
    assert out["costs"]["physical"]["backend_invocations"] == 1
    assert out["costs"]["physical"]["model_generate_calls"] == 0
    assert out["costs"]["physical"]["model_generation_seconds"] is None


def test_missing_latency_and_model_call_observation_are_not_measured_zero(board):
    pair, costs = pair_for(board, board.model_dump_json())
    missing = replaced(costs[0], model_generation_seconds=None)
    out = evaluate_pairs(plan_for(board.summary), (pair,), (missing,))
    assert out["costs"]["physical"]["model_generation_seconds"] is None
    assert out["costs"]["physical"]["model_generation_seconds_status"] == "not_available"
    assert out["costs"]["physical"]["model_generate_calls"] is None
    zero = replaced(missing, model_generation_seconds=0.0, model_generate_calls=0,
                    model_generate_count_source="observed")
    # A completed backend cannot return a generated raw while claiming no generation.
    with pytest.raises(ValueError):
        evaluate_pairs(plan_for(board.summary), (pair,), (zero,))
    zero = replaced(zero, model_generate_calls=1)
    out = evaluate_pairs(plan_for(board.summary), (pair,), (zero,))
    assert out["costs"]["physical"]["model_generation_seconds"] == 0.0
    assert out["costs"]["physical"]["model_generation_seconds_status"] == "available"


def test_input_failure_does_not_fabricate_backend_or_model_calls():
    summary = "  "
    pair = PairedCaseResult(case_id="synthetic_0", original_summary=summary,
                            initial_failure_stage="input_validation", initial_failure_category="invalid_summary",
                            b0=VariantResult(variant="B0", state="not_run", failure_category="input_failure"),
                            b1=VariantResult(variant="B1", state="not_run", failure_category="input_failure"))
    out = evaluate_pairs(plan_for(summary), (pair,), ())
    assert out["planned"] == out["attempted"] == out["failed_cases"] == out["initial_input_failures"] == 1
    assert out["initial_infrastructure_failures"] == 0 and out["not_run"] == 0
    assert out["costs"]["physical"]["backend_invocations"] == 0
    assert out["costs"]["physical"]["model_generate_calls"] == 0
    assert out["variants"]["B0"]["acceptance_planned"] == 0


def test_same_code_location_but_different_adjudicated_discrepancy_does_not_match(board):
    case = semantic_case(board)
    second = replaced(case.annotation.issues[0], finding_id="f2", discrepancy_id="d2")
    case = replaced(case, annotation=replaced(case.annotation, issues=(*case.annotation.issues, second)))
    out = prepare_semantic_matches(case, (link(0, "d2"),))
    assert [match["finding_id"] for match in out["matches"]] == ["f2"]
    assert out["unmatched_gold"] == ["f1"]


def test_repair_loading_failure_in_denominator_without_extra_model_call(board):
    pair, costs = pair_for(board, "bad", [RuntimeError("synthetic repair load failure")])
    initial = replaced(costs[0], model_generate_calls=1, model_generate_count_source="observed")
    repair = replaced(costs[1], model_generate_calls=0, model_generate_count_source="observed",
                      input_tokens=None, generated_tokens=None, model_generation_seconds=None,
                      peak_allocated_vram_bytes=None, hit_max_new_tokens=None)
    out = evaluate_pairs(plan_for(board.summary), (pair,), (initial, repair))
    assert out["eligible_initial_failures"] == out["repair_cases_attempted"] == 1
    assert out["repair_backend_failure_cases"] == 1 and out["conditional_repair_success"] == 0
    assert out["costs"]["physical"]["backend_invocations"] == 2
    assert out["costs"]["physical"]["model_generate_calls"] == 1
    assert out["costs"]["B0_logical"]["model_generate_calls"] == 1
    assert out["costs"]["B1_logical"]["model_generate_calls"] == 1
    assert out["costs"]["physical"]["model_generation_seconds"] is None
    assert out["costs"]["physical"]["model_generation_seconds_status"] == "partial"


@pytest.mark.parametrize("changes", [
    {"model_generate_calls": True, "model_generate_count_source": "observed"},
    {"model_generate_calls": 1},
    {"model_generate_count_source": "observed"},
    {"model_generate_calls": 2, "model_generate_count_source": "observed"},
])
def test_invalid_or_inferred_model_count_is_rejected(board, changes):
    pair, costs = pair_for(board, board.model_dump_json())
    with pytest.raises(ValueError):
        evaluate_pairs(plan_for(board.summary), (pair,), (replaced(costs[0], **changes),))


def root_case(board, *, prediction_locations=([],), gold_location=(), related_locations=()):
    predictions = [replaced(issue_for(board), location=path) for path in prediction_locations]
    case = semantic_case(board, predictions=predictions)
    finding = replaced(case.annotation.issues[0], issue=replaced(issue_for(board), location=list(gold_location)),
                       related_locations=related_locations)
    return replaced(case, annotation=replaced(case.annotation, issues=(finding,)))


def test_exact_root_matches_exact_gold_root(board):
    out = prepare_semantic_matches(root_case(board), (link(),))
    assert len(out["matches"]) == 1 and not out["unmatched_gold"]


@pytest.mark.parametrize("prediction_root", [True, False])
def test_root_and_scene_locations_are_not_wildcards(board, prediction_root):
    scene = ("scenes", 0, "caption_vi")
    case = root_case(board, prediction_locations=([] if prediction_root else list(scene),),
                     gold_location=scene if prediction_root else ())
    out = prepare_semantic_matches(case, (link(),))
    assert not out["matches"] and out["unmatched_predictions"] == [0]
    assert out["unmatched_gold"] == ["f1"]


@pytest.mark.parametrize("prediction_root", [True, False])
def test_root_related_locations_must_be_explicit(board, prediction_root):
    scene = ("scenes", 0, "caption_vi")
    case = root_case(board, prediction_locations=([] if prediction_root else list(scene),),
                     gold_location=scene if prediction_root else (),
                     related_locations=((),) if prediction_root else (scene,))
    assert len(prepare_semantic_matches(case, (link(),))["matches"]) == 1


def test_duplicate_root_predictions_still_match_once(board):
    case = root_case(board, prediction_locations=([], []))
    out = prepare_semantic_matches(case, (link(), link(1)))
    assert len(out["matches"]) == 1 and out["duplicate_predictions"] == [1]
    assert not out["unmatched_gold"]


def test_unresolved_findings_cannot_open_full_gold_gate(board):
    case = semantic_case(board)
    tentative = replaced(case.annotation.issues[0], finding_id="tentative", discrepancy_id="d2",
                         status="uncertain", issue=replaced(issue_for(board), severity="warning"))
    # Inconsistent imported flags must be rejected, not treated as human approval.
    invalid = replaced(case, annotation=replaced(case.annotation, issues=(*case.annotation.issues, tentative)))
    with pytest.raises(ValueError, match="Unresolved"):
        annotation_readiness(invalid)
    with pytest.raises(ValueError, match="Unresolved"):
        prepare_semantic_matches(invalid, (link(),))
    case = replaced(invalid, annotation=replaced(invalid.annotation, annotation_status="uncertain", adjudicated=False))
    before = json_bytes(case)
    readiness = annotation_readiness(case)
    assert case.annotation.verdict == "fail" and case.annotation.human_review_state == "completed"
    assert readiness["gold_ready"] is False and readiness["unresolved_findings"] == 1
    with pytest.raises(ValueError, match="gold gate"):
        prepare_semantic_matches(case, (link(),))
    assert json_bytes(case) == before
    assert case.annotation.issues[1].status == "uncertain"
    assert not case.annotation.adjudicated


def test_uncertain_error_severity_is_rejected_without_downgrading(board):
    finding = semantic_case(board).annotation.issues[0]
    invalid = replaced(finding, status="uncertain")
    with pytest.raises(ValueError, match="warning"):
        parse_record(json_bytes(invalid), AnnotatedFinding)
    assert invalid.issue.severity == "error" and invalid.status == "uncertain"
    valid = replaced(invalid, issue=replaced(invalid.issue, severity="warning"))
    checked = parse_record(json_bytes(valid), AnnotatedFinding)
    assert checked.status == "uncertain" and checked.issue.severity == "warning"


def test_fully_confirmed_adjudicated_findings_open_gold_gate_without_inventing_approval(board):
    case = semantic_case(board)
    assert annotation_readiness(case)["gold_ready"] is True
    assert annotation_readiness(case)["unresolved_findings"] == 0
    unapproved = replaced(case, annotation=replaced(case.annotation, adjudicated=False))
    before = json_bytes(unapproved)
    assert annotation_readiness(unapproved)["gold_ready"] is False
    with pytest.raises(ValueError, match="gold gate"):
        prepare_semantic_matches(unapproved, (link(),))
    assert json_bytes(unapproved) == before and not unapproved.annotation.adjudicated


def test_logical_cost_attribution_is_not_variant_execution_count(board):
    pair, costs = pair_for(board, board.model_dump_json())
    pair = replaced(pair, b0=VariantResult(variant="B0", state="not_run", failure_category="stop_policy"))
    out = evaluate_pairs(plan_for(board.summary), (pair,), costs)
    assert out["variants"]["B0"]["attempted"] == 0 and out["variants"]["B0"]["not_run"] == 1
    assert out["variants"]["B1"]["attempted"] == 1
    assert out["costs"]["physical"]["backend_invocations"] == 1
    assert out["costs"]["B0_logical"]["backend_invocations"] == 1
    assert out["costs"]["B1_logical"]["backend_invocations"] == 1
