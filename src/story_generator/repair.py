"""Bounded deterministic repair orchestration; không inference implementation hoặc semantic gate."""

from copy import deepcopy
import json
from time import perf_counter
from typing import Any, Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field, JsonValue

from src.storyboard.schema import Storyboard
from src.storyboard.validator import StoryboardValidator, ValidationIssue, ValidationReport
from .backend import StoryBackend


REPAIRABLE_CODES = frozenset({"INVALID_JSON", "SCHEMA_VIOLATION", "SUMMARY_MISMATCH"})
RepairStatus = Literal[
    "accepted_initial", "accepted_after_repair", "budget_exhausted", "input_failure", "backend_failure",
]


class _Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)


class RepairFeedback(_Record):
    """Request cho next attempt; errors chỉ gồm deterministic hard errors của previous raw."""

    original_summary: str
    previous_raw_output: str
    attempt_index: int
    errors: list[ValidationIssue]


class RepairBackend(Protocol):
    def generate_repair(self, feedback: RepairFeedback) -> str: ...


class RepairAttempt(_Record):
    attempt_index: int
    generation_kind: Literal["initial", "repair"]
    raw_output: str | None = None
    raw_output_preservation: Literal["not_available", "verbatim", "escaped_diagnostic"] = "not_available"
    validation_report: ValidationReport | None = None
    feedback: RepairFeedback | None = None
    backend_metadata: dict[str, JsonValue] | None = None
    metadata_status: Literal["not_available", "captured", "discarded"] = "not_available"
    failure_category: str | None = None
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    elapsed_seconds: float  # Controller wall time quanh backend method, không phải model.generate.


class RepairResult(_Record):
    status: RepairStatus
    original_summary: str | None
    max_retries: int
    attempts: tuple[RepairAttempt, ...]
    storyboard: Storyboard | None = None
    failure_category: str | None = None
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    elapsed_seconds: float  # Toàn bộ controller invocation, không phải inference benchmark.


class RepairControllerError(RuntimeError):
    """Unexpected validator/materialization failure; giữ history và exception chaining."""

    def __init__(self, attempts: list[RepairAttempt]):
        super().__init__("Deterministic validation/materialization thất bại; không tiếp tục repair.")
        self.attempts = tuple(attempt.model_copy(deep=True) for attempt in attempts)
        self.failure_category = "validation_failure"


def _utf8(value: str) -> bool:
    try:
        value.encode("utf-8")
        return True
    except UnicodeEncodeError:
        return False


def _unicode_diagnostic(value: str, location: str) -> dict[str, JsonValue]:
    return {
        "category": "unicode_transport", "location": location,
        "representation": "python_unicode_escape", "escaped_text": value.encode("unicode_escape").decode("ascii"),
        "original_utf8_preserved": False,
    }


def _exception_types(error: Exception) -> list[str]:
    names, seen = [], set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        names.append(type(error).__name__)
        error = error.__cause__
    return names


def _previous_id(backend: Any, attribute: str) -> tuple[str | None, bool]:
    try:
        previous = getattr(backend, attribute, None)
        return (previous.get("call_id") if isinstance(previous, dict) else None), True
    except Exception:
        return None, False


def _metadata_snapshot(
    backend: Any, attribute: str, previous_id: str | None, readable_before: bool, raw: Any,
) -> tuple[dict | None, str, str | None]:
    """Optional public snapshots; chỉ giữ allowlist JSON-safe, không messages/env/credentials."""
    try:
        value = getattr(backend, attribute, None)
        if value is None:
            return None, "not_available", None
        if (not readable_before or not isinstance(value, dict) or not isinstance(value.get("call_id"), str)
                or not value["call_id"] or value["call_id"] == previous_id):
            return None, "discarded", None
        current_raw = value.get("raw_output")
        if isinstance(raw, str) and current_raw != raw:
            return None, "discarded", None
        keys = {
            "call_id", "purpose", "model_id", "revision", "prompt_version", "prompt_sha256", "device", "precision",
            "batch_size", "input_tokens", "generated_tokens", "generation_latency_seconds", "peak_allocated_vram_bytes",
            "hit_max_new_tokens", "error_category", "execution_mode", "gpu_model",
        }
        snapshot = {key: deepcopy(value[key]) for key in keys if key in value}
        nested_keys = {
            "generation_parameters": {"do_sample", "max_new_tokens", "num_beams", "num_return_sequences", "repetition_penalty",
                                      "return_dict_in_generate", "output_scores", "pad_token_id"},
            "package_versions": {"python", "torch", "transformers", "pydantic", "huggingface-hub", "safetensors"},
        }
        for key, allowed in nested_keys.items():
            if isinstance(value.get(key), dict):
                snapshot[key] = {k: deepcopy(v) for k, v in value[key].items() if k in allowed}
        json.dumps(snapshot, ensure_ascii=False, allow_nan=False).encode("utf-8")
        return snapshot, "captured", current_raw if isinstance(current_raw, str) else None
    except Exception:
        return None, "discarded", None


def _feedback(summary: str, previous: RepairAttempt, index: int) -> RepairFeedback:
    errors = []
    for issue in previous.validation_report.issues:
        if issue.severity != "error" or issue.code not in REPAIRABLE_CODES:
            continue
        # Raw chứa dữ liệu gốc; không lặp toàn input/ctx/exception trong schema feedback.
        evidence = deepcopy(issue.evidence)
        if issue.code == "SCHEMA_VIOLATION":
            evidence = {"validation_type": issue.evidence["pydantic_error"]["type"]}
        errors.append(ValidationIssue(code=issue.code, severity="error", location=issue.location,
                                      message=issue.message, evidence=evidence))
    return RepairFeedback(original_summary=summary, previous_raw_output=previous.raw_output,
                          attempt_index=index, errors=errors)


class BoundedRepairController:
    """Một initial call + budget repair calls; không sở hữu/load model, không semantic reviewer."""

    def __init__(self, initial_backend: StoryBackend, repair_backend: RepairBackend | None = None, *, max_retries: int = 2):
        if type(max_retries) is not int or max_retries < 0:
            raise ValueError("max_retries phải là integer không âm, không nhận bool.")
        if not callable(getattr(initial_backend, "generate", None)):
            raise TypeError("initial_backend phải cung cấp generate(summary) -> str.")
        if max_retries > 0 and not callable(getattr(repair_backend, "generate_repair", None)):
            raise TypeError("Repair budget dương cần repair_backend.generate_repair(feedback) -> str.")
        self._initial = initial_backend
        self._repair = repair_backend
        self._max_retries = max_retries

    def generate(self, original_summary: str) -> RepairResult:
        started = perf_counter()
        attempts: list[RepairAttempt] = []
        safe_summary = original_summary if isinstance(original_summary, str) and _utf8(original_summary) else None

        def finish(status: RepairStatus, *, board=None, failure=None, diagnostics=None):
            return RepairResult(status=status, original_summary=safe_summary, max_retries=self._max_retries,
                                attempts=tuple(attempts), storyboard=board, failure_category=failure,
                                diagnostics=diagnostics or [], elapsed_seconds=perf_counter() - started)

        if not isinstance(original_summary, str) or not original_summary.strip():
            return finish("input_failure", failure="invalid_summary")
        if safe_summary is None:
            return finish("input_failure", failure="invalid_summary_unicode",
                          diagnostics=[_unicode_diagnostic(original_summary, "original_summary")])

        validator = StoryboardValidator()
        for index in range(1 + self._max_retries):
            kind = "initial" if index == 0 else "repair"
            feedback = None if index == 0 else _feedback(original_summary, attempts[-1], index)
            backend, attribute = (self._initial, "last_run") if index == 0 else (self._repair, "last_repair")
            previous_id, readable_before = _previous_id(backend, attribute)
            raw, backend_error = None, None
            call_started = perf_counter()
            try:
                raw = backend.generate(original_summary) if index == 0 else backend.generate_repair(feedback.model_copy(deep=True))
            except Exception as error:
                backend_error = error
            elapsed = perf_counter() - call_started
            metadata, metadata_status, metadata_raw = _metadata_snapshot(backend, attribute, previous_id, readable_before, raw)
            if backend_error is not None and raw is None:
                raw = metadata_raw  # Chỉ current fresh snapshot; không lấy raw từ stale metadata.
            diagnostics = []
            preservation = "not_available"
            if isinstance(raw, str):
                preservation = "verbatim" if _utf8(raw) else "escaped_diagnostic"
                if preservation == "escaped_diagnostic":
                    diagnostics.append(_unicode_diagnostic(raw, "raw_output"))
            if metadata_status == "discarded":
                diagnostics.append({"category": "metadata_discarded", "reason": "unavailable_identity_or_unsafe_snapshot"})
            fields = dict(attempt_index=index, generation_kind=kind,
                          raw_output=raw if preservation == "verbatim" else None, raw_output_preservation=preservation,
                          feedback=feedback, backend_metadata=metadata, metadata_status=metadata_status,
                          diagnostics=diagnostics, elapsed_seconds=elapsed)
            if backend_error is not None:
                diagnostics.append({"category": "backend_exception", "exception_types": _exception_types(backend_error)})
                attempts.append(RepairAttempt(**fields, failure_category="backend_exception"))
                return finish("backend_failure", failure="backend_exception")
            if not isinstance(raw, str) or preservation != "verbatim":
                category = "backend_output_type" if not isinstance(raw, str) else "invalid_output_unicode"
                attempts.append(RepairAttempt(**fields, failure_category=category))
                return finish("backend_failure", failure=category)
            safe_report = None
            try:
                report = validator.validate_raw(raw, expected_summary=original_summary)
                # Kiểm tra report transport; không sanitize/repair validator output để che lỗi.
                json.dumps(report.model_dump(mode="json"), ensure_ascii=False, allow_nan=False).encode("utf-8")
                safe_report = report.model_copy(deep=True)
                accepted = report.production_success is True and all(
                    getattr(report, field) == "passed" for field in ["json_syntax", "structural_validity", "summary_matching"]
                )
                # Report hiện không trả Storyboard. Chỉ materialize lại accepted raw qua shared model.
                board = Storyboard.model_validate_json(raw) if accepted else None
            except Exception as error:
                attempts.append(RepairAttempt(**fields, validation_report=safe_report, failure_category="validation_failure"))
                raise RepairControllerError(attempts) from error
            attempts.append(RepairAttempt(**fields, validation_report=report.model_copy(deep=True),
                                          failure_category=None if accepted else "deterministic_validation_failure"))
            if accepted:
                return finish("accepted_initial" if index == 0 else "accepted_after_repair", board=board)
            hard_errors = [issue for issue in report.issues if issue.severity == "error"]
            if not hard_errors or any(issue.code not in REPAIRABLE_CODES for issue in hard_errors):
                # Không chạy thêm generation nếu output gate và error contract mâu thuẫn.
                raise RepairControllerError(attempts)
        return finish("budget_exhausted", failure="repair_budget_exhausted")
