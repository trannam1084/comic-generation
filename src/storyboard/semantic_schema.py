"""Contract semantic review riêng; không thay Shared Storyboard Schema."""

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, computed_field, field_validator, model_validator

SemanticCode = Literal[
    "CHARACTER_IDENTITY_MISMATCH", "CHARACTER_ROLE_MISMATCH", "CHARACTER_FRAGMENTATION",
    "OBJECT_TRANSLATION_MISMATCH", "VISUAL_LANGUAGE_MISMATCH", "MISSING_KEY_EVENT",
    "ENDING_CONTRADICTION", "UNSUPPORTED_STORY_EVENT",
]
Verdict = Literal["pass", "fail", "uncertain"]
Location = list[str | int]


class _ReviewModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


def _nonblank(value: str) -> str:
    if not value.strip():
        raise ValueError("Text phải có nội dung; không tự trim.")
    value.encode("utf-8")
    return value


def _valid_location(path: Location) -> Location:
    for part in path:
        if isinstance(part, int) and part < 0:
            raise ValueError("Location không nhận index âm.")
        if isinstance(part, str):
            _nonblank(part)
    return path


class SemanticEvidence(_ReviewModel):
    """Exact quote from a source string; locations use zero-based list positions."""

    source: Literal["original_summary", "storyboard"]
    location: Location
    quote: str

    _quote_nonblank = field_validator("quote")(_nonblank)

    _path_components = field_validator("location")(_valid_location)

    @model_validator(mode="after")
    def summary_path_is_root(self) -> Self:
        if self.source == "original_summary" and self.location:
            raise ValueError("Original summary là một string; evidence location phải là [].")
        return self


class SemanticIssue(_ReviewModel):
    code: SemanticCode
    severity: Literal["error", "warning"]
    location: Location
    message: str
    evidence: list[SemanticEvidence] = Field(min_length=1)

    _message_nonblank = field_validator("message")(_nonblank)
    _path_components = field_validator("location")(_valid_location)


class SemanticReviewResponse(_ReviewModel):
    """Model-generated review claims, not semantic ground truth."""

    verdict: Verdict
    explanation: str
    issues: list[SemanticIssue]

    _explanation_nonblank = field_validator("explanation")(_nonblank)

    @model_validator(mode="after")
    def verdict_agrees_with_issues(self) -> Self:
        errors = any(issue.severity == "error" for issue in self.issues)
        if self.verdict == "pass" and self.issues:
            raise ValueError("PASS không đi cùng issues; có nghi vấn phải abstain/uncertain.")
        if self.verdict == "fail" and not errors:
            raise ValueError("FAIL cần ít nhất một error issue có evidence.")
        if self.verdict == "uncertain" and errors:
            raise ValueError("UNCERTAIN chỉ chứa warnings hoặc không có issues.")
        return self


class SemanticValidationReport(_ReviewModel):
    """Runtime report: lỗi reviewer không biến thành semantic FAIL hoặc PASS."""

    review_status: Literal["completed", "failed", "not_checked"]
    response: SemanticReviewResponse | None = None
    raw_reviewer_output: str | None = None
    raw_reviewer_output_preservation: Literal["not_available", "verbatim", "escaped_diagnostic"] = "not_available"
    diagnostics: list[dict[str, JsonValue]] = Field(default_factory=list)
    error_category: Literal[
        "invalid_arguments", "invalid_source_storyboard", "reviewer_backend_failure",
        "reviewer_output_type", "invalid_reviewer_json", "invalid_reviewer_unicode", "reviewer_schema_violation",
        "invalid_issue_location", "invalid_issue_evidence", "reviewer_metadata_error",
    ] | None = None
    errors: list[dict[str, JsonValue]] = Field(default_factory=list)
    source_structural_validity: Literal["passed", "failed", "not_checked"] = "not_checked"
    summary_matching: Literal["passed", "failed", "not_checked"] = "not_checked"
    original_summary: str | None = None
    storyboard_snapshot: dict[str, JsonValue] | None = None
    provenance: dict[str, JsonValue] = Field(default_factory=dict)
    review_metadata: dict[str, JsonValue] | None = None
    human_annotation_status: Literal["not_checked"] = "not_checked"

    @computed_field
    @property
    def verdict(self) -> Verdict | None:
        return self.response.verdict if self.response is not None else None

    @computed_field
    @property
    def issues(self) -> list[SemanticIssue]:
        return self.response.issues if self.response is not None else []

    @model_validator(mode="after")
    def separate_execution_and_verdict(self) -> Self:
        if self.review_status == "completed":
            if self.response is None or self.error_category is not None:
                raise ValueError("Completed cần response hợp lệ và không có runtime error.")
        elif self.response is not None:
            raise ValueError("Failed/not_checked không có model verdict hợp lệ.")
        if self.review_status == "failed" and self.error_category is None:
            raise ValueError("Failed cần error_category.")
        return self
