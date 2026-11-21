"""Contracts offline riêng của TV1; không thay schemas production hoặc rubric TV3."""

from typing import Annotated, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from src.story_generator.repair import RepairAttempt, RepairResult
from src.storyboard.schema import Storyboard
from src.storyboard.semantic_schema import SemanticIssue, SemanticValidationReport, Verdict

Sha256 = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{64}$")]
Commit = Annotated[str, StringConstraints(pattern=r"^[0-9a-f]{40}$")]
Text = Annotated[str, StringConstraints(pattern=r"\S")]
Variant = Literal["B0", "B1"]
Location = tuple[str | int, ...]


class Record(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True,
                              revalidate_instances="always", allow_inf_nan=False)


class ArtifactReference(Record):
    """Logical artifact ID + byte hash; không tự đọc filesystem path từ record."""

    artifact_id: Text
    sha256: Sha256


class PlannedCase(Record):
    case_id: Text
    original_summary_sha256: Sha256
    origin: Literal["synthetic_cpu_fixture", "development", "official_dev", "official_test"]


class PlannedRun(Record):
    case_id: Text
    variant: Variant


class DatasetGates(Record):
    split_frozen: bool = False
    review_approved: bool = False
    rights_approved: bool = False
    official_test_authorized: bool = False
    dataset_reference: ArtifactReference | None = None


class EvaluationPlan(Record):
    """Frozen contract mới; supplied draft templates chưa phải frozen plan hợp lệ."""

    schema_version: Literal["task11-offline-v1"] = "task11-offline-v1"
    status: Literal["frozen"]
    source_commit: Commit
    model_revision: Commit
    story_prompt_sha256: Sha256
    repair_prompt_sha256: Sha256
    policy_sha256: Sha256
    cases: tuple[PlannedCase, ...]
    planned_runs: tuple[PlannedRun, ...]
    gates: DatasetGates = Field(default_factory=DatasetGates)
    human_rubric_version: Text | None = None

    @model_validator(mode="after")
    def inventory_and_gates(self) -> Self:
        ids = [case.case_id for case in self.cases]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate planned case IDs.")
        actual = [(run.case_id, run.variant) for run in self.planned_runs]
        expected = {(case_id, variant) for case_id in ids for variant in ("B0", "B1")}
        if len(actual) != len(set(actual)) or set(actual) != expected:
            raise ValueError("Inventory phải có đúng một B0 và B1 cho mỗi planned case.")
        official = any(case.origin.startswith("official_") for case in self.cases)
        if official and not (self.gates.split_frozen and self.gates.review_approved
                             and self.gates.rights_approved and self.gates.dataset_reference):
            raise ValueError("Official data cần frozen split, review/rights approvals và hash reference.")
        if any(c.origin == "official_test" for c in self.cases) and not self.gates.official_test_authorized:
            raise ValueError("Official Test chưa được authorized.")
        return self


class VariantResult(Record):
    variant: Variant
    state: Literal["completed", "failed", "not_run"]
    initial_raw_sha256: Sha256 | None = None
    result: RepairResult | None = None
    partial_history: tuple[RepairAttempt, ...] = ()
    failure_category: Text | None = None

    @model_validator(mode="after")
    def state_contract(self) -> Self:
        if self.state == "not_run":
            if self.result is not None or self.partial_history or self.initial_raw_sha256 is not None:
                raise ValueError("Not-run không có fabricated result/history/raw hash.")
            if self.failure_category is None:
                raise ValueError("Not-run cần reason.")
        elif self.state == "completed":
            if self.result is None or self.result.status not in (
                "accepted_initial", "accepted_after_repair", "budget_exhausted"
            ) or self.failure_category is not None or self.partial_history:
                raise ValueError("Completed cần interpretable controller result.")
        elif self.failure_category is None:
            raise ValueError("Failed cần failure_category.")
        if self.state == "failed" and self.result is not None and self.result.status not in (
            "input_failure", "backend_failure"
        ):
            raise ValueError("Failed không được chứa accepted/exhausted result.")
        if self.result is not None and self.partial_history:
            raise ValueError("Không lưu hai histories cạnh tranh.")
        if self.state == "failed" and self.result is not None and self.failure_category != self.result.failure_category:
            raise ValueError("Failure category của wrapper phải khớp RepairResult.")
        if self.partial_history and self.failure_category != "validation_failure":
            raise ValueError("Partial exception history cần validation_failure category.")
        return self


class PairedCaseResult(Record):
    case_id: Text
    original_summary: str
    initial_raw: str | None = None
    initial_failure_category: Text | None = None
    initial_failure_stage: Literal["input_validation", "backend"] | None = None
    b0: VariantResult
    b1: VariantResult

    @model_validator(mode="after")
    def pair_identity(self) -> Self:
        if self.b0.variant != "B0" or self.b1.variant != "B1":
            raise ValueError("Wrong paired variant identity.")
        if self.initial_raw is not None and self.initial_failure_category is not None:
            raise ValueError("Initial failure không có replay candidate.")
        if (self.initial_failure_category is None) != (self.initial_failure_stage is None):
            raise ValueError("Initial failure cần cả category và stage.")
        if self.initial_failure_stage == "input_validation":
            if self.original_summary.strip() or self.initial_failure_category != "invalid_summary":
                raise ValueError("Input validation failure phải khớp production invalid_summary gate.")
        elif not self.original_summary.strip():
            raise ValueError("Blank summary chỉ được ghi nhận như input_validation failure.")
        return self


class InferenceCost(Record):
    """Ledger backend invocations; model.generate count cần independent observation.

    Loading có thể fail trước model.generate. Replay không có entry. Không suy ra
    model calls từ attempt count; unknown observation giữ None.
    """

    call_id: Text
    case_id: Text
    purpose: Literal["story_generation", "story_repair"]
    attempt_index: int = Field(ge=0, le=2)
    state: Literal["completed", "failed"]
    raw_sha256: Sha256 | None = None
    prompt_sha256: Sha256
    input_tokens: int | None = Field(default=None, ge=0)
    generated_tokens: int | None = Field(default=None, ge=0)
    model_generation_seconds: float | None = Field(default=None, ge=0)
    backend_wall_seconds: float | None = Field(default=None, ge=0)
    peak_allocated_vram_bytes: int | None = Field(default=None, ge=0)
    hit_max_new_tokens: bool | None = None
    model_generate_calls: int | None = Field(default=None, ge=0, le=1)
    model_generate_count_source: Literal["observed", "not_available"] = "not_available"

    @model_validator(mode="after")
    def purpose_index(self) -> Self:
        if (self.attempt_index == 0) != (self.purpose == "story_generation"):
            raise ValueError("Purpose không khớp attempt index.")
        if (self.model_generate_calls is None) != (self.model_generate_count_source == "not_available"):
            raise ValueError("Model.generate count cần explicit observation source.")
        if self.state == "completed" and self.raw_sha256 is None:
            raise ValueError("Completed physical backend invocation cần raw hash.")
        if self.model_generate_calls == 0 and (self.state == "completed" or self.raw_sha256 is not None
                                              or self.generated_tokens not in (None, 0)
                                              or self.model_generation_seconds not in (None, 0.0)):
            raise ValueError("Observed zero model calls mâu thuẫn generated output/measurements.")
        return self


class AnnotatedFinding(Record):
    finding_id: Text
    discrepancy_id: Text
    issue: SemanticIssue
    related_locations: tuple[Location, ...] = ()
    status: Literal["confirmed", "uncertain"]


class HumanAnnotation(Record):
    """Human state tách verdict. Không tự điền gold hoặc adjudication."""

    case_id: Text
    original_summary_sha256: Sha256
    storyboard_sha256: Sha256
    rubric_version: Text
    annotator: Text | None = None
    review_date: Text | None = None
    human_review_state: Literal["pending_human_review", "in_progress", "completed"]
    annotation_status: Literal["confirmed", "uncertain"] | None = None
    adjudicated: bool = False
    prior_prediction_exposure: Literal["none", "yes", "unknown"] = "unknown"
    verdict: Verdict | None = None
    issues: tuple[AnnotatedFinding, ...] = ()
    accepted_creative_variations: tuple[str, ...] = ()
    additional_notes: tuple[str, ...] = ()

    @model_validator(mode="after")
    def human_state(self) -> Self:
        ids = [issue.finding_id for issue in self.issues]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate human finding IDs.")
        if self.human_review_state != "completed":
            if self.verdict is not None or self.annotation_status is not None or self.adjudicated:
                raise ValueError("Pending/in-progress không nhận final verdict/gold status.")
        else:
            if not (self.annotator and self.review_date and self.verdict and self.annotation_status):
                raise ValueError("Completed cần reviewer/date/verdict/annotation status.")
            errors = any(f.issue.severity == "error" and f.status == "confirmed" for f in self.issues)
            if self.verdict == "pass" and self.issues:
                raise ValueError("Confirmed PASS không chứa findings.")
            if self.verdict == "fail" and not errors:
                raise ValueError("FAIL cần confirmed error finding.")
            if self.verdict == "uncertain" and errors:
                raise ValueError("UNCERTAIN không đi cùng confirmed error.")
            if self.annotation_status == "uncertain" and self.adjudicated:
                raise ValueError("Uncertain annotation không mở gold gate.")
        return self


class SemanticCase(Record):
    case_id: Text
    original_summary: Text
    storyboard: Storyboard
    annotation: HumanAnnotation
    reviewer_report: SemanticValidationReport


class DiscrepancyLink(Record):
    """Human crosswalk: không suy ra semantic identity bằng quote/location alone."""

    prediction_index: int = Field(ge=0)
    discrepancy_id: Text
    confirmed_by: Text


class EvaluationInput(Record):
    """Offline caller-supplied batch; không là input cho model/inference."""

    plan: EvaluationPlan
    pairs: tuple[PairedCaseResult, ...]
    costs: tuple[InferenceCost, ...]
