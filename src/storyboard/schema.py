"""Shared Storyboard Contract v1.0: chỉ kiểm tra cấu trúc, không sửa nội dung."""

from __future__ import annotations

from typing import Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

__all__ = ["Character", "Scene", "Storyboard"]


def _require_nonblank(value: str) -> str:
    """Từ chối chuỗi trống nhưng giữ nguyên khoảng trắng của chuỗi hợp lệ."""
    if not value.strip():
        raise ValueError("Chuỗi không được rỗng hoặc chỉ chứa whitespace.")
    return value


class _ContractModel(BaseModel):
    """Cấu hình chung; không coi model mutable là hợp lệ mãi sau khi parse."""

    model_config = ConfigDict(
        strict=True,
        extra="forbid",
        revalidate_instances="always",
    )


class Character(_ContractModel):
    """Nhân vật có ID phân biệt hoa/thường và mô tả ngoại hình dùng chung."""

    id: str
    visual: str

    @field_validator("id", "visual")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        """Không trim hoặc đổi case ID/mô tả ngoại hình."""
        return _require_nonblank(value)


class Scene(_ContractModel):
    """Một cảnh; base prompt độc lập với final prompt của Image Pipeline."""

    index: int
    caption_vi: str
    image_prompt_en: str
    characters: list[str]

    @field_validator("caption_vi", "image_prompt_en")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        """Kiểm tra nội dung có ký tự nhưng không đặt giới hạn độ dài."""
        return _require_nonblank(value)

    @field_validator("characters")
    @classmethod
    def require_unique_references(cls, value: list[str]) -> list[str]:
        """Cho phép list rỗng; không tự xóa reference trùng."""
        if len(value) != len(set(value)):
            raise ValueError("Character references trong cùng scene không được trùng.")
        return value


class Storyboard(_ContractModel):
    """Bốn cảnh đúng thứ tự và references hợp lệ; chưa kiểm tra ngữ nghĩa truyện."""

    summary: str
    characters: list[Character]
    scenes: list[Scene] = Field(min_length=4, max_length=4)

    @field_validator("summary")
    @classmethod
    def require_nonblank_summary(cls, value: str) -> str:
        """Giữ nguyên tóm tắt gốc để bước semantic validation đối chiếu sau."""
        return _require_nonblank(value)

    @field_validator("characters")
    @classmethod
    def require_unique_character_ids(cls, value: list[Character]) -> list[Character]:
        """So sánh ID chính xác, phân biệt chữ hoa/chữ thường."""
        ids = [character.id for character in value]
        if len(ids) != len(set(ids)):
            raise ValueError("Character ID trong Storyboard không được trùng.")
        return value

    @field_validator("scenes")
    @classmethod
    def require_scene_order(cls, value: list[Scene]) -> list[Scene]:
        """Reject index sai thứ tự hoặc trùng; không tự sort scenes."""
        indices = [scene.index for scene in value]
        if indices != [1, 2, 3, 4]:
            raise ValueError(
                f"scenes phải có index theo thứ tự chính xác [1, 2, 3, 4]; nhận {indices}."
            )
        return value

    @model_validator(mode="after")
    def require_known_character_references(self) -> Self:
        """Đối chiếu references sau khi tất cả fields đã validate thành công."""
        known_ids = {character.id for character in self.characters}
        for position, scene in enumerate(self.scenes):
            unknown = [cid for cid in scene.characters if cid not in known_ids]
            if unknown:
                raise ValueError(
                    f"scenes[{position}].characters (index={scene.index}) "
                    f"tham chiếu Character ID không tồn tại: {unknown!r}."
                )
        return self
