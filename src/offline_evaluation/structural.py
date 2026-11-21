"""Offline paired B0/B1 validation/aggregation; không generation hoặc repair orchestration."""

from collections import Counter
import math

from src.storyboard.schema import Storyboard
from src.storyboard.validator import StoryboardValidator

from .contracts import EvaluationPlan, InferenceCost, PairedCaseResult
from .integrity import checked_copy, json_bytes, sha256_bytes, sha256_text

ACCEPTED = {"accepted_initial", "accepted_after_repair"}


def ratio(numerator: int, denominator: int) -> float | None:
    return numerator / denominator if denominator else None


def _history(variant):
    return variant.result.attempts if variant.result is not None else variant.partial_history


def _validate_history(pair, variant) -> None:
    budget = 0 if variant.variant == "B0" else 2
    result = variant.result
    attempts = _history(variant)
    if result is not None:
        if result.original_summary != pair.original_summary or result.max_retries != budget:
            raise ValueError("Controller summary/budget không khớp frozen paired design.")
        if not math.isfinite(result.elapsed_seconds) or result.elapsed_seconds < 0:
            raise ValueError("Invalid controller elapsed time.")
    if len(attempts) > 1 + budget:
        raise ValueError("Attempt history vượt retry budget.")
    if variant.state == "completed" and not attempts:
        raise ValueError("Completed history không được rỗng.")
    for index, attempt in enumerate(attempts):
        if attempt.attempt_index != index or attempt.generation_kind != ("initial" if index == 0 else "repair"):
            raise ValueError("Attempt order/kind không hợp lệ.")
        if not math.isfinite(attempt.elapsed_seconds) or attempt.elapsed_seconds < 0:
            raise ValueError("Invalid attempt elapsed time.")
        if index == 0:
            if attempt.raw_output != pair.initial_raw or attempt.feedback is not None:
                raise ValueError("Replay initial raw không khớp frozen candidate.")
        else:
            previous = attempts[index - 1]
            if previous.failure_category != "deterministic_validation_failure" or previous.validation_report is None:
                raise ValueError("Repair sau infrastructure failure hoặc accepted output.")
            feedback = attempt.feedback
            if (feedback is None or feedback.original_summary != pair.original_summary
                    or feedback.previous_raw_output != previous.raw_output or feedback.attempt_index != index):
                raise ValueError("Repair feedback không tham chiếu latest failed attempt.")
            expected = []
            for issue in previous.validation_report.issues:
                if issue.severity == "error":
                    item = issue.model_dump(mode="json")
                    if issue.code == "SCHEMA_VIOLATION":
                        item["evidence"] = {"validation_type": issue.evidence["pydantic_error"]["type"]}
                    expected.append(item)
            if json_bytes(feedback.errors) != json_bytes(expected):
                raise ValueError("Repair errors không khớp latest deterministic report.")
        report = attempt.validation_report
        if attempt.raw_output is not None and attempt.raw_output_preservation != "verbatim":
            raise ValueError("Raw preservation label không khớp raw text.")
        if report is not None:
            if attempt.raw_output is None:
                raise ValueError("Validation report không có corresponding raw.")
            actual = StoryboardValidator().validate_raw(attempt.raw_output, expected_summary=pair.original_summary)
            if json_bytes(actual) != json_bytes(report):
                raise ValueError("Stored validation report không khớp production revalidation.")
            accepted = all(getattr(actual, key) == "passed" for key in (
                "json_syntax", "structural_validity", "summary_matching"
            ))
            if accepted and index != len(attempts) - 1:
                raise ValueError("Hidden extra attempt sau accepted candidate.")
            if attempt.failure_category not in (None, "validation_failure", "deterministic_validation_failure"):
                raise ValueError("Validation report đi kèm incompatible infrastructure category.")
            if attempt.failure_category != "validation_failure":
                expected_failure = None if accepted else "deterministic_validation_failure"
                if attempt.failure_category != expected_failure:
                    raise ValueError("Attempt acceptance/failure category mâu thuẫn.")
        elif attempt.failure_category not in (
            "validation_failure", "backend_exception", "backend_output_type", "invalid_output_unicode"
        ):
            raise ValueError("Missing validation report không phải infrastructure failure hợp lệ.")
    if result is None:
        if attempts and attempts[-1].failure_category != "validation_failure":
            raise ValueError("Partial controller history phải kết thúc ở validation_failure.")
        return
    accepted = result.status in ACCEPTED
    if accepted:
        last = attempts[-1] if attempts else None
        if last is None or last.validation_report is None or last.validation_report.production_success is not True:
            raise ValueError("Accepted result thiếu accepted raw/report.")
        if last.failure_category is not None or result.failure_category is not None or result.storyboard is None:
            raise ValueError("Accepted result có failure hoặc thiếu Storyboard.")
        parsed = Storyboard.model_validate_json(last.raw_output)
        if json_bytes(parsed) != json_bytes(result.storyboard):
            raise ValueError("Accepted storyboard khác accepted raw.")
        if (result.status == "accepted_initial") != (len(attempts) == 1):
            raise ValueError("Accepted status không khớp actual attempt count.")
    elif result.storyboard is not None:
        raise ValueError("Failed/exhausted result không được có accepted Storyboard.")
    if result.status == "budget_exhausted":
        if len(attempts) != 1 + budget or any(a.failure_category != "deterministic_validation_failure" for a in attempts):
            raise ValueError("Budget-exhausted history không khớp budget/validation failures.")
        if result.failure_category != "repair_budget_exhausted":
            raise ValueError("Wrong exhaustion category.")
    if result.status == "backend_failure":
        if (result.failure_category not in ("backend_exception", "backend_output_type", "invalid_output_unicode")
                or not attempts or attempts[-1].failure_category != result.failure_category
                or attempts[-1].validation_report is not None):
            raise ValueError("Backend failure thiếu corresponding failed attempt.")
    if result.status == "input_failure":
        raise ValueError("Input failure phải ở pre-initial record, không replay frozen raw.")


def _sum_costs(calls: list[InferenceCost]) -> dict:
    # Không biến unknown metric thành zero; empty actual ledger thật sự có zero cost.
    result = {"backend_invocations": len(calls)}
    model_counts = [c.model_generate_calls for c in calls if c.model_generate_calls is not None]
    result["model_generate_calls"] = sum(model_counts) if len(model_counts) == len(calls) else None
    result["model_generate_calls_known_subtotal"] = sum(model_counts)
    result["model_generate_calls_coverage"] = len(model_counts)
    result["model_generate_calls_status"] = ("available" if len(model_counts) == len(calls)
                                               else "partial" if model_counts else "not_available")
    for field in ("input_tokens", "generated_tokens", "model_generation_seconds", "backend_wall_seconds"):
        known = [getattr(call, field) for call in calls if getattr(call, field) is not None]
        result[field] = sum(known) if len(known) == len(calls) else None
        result[field + "_known_subtotal"] = sum(known)
        result[field + "_coverage"] = len(known)
        result[field + "_status"] = ("available" if len(known) == len(calls)
                                       else "partial" if known else "not_available")
    known_vram = [c.peak_allocated_vram_bytes for c in calls if c.peak_allocated_vram_bytes is not None]
    result["peak_allocated_vram_bytes"] = max(known_vram) if known_vram else None
    result["vram_coverage"] = len(known_vram)
    result["token_budget_hits"] = sum(c.hit_max_new_tokens is True for c in calls)
    result["token_budget_observation_coverage"] = sum(c.hit_max_new_tokens is not None for c in calls)
    return result


def evaluate_pairs(plan: EvaluationPlan, pairs: tuple[PairedCaseResult, ...],
                   costs: tuple[InferenceCost, ...]) -> dict:
    """Validate frozen inventory + evidence; planned denominators gồm failed/not-run.

    Actual ledger do caller cung cấp từ artifacts đã xác minh, không suy ra measurement.
    Không mở dataset paths, gọi model hoặc suy diễn semantic scores.
    """
    plan = checked_copy(plan, EvaluationPlan)
    pairs = tuple(checked_copy(pair, PairedCaseResult) for pair in pairs)
    costs = tuple(checked_copy(cost, InferenceCost) for cost in costs)
    planned = {case.case_id: case for case in plan.cases}
    ids = [pair.case_id for pair in pairs]
    if len(ids) != len(set(ids)) or set(ids) != set(planned):
        raise ValueError("Missing/extra/duplicate paired cases; phải giữ not-run records.")
    ledger = {}
    call_ids = set()
    for call in costs:
        key = call.case_id, call.attempt_index
        if call.case_id not in planned or key in ledger or call.call_id in call_ids:
            raise ValueError("Unknown/duplicate physical inference call; replay không thuộc ledger.")
        ledger[key] = call
        call_ids.add(call.call_id)
    expected_calls = set()
    per_case = []
    for pair in pairs:
        if sha256_text(pair.original_summary) != planned[pair.case_id].original_summary_sha256:
            raise ValueError("Original summary provenance hash mismatch.")
        if pair.initial_raw is None:
            if pair.b0.state != "not_run" or pair.b1.state != "not_run":
                raise ValueError("Không có initial raw thì không replay B0/B1.")
            if pair.initial_failure_stage == "backend":
                key = pair.case_id, 0
                expected_calls.add(key)
                if key not in ledger or ledger[key].state != "failed" or ledger[key].raw_sha256 is not None:
                    raise ValueError("Initial infrastructure failure cần actual failed ledger entry.")
            per_case.append({"case_id": pair.case_id, "initial_acceptance": None,
                             "initial_json_schema_pass": None, "eligible_for_repair": False,
                             "initial_failure_category": pair.initial_failure_category,
                             "initial_failure_stage": pair.initial_failure_stage,
                             "initial_raw_sha256": None, "initial_errors": None,
                             "original_summary_sha256": planned[pair.case_id].original_summary_sha256,
                             "origin": planned[pair.case_id].origin})
            continue
        raw_hash = sha256_text(pair.initial_raw)
        key = pair.case_id, 0
        expected_calls.add(key)
        initial_call = ledger.get(key)
        if initial_call is None or initial_call.raw_sha256 != raw_hash or initial_call.state != "completed":
            raise ValueError("Frozen initial raw thiếu corresponding physical generation evidence.")
        reports = []
        for variant in (pair.b0, pair.b1):
            if variant.state != "not_run" and variant.initial_raw_sha256 != raw_hash:
                raise ValueError("B0/B1 initial raw SHA-256 mismatch.")
            _validate_history(pair, variant)
            history = _history(variant)
            if history and history[0].validation_report is not None:
                reports.append(json_bytes(history[0].validation_report))
        if len(reports) == 2 and reports[0] != reports[1]:
            raise ValueError("Paired initial validation reports khác nhau.")
        for attempt in _history(pair.b1)[1:]:
            key = pair.case_id, attempt.attempt_index
            expected_calls.add(key)
            call = ledger.get(key)
            if call is None:
                raise ValueError("Actual repair attempt thiếu physical ledger entry.")
            expected_hash = sha256_text(attempt.raw_output) if attempt.raw_output is not None else None
            if call.raw_sha256 != expected_hash:
                raise ValueError("Repair ledger raw mismatch.")
            expected_state = "failed" if attempt.failure_category in (
                "backend_exception", "backend_output_type", "invalid_output_unicode"
            ) else "completed"
            if call.state != expected_state:
                raise ValueError("Repair ledger state mismatch.")
            metadata = attempt.backend_metadata
            if metadata:
                if metadata.get("call_id") != call.call_id:
                    raise ValueError("Repair metadata call identity mismatch.")
                if metadata.get("purpose", "story_repair") not in ("story_repair", "repair"):
                    raise ValueError("Repair metadata purpose mismatch.")
                for meta_key, expected in (("revision", plan.model_revision), ("prompt_sha256", call.prompt_sha256)):
                    if meta_key in metadata and metadata[meta_key] != expected:
                        raise ValueError("Repair metadata provenance mismatch.")
                for meta_key, cost_key in (("input_tokens", "input_tokens"), ("generated_tokens", "generated_tokens"),
                                           ("generation_latency_seconds", "model_generation_seconds"),
                                           ("peak_allocated_vram_bytes", "peak_allocated_vram_bytes"),
                                           ("hit_max_new_tokens", "hit_max_new_tokens")):
                    measured = getattr(call, cost_key)
                    if meta_key in metadata and measured is not None and metadata[meta_key] != measured:
                        raise ValueError("Cost ledger contradicts captured metadata.")
        initial = StoryboardValidator().validate_raw(pair.initial_raw, expected_summary=pair.original_summary)
        per_case.append({"case_id": pair.case_id, "initial_acceptance": initial.production_success is True,
                         "initial_json_schema_pass": initial.json_syntax == initial.structural_validity == "passed",
                         "eligible_for_repair": initial.production_success is False,
                         "initial_failure_category": None, "initial_raw_sha256": raw_hash,
                         "initial_errors": [{"code": i.code, "location": list(i.location)}
                                            for i in initial.issues if i.severity == "error"],
                         "original_summary_sha256": planned[pair.case_id].original_summary_sha256,
                         "origin": planned[pair.case_id].origin})
    if set(ledger) != expected_calls:
        raise ValueError("Extra/missing physical calls; không double-count B0/B1 replay.")
    n = len(plan.cases)
    variants = {}
    for name in ("B0", "B1"):
        records = [getattr(pair, name.lower()) for pair in pairs]
        statuses = Counter(v.result.status if v.result is not None else v.state for v in records)
        completed = sum(v.state == "completed" for v in records)
        accepted = sum(v.result is not None and v.result.status in ACCEPTED for v in records)
        variants[name] = {"planned": n, "attempted": sum(v.state != "not_run" for v in records),
                          "completed": completed, "failed": sum(v.state == "failed" for v in records),
                          "not_run": sum(v.state == "not_run" for v in records), "statuses": dict(statuses),
                          "accepted": accepted, "acceptance_planned": ratio(accepted, n),
                          "acceptance_completed": ratio(accepted, completed), "coverage": ratio(completed, n),
                          "failure_categories": dict(Counter(v.failure_category for v in records if v.state == "failed"))}
        for status in ("accepted_initial", "accepted_after_repair", "budget_exhausted", "input_failure", "backend_failure"):
            variants[name][status] = statuses[status]
    repair_cases = [p for p in pairs if len(_history(p.b1)) > 1]
    successes = [p for p in repair_cases if p.b1.result and p.b1.result.status == "accepted_after_repair"]
    eligible = sum(row["eligible_for_repair"] for row in per_case)
    logical_b0 = [c for c in costs if c.purpose == "story_generation"]
    attempted = len({call.case_id for call in costs} | {p.case_id for p in pairs if p.initial_failure_category is not None})
    completed = sum(p.b0.state == p.b1.state == "completed" for p in pairs)
    failed = sum(p.initial_failure_category is not None or p.b0.state == "failed" or p.b1.state == "failed" for p in pairs)
    output = {
        "schema_version": "task11-offline-v1", "plan_sha256": sha256_bytes(json_bytes(plan)),
        "planned": n, "attempted": attempted, "completed_paired": completed,
        "failed_cases": failed, "not_run": n - attempted,
        "partial_cases": attempted - completed - failed, "paired_coverage": ratio(completed, n),
        "initial_infrastructure_failures": sum(p.initial_failure_stage == "backend" for p in pairs),
        "initial_input_failures": sum(p.initial_failure_stage == "input_validation" for p in pairs),
        "initial_accepted": sum(row["initial_acceptance"] is True for row in per_case),
        "initial_json_schema_pass": sum(row["initial_json_schema_pass"] is True for row in per_case),
        "eligible_initial_failures": eligible, "repair_cases_attempted": len(repair_cases),
        "eligible_not_attempted": eligible - len(repair_cases),
        "repair_backend_failure_cases": sum(p.b1.result is not None and p.b1.result.status == "backend_failure"
                                            for p in repair_cases),
        "first_repair_successes": sum(len(p.b1.result.attempts) == 2 for p in successes),
        "second_repair_successes": sum(len(p.b1.result.attempts) == 3 for p in successes),
        "conditional_repair_success": ratio(len(successes), len(repair_cases)),
        "mean_repair_backend_invocations_planned": ratio(sum(c.purpose == "story_repair" for c in costs), n),
        "acceptance_improvement_pp": 100 * (variants["B1"]["accepted"] - variants["B0"]["accepted"]) / n if n else None,
        "variants": variants, "per_case_initial": per_case,
        "per_case_final": [{"case_id": p.case_id, "variants": {
            name: {"state": v.state, "status": v.result.status if v.result else None,
                   "accepted_storyboard_sha256": sha256_bytes(json_bytes(v.result.storyboard))
                   if v.result and v.result.storyboard is not None else None,
                   "final_summary_matching": _history(v)[-1].validation_report.summary_matching
                   if _history(v) and _history(v)[-1].validation_report else "not_checked",
                   "final_errors": [{"code": i.code, "location": list(i.location)}
                                    for i in _history(v)[-1].validation_report.issues if i.severity == "error"]
                   if _history(v) and _history(v)[-1].validation_report else None}
            for name, v in (("B0", p.b0), ("B1", p.b1))}} for p in pairs],
        "costs": {"physical": _sum_costs(list(costs)), "B0_logical": _sum_costs(logical_b0),
                  "B1_logical": _sum_costs(list(costs))},
        "semantic_evaluation": "not_checked",
    }
    json_bytes(output)
    return output
