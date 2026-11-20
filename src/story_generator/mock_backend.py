"""Backend fixture deterministic trên CPU; không phải AI sinh truyện."""

from pathlib import Path

from src.storyboard.schema import Storyboard


class MockStoryBackend:
    """Đọc và validate một snapshot fixture khi khởi tạo rõ ràng."""

    def __init__(self, fixture_path: str | Path | None = None) -> None:
        path = (
            Path(fixture_path)
            if fixture_path is not None
            else Path(__file__).resolve().parents[2] / "examples" / "storyboard.json"
        )
        self._raw_output = path.read_text(encoding="utf-8")
        storyboard = Storyboard.model_validate_json(self._raw_output)
        self._summary = storyboard.summary

    def generate(self, summary: str) -> str:
        """Chỉ hỗ trợ summary khớp chính xác fixture; không trim hay thay truyện."""
        if summary != self._summary:
            raise ValueError(
                "MockStoryBackend chưa có fixture cho summary đầu vào; "
                "summary phải khớp chính xác fixture."
            )
        return self._raw_output
