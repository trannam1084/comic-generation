"""Điều phối một lần sinh storyboard; không retry, repair hoặc fallback."""

from pydantic import ValidationError

from src.storyboard.schema import Storyboard

from .backend import StoryBackend


class StoryInputError(ValueError):
    """Summary đầu vào sai kiểu hoặc không có nội dung."""


class StoryBackendError(RuntimeError):
    """Backend phát sinh exception; nguyên nhân gốc nằm ở __cause__."""


class StoryOutputError(ValueError):
    """Output sai kiểu, sai contract hoặc không giữ summary gốc."""

    def __init__(self, message: str, *, raw_output: object) -> None:
        super().__init__(message)
        self.raw_output = raw_output


class StoryGenerator:
    """Nhận backend qua dependency injection và trả shared Storyboard đã validate."""

    def __init__(self, backend: StoryBackend) -> None:
        self._backend = backend

    def generate(self, summary: str) -> Storyboard:
        """Giữ nguyên input/output; mỗi input hợp lệ chỉ gọi backend một lần."""
        if not isinstance(summary, str) or not summary.strip():
            raise StoryInputError("Summary phải là string không rỗng hoặc whitespace.")

        try:
            raw_output = self._backend.generate(summary)
        except Exception as exc:
            raise StoryBackendError("Backend không thể sinh storyboard.") from exc

        if not isinstance(raw_output, str):
            raise StoryOutputError(
                f"Backend phải trả raw JSON dạng str, nhận {type(raw_output).__name__}.",
                raw_output=raw_output,
            )

        try:
            storyboard = Storyboard.model_validate_json(raw_output)
        except ValidationError as exc:
            raise StoryOutputError(
                "Output không phải storyboard JSON hợp lệ theo Contract v1.0.",
                raw_output=raw_output,
            ) from exc

        if storyboard.summary != summary:
            raise StoryOutputError(
                "Summary trong storyboard không khớp chính xác input gốc.",
                raw_output=raw_output,
            )

        return storyboard
