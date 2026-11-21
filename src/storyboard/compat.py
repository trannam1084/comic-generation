"""Adapter chuyển tiếp của TV1; loại bỏ khi PromptBuilder dùng shared schema."""

from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import (
    Character as LegacyCharacter,
    Scene as LegacyScene,
    ScenePrompt,
    Storyboard as LegacyStoryboard,
)

from .schema import Storyboard


class LegacyPromptBuilderAdapter:
    """Giữ nguyên code TV2, chuyển collection types tường minh sau validation."""

    def __init__(self, builder: PromptBuilder) -> None:
        self._builder = builder

    def build(self, storyboard: Storyboard) -> list[ScenePrompt]:
        """Không đổi text, ID, thứ tự hoặc bỏ dữ liệu trong quá trình chuyển."""
        validated = Storyboard.model_validate(storyboard)
        legacy = LegacyStoryboard(
            summary=validated.summary,
            characters=tuple(
                LegacyCharacter(id=character.id, visual=character.visual)
                for character in validated.characters
            ),
            scenes=tuple(
                LegacyScene(
                    index=scene.index,
                    caption_vi=scene.caption_vi,
                    image_prompt_en=scene.image_prompt_en,
                    characters=tuple(scene.characters),
                )
                for scene in validated.scenes
            ),
        )
        return self._builder.build(legacy)
