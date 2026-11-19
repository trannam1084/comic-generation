"""Một LLM review call, kiểm tra contract/grounding, không Repair hoặc semantic ground truth."""

from copy import deepcopy
import hashlib
import json
import math
from typing import Any, Protocol
from uuid import uuid4

from pydantic import ValidationError, __version__ as pydantic_version

from .schema import Storyboard
from .semantic_prompts import SEMANTIC_PROMPT_VERSION, build_semantic_messages
from .semantic_schema import SemanticReviewResponse, SemanticValidationReport


class SemanticReviewBackend(Protocol):
    def review(self, messages: list[dict[str, str]], *, prompt_version: str) -> str: ...

    @property
    def last_review(self) -> dict[str, Any] | None: ...


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON object key trong reviewer response.")
        result[key] = value
    return result


def _finite_constant(value: str) -> None:
    raise ValueError("Reviewer JSON không chấp nhận NaN/Infinity.")


def _resolve(root: Any, path: list[str | int]) -> Any:
    current = root
    for part in path:
        if type(current) is dict and type(part) is str and part in current:
            current = current[part]
        elif type(current) is list and type(part) is int and 0 <= part < len(current):
            current = current[part]
        else:
            raise ValueError("Location không tồn tại trong storyboard snapshot.")
    return current


def _contract_errors(response: SemanticReviewResponse, summary: str, snapshot: dict) -> tuple[str | None, list]:
    for position, issue in enumerate(response.issues):
        try:
            _resolve(snapshot, issue.location)
        except ValueError:
            return "invalid_issue_location", [{"issue_position": position, "location": issue.location}]
        for evidence_position, evidence in enumerate(issue.evidence):
            try:
                source = summary if evidence.source == "original_summary" else _resolve(snapshot, evidence.location)
            except ValueError:
                source = None
            if not isinstance(source, str) or evidence.quote not in source:
                return "invalid_issue_evidence", [{
                    "issue_position": position, "evidence_position": evidence_position,
                    "source": evidence.source, "location": evidence.location,
                    "reason": "Evidence phải quote exact substring của text field tồn tại.",
                }]
    return None, []


def _error_types(error: Exception) -> list[str]:
    names = []
    seen = set()
    while error is not None and id(error) not in seen:
        seen.add(id(error))
        names.append(type(error).__name__)
        error = error.__cause__
    return names


def _is_utf8(value: str) -> bool:
    try:
        value.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


def _escaped_text(value: str) -> dict[str, Any]:
    """Biểu diễn diagnostic của Python code points, không phải raw UTF-8 đã sửa."""
    return {
        "representation": "python_unicode_escape",
        "escaped_text": value.encode("unicode_escape").decode("ascii"),
        "original_utf8_preserved": False,
    }


def _unsafe_strings(value: Any, path: tuple = ()):
    """Duyệt cả dict keys và values; không normalize hay sửa snapshot."""
    if isinstance(value, str):
        if not _is_utf8(value):
            yield path, value
    elif isinstance(value, dict):
        for position, (key, item) in enumerate(value.items()):
            if isinstance(key, str) and not _is_utf8(key):
                yield (*path, "<key>", position), key
            yield from _unsafe_strings(item, (*path, key))
    elif isinstance(value, (list, tuple)):
        for position, item in enumerate(value):
            yield from _unsafe_strings(item, (*path, position))


def _safe_error_value(value: Any) -> Any:
    """Chỉ dùng cho diagnostic/error details; không dùng cho prompt/evidence matching."""
    if isinstance(value, str):
        return value if _is_utf8(value) else _escaped_text(value)
    if isinstance(value, (list, tuple)):
        return [_safe_error_value(item) for item in value]
    if isinstance(value, dict):
        if any(not isinstance(key, str) or not _is_utf8(key) for key in value):
            return {"representation": "mapping_entries", "entries": [
                {"key": _safe_error_value(key), "value": _safe_error_value(item)}
                for key, item in value.items()
            ]}
        return {key: _safe_error_value(item) for key, item in value.items()}
    if isinstance(value, float) and not math.isfinite(value):
        return "NaN" if math.isnan(value) else ("Infinity" if value > 0 else "-Infinity")
    return value


def _unicode_diagnostics(value: Any, path: tuple) -> list[dict]:
    return [
        {"category": "unicode_transport", "location": _safe_error_value(list(location)), **_escaped_text(text)}
        for location, text in _unsafe_strings(value, path)
    ]


def _validation_errors(error: ValidationError, diagnostics: list[dict]) -> list[dict]:
    try:
        details = json.loads(error.json(), parse_constant=str)
        if any(_unsafe_strings(details)):
            raise ValueError("Error JSON có string không transport được bằng UTF-8.")
        return details
    except Exception as serialization_error:
        diagnostic = {
            "category": "pydantic_error_serialization_fallback",
            "exception_types": _error_types(serialization_error),
            "fallback": "errors_without_input_or_context",
            "omitted_fields": ["input", "ctx"],
        }
        diagnostics.append(diagnostic)
        try:
            # Native loc/type/msg/url vẫn giữ khi có thể; không stringify exception/input tùy ý.
            details = error.errors(include_input=False, include_context=False)
            return _safe_error_value(details)
        except Exception as fallback_error:
            diagnostic["fallback_exception_types"] = _error_types(fallback_error)
            return [{"type": "validation_error", "loc": [], "msg": "Structured details unavailable; see diagnostics."}]


class SemanticStoryboardValidator:
    """Offline semantic analysis, kể cả summary mismatch; chưa là production acceptance policy."""

    def __init__(self, backend: SemanticReviewBackend):
        self._backend = backend

    def validate(self, original_summary: str, storyboard: Storyboard) -> SemanticValidationReport:
        state = {
            "review_status": "not_checked",
            "diagnostics": [],
            "provenance": {
                "review_attempt_id": uuid4().hex, "prompt_version": SEMANTIC_PROMPT_VERSION,
                "purpose": "semantic_review", "mode": "offline_analysis",
                "reviewer_is_ground_truth": False, "pydantic_version": pydantic_version,
            },
        }
        if not isinstance(original_summary, str) or not original_summary.strip() or not isinstance(storyboard, Storyboard):
            return SemanticValidationReport(**state, error_category="invalid_arguments")
        source_diagnostics = _unicode_diagnostics(original_summary, ("original_summary",))
        if source_diagnostics:
            state["diagnostics"].extend(source_diagnostics)
            return SemanticValidationReport(**state, error_category="invalid_arguments",
                                            errors=[{"type": "unicode_transport", "loc": ["original_summary"]}])
        state["original_summary"] = original_summary
        try:
            checked = Storyboard.model_validate(storyboard)
        except ValidationError as error:
            return SemanticValidationReport(
                **state, source_structural_validity="failed", error_category="invalid_source_storyboard",
                errors=_validation_errors(error, state["diagnostics"]),
            )
        snapshot = checked.model_dump()
        source_diagnostics = _unicode_diagnostics(snapshot, ("storyboard",))
        if source_diagnostics:
            state["diagnostics"].extend(source_diagnostics)
            return SemanticValidationReport(
                **state, source_structural_validity="passed", error_category="invalid_source_storyboard",
                errors=[{"type": "unicode_transport", "loc": item["location"]} for item in source_diagnostics],
            )
        state.update(
            source_structural_validity="passed",
            summary_matching="passed" if checked.summary == original_summary else "failed",
            storyboard_snapshot=deepcopy(snapshot),
        )
        messages = build_semantic_messages(original_summary, checked)
        prompt_hash = hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()
        state["provenance"].update(
            prompt_sha256=prompt_hash,
            original_summary_sha256=hashlib.sha256(original_summary.encode("utf-8")).hexdigest(),
            storyboard_sha256=hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest(),
        )
        state["review_status"] = "failed"
        # Trước call chỉ đọc call_id để chống dùng snapshot cũ; không gắn metadata cũ vào report.
        try:
            previous = self._backend.last_review
            previous_id = previous.get("call_id") if previous is not None else None
        except Exception as error:
            return SemanticValidationReport(**state, error_category="reviewer_metadata_error",
                                            errors=[{"exception_types": _error_types(error)}])
        raw = None
        backend_error = None
        try:
            # Copy data boundary để backend không mutate prompt/snapshot của caller.
            raw = self._backend.review(deepcopy(messages), prompt_version=SEMANTIC_PROMPT_VERSION)
        except Exception as error:
            backend_error = _error_types(error)
        metadata = None
        metadata_error = None
        current_metadata_raw = None
        try:
            candidate = self._backend.last_review
            if candidate is not None:
                if (not isinstance(candidate, dict) or not isinstance(candidate.get("call_id"), str)
                        or not candidate["call_id"] or candidate["call_id"] == previous_id
                        or candidate.get("purpose") != "semantic_review"
                        or candidate.get("prompt_version") != SEMANTIC_PROMPT_VERSION
                        or candidate.get("prompt_sha256") != prompt_hash or candidate.get("messages") != messages):
                    raise ValueError("Reviewer metadata không chứng minh là của invocation hiện tại.")
                if isinstance(raw, str) and candidate.get("raw_output") != raw:
                    raise ValueError("Metadata raw_output không khớp return value.")
                current_metadata_raw = candidate.get("raw_output")
                metadata_diagnostics = _unicode_diagnostics(candidate, ("review_metadata",))
                if metadata_diagnostics:
                    state["diagnostics"].extend(metadata_diagnostics)
                    raise ValueError("Reviewer metadata chứa string không encode UTF-8 được.")
                json.dumps(candidate, allow_nan=False)
                metadata = deepcopy(candidate)
        except Exception as error:
            metadata_error = {"category": "reviewer_metadata_error", "exception_types": _error_types(error)}
        if backend_error is not None and raw is None and isinstance(current_metadata_raw, str):
            raw = current_metadata_raw
        raw_diagnostics = _unicode_diagnostics(raw, ("raw_reviewer_output",)) if isinstance(raw, str) else []
        state["diagnostics"].extend(raw_diagnostics)
        state.update(
            raw_reviewer_output=raw if isinstance(raw, str) and not raw_diagnostics else None,
            raw_reviewer_output_preservation=("escaped_diagnostic" if raw_diagnostics else
                                              "verbatim" if isinstance(raw, str) else "not_available"),
            review_metadata=metadata,
        )
        if backend_error is not None:
            errors = [{"exception_types": backend_error}]
            if metadata_error:
                errors.append(metadata_error)
            return SemanticValidationReport(**state, error_category="reviewer_backend_failure", errors=errors)
        if raw_diagnostics:
            return SemanticValidationReport(**state, error_category="invalid_reviewer_unicode",
                                            errors=[{"type": "unicode_transport", "loc": ["raw_reviewer_output"]}])
        if not isinstance(raw, str):
            errors = [{"output_type": type(raw).__name__}]
            if metadata_error:
                errors.append(metadata_error)
            return SemanticValidationReport(**state, error_category="reviewer_output_type",
                                            errors=errors)
        if metadata_error:
            return SemanticValidationReport(**state, error_category="reviewer_metadata_error", errors=[metadata_error])
        try:
            data = json.loads(raw, object_pairs_hook=_unique_object, parse_constant=_finite_constant)
        except (ValueError, RecursionError) as error:
            return SemanticValidationReport(**state, error_category="invalid_reviewer_json",
                                            errors=[{"exception_types": _error_types(error)}])
        try:
            response = SemanticReviewResponse.model_validate(data)
        except ValidationError as error:
            return SemanticValidationReport(**state, error_category="reviewer_schema_violation",
                                            errors=_validation_errors(error, state["diagnostics"]))
        category, errors = _contract_errors(response, original_summary, snapshot)
        if category:
            return SemanticValidationReport(**state, error_category=category, errors=errors)
        state["review_status"] = "completed"
        return SemanticValidationReport(**state, response=response)
