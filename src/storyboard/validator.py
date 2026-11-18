"""Deterministic consistency reporting; không sửa dữ liệu hoặc đánh giá semantic."""

from __future__ import annotations

import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, JsonValue, ValidationError, computed_field
from pydantic_core import from_json

from .schema import Storyboard

__all__ = ["ValidationIssue", "ValidationReport", "StoryboardValidator"]

CheckStatus = Literal["passed", "failed", "not_checked"]
IssueCode = Literal[
    "INVALID_JSON",
    "SCHEMA_VIOLATION",
    "SUMMARY_MISMATCH",
    "UNUSED_CHARACTER",
    "DUPLICATE_VISUAL_DESCRIPTION",
    "DUPLICATE_SCENE_CAPTION",
]


class ValidationIssue(BaseModel):
    """Location dùng list position từ 0; evidence chỉ chứa dữ liệu JSON."""

    model_config = ConfigDict(strict=True, extra="forbid")

    code: IssueCode
    severity: Literal["error", "warning"]
    location: tuple[str | int, ...]
    message: str
    evidence: dict[str, JsonValue]


class ValidationReport(BaseModel):
    """Report không chứa nested Storyboard để tránh validate lại khi tạo report."""

    model_config = ConfigDict(strict=True, extra="forbid")

    json_syntax: CheckStatus = "not_checked"
    structural_validity: CheckStatus = "not_checked"
    summary_matching: CheckStatus = "not_checked"
    semantic_validity: Literal["not_checked"] = "not_checked"
    visual_language_validity: Literal["not_checked"] = "not_checked"
    raw_output: str | None = None
    issues: list[ValidationIssue]
    pydantic_errors: list[dict[str, JsonValue]]

    @computed_field
    @property
    def production_success(self) -> bool | None:
        """Tương thích output gate StoryGenerator, không khẳng định đã gọi backend."""
        if "failed" in (self.json_syntax, self.structural_validity, self.summary_matching):
            return False
        if self.structural_validity == "passed" and self.summary_matching == "passed":
            return True
        return None


def _check_expected_summary(expected_summary: str | None) -> None:
    if expected_summary is not None:
        if not isinstance(expected_summary, str):
            raise TypeError("expected_summary phải là str hoặc None.")
        if not expected_summary.strip():
            raise ValueError("expected_summary không được rỗng hoặc chỉ chứa whitespace.")


def _schema_failure(
    error: ValidationError, *, raw_output: str | None, json_syntax: CheckStatus
) -> ValidationReport:
    # JSON form giữ loc/type/msg/input/url và ctx; exception trong ctx thành string.
    # Đây là serialize lỗi, không parse/validate raw output thêm lần nữa.
    # Input như 1e999 có thể overflow thành inf; evidence dùng tên constant thay
    # vì chứa float không hợp lệ trong JSON. Raw input vẫn giữ nguyên trong report.
    details = json.loads(error.json(), parse_constant=str)
    return ValidationReport(
        raw_output=raw_output,
        json_syntax=json_syntax,
        structural_validity="failed",
        pydantic_errors=details,
        issues=[
            ValidationIssue(
                code="SCHEMA_VIOLATION",
                severity="error",
                location=tuple(detail["loc"]),
                message=detail["msg"],
                evidence={"pydantic_error": detail},
            )
            for detail in details
        ],
    )


def _consistency_issues(storyboard: Storyboard) -> list[ValidationIssue]:
    used = {reference for scene in storyboard.scenes for reference in scene.characters}
    issues = []
    visuals: dict[str, list[int]] = {}
    for position, character in enumerate(storyboard.characters):
        if character.id not in used:
            issues.append(
                ValidationIssue(
                    code="UNUSED_CHARACTER",
                    severity="warning",
                    location=("characters", position, "id"),
                    message="Character ID không được tham chiếu trong bất kỳ scene nào.",
                    evidence={"character_id": character.id},
                )
            )
        visuals.setdefault(character.visual, []).append(position)

    for visual, positions in visuals.items():
        if len(positions) > 1:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_VISUAL_DESCRIPTION",
                    severity="warning",
                    location=("characters", positions[0], "visual"),
                    message="Visual descriptions giống hệt nhau; chưa kết luận cùng identity.",
                    evidence={
                        "visual": visual,
                        "character_ids": [storyboard.characters[pos].id for pos in positions],
                        "character_positions": positions,
                    },
                )
            )

    captions: dict[str, list[int]] = {}
    for position, scene in enumerate(storyboard.scenes):
        captions.setdefault(scene.caption_vi, []).append(position)
    for caption, positions in captions.items():
        if len(positions) > 1:
            issues.append(
                ValidationIssue(
                    code="DUPLICATE_SCENE_CAPTION",
                    severity="warning",
                    location=("scenes", positions[0], "caption_vi"),
                    message="Nhiều scenes có caption giống hệt nhau; chưa kết luận trùng ngữ nghĩa.",
                    evidence={
                        "caption_vi": caption,
                        "scene_indices": [storyboard.scenes[pos].index for pos in positions],
                        "scene_positions": positions,
                    },
                )
            )
    return issues


def _valid_report(
    storyboard: Storyboard,
    *,
    expected_summary: str | None,
    raw_output: str | None,
    json_syntax: CheckStatus,
) -> ValidationReport:
    issues = []
    matching: CheckStatus = "not_checked"
    if expected_summary is not None:
        matching = "passed" if storyboard.summary == expected_summary else "failed"
        if matching == "failed":
            issues.append(
                ValidationIssue(
                    code="SUMMARY_MISMATCH",
                    severity="error",
                    location=("summary",),
                    message="Summary không khớp chính xác input gốc; không tự ghi đè.",
                    evidence={"expected": expected_summary, "actual": storyboard.summary},
                )
            )
    issues.extend(_consistency_issues(storyboard))
    return ValidationReport(
        raw_output=raw_output,
        json_syntax=json_syntax,
        structural_validity="passed",
        summary_matching=matching,
        issues=issues,
        pydantic_errors=[],
    )


class StoryboardValidator:
    """Stateless; errors dừng checks phụ thuộc schema, warnings không chặn output gate."""

    def validate_raw(
        self, raw_output: str, *, expected_summary: str | None = None
    ) -> ValidationReport:
        """Parse JSON một lần, dùng shared schema một lần; giữ nguyên raw text."""
        _check_expected_summary(expected_summary)
        if not isinstance(raw_output, str):
            raise TypeError("raw_output phải là str; không tự ép kiểu output backend.")
        try:
            # Cùng JSON engine với shared Pydantic model; không cho non-JSON constants.
            data = from_json(raw_output, allow_inf_nan=False)
        except ValueError as error:
            evidence: dict[str, JsonValue] = {
                "decoder": "pydantic_core.from_json", "error": str(error)
            }
            return ValidationReport(
                raw_output=raw_output,
                json_syntax="failed",
                issues=[
                    ValidationIssue(
                        code="INVALID_JSON",
                        severity="error",
                        location=(),
                        message="Raw output không phải JSON hợp lệ; không strip fences hoặc sửa dữ liệu.",
                        evidence=evidence,
                    )
                ],
                pydantic_errors=[],
            )
        try:
            storyboard = Storyboard.model_validate(data)
        except ValidationError as error:
            return _schema_failure(error, raw_output=raw_output, json_syntax="passed")
        return _valid_report(
            storyboard, expected_summary=expected_summary, raw_output=raw_output, json_syntax="passed"
        )

    def validate(
        self, storyboard: Storyboard, *, expected_summary: str | None = None
    ) -> ValidationReport:
        """Revalidate instance mutable một lần; không có raw thì JSON syntax là not_checked."""
        _check_expected_summary(expected_summary)
        if not isinstance(storyboard, Storyboard):
            raise TypeError("validate nhận shared Storyboard; raw text dùng validate_raw.")
        try:
            checked = Storyboard.model_validate(storyboard)
        except ValidationError as error:
            return _schema_failure(error, raw_output=None, json_syntax="not_checked")
        return _valid_report(
            checked, expected_summary=expected_summary, raw_output=None, json_syntax="not_checked"
        )
