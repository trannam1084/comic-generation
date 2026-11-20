"""Interface backend sinh raw storyboard JSON, không phụ thuộc GPU."""

from typing import Protocol


class StoryBackend(Protocol):
    """Backend có thể thay thế qua structural typing, không cần kế thừa class."""

    def generate(self, summary: str) -> str:
        """Trả raw JSON hoặc raise lỗi; không yêu cầu tải model lúc import."""
        ...
