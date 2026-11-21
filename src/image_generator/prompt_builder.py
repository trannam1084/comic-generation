
from __future__ import annotations

import re

from .schemas import Scene, ScenePrompt, Storyboard

DEFAULT_STYLE = "comic book illustration, clean line art, vibrant colors, consistent character design"
DEFAULT_NEGATIVE = "text, letters, watermark, signature, blurry, low quality, deformed, extra limbs"
EXPECTED_SCENES = 4


def _normalize(text: str) -> str:
    """Gộp khoảng trắng thừa, bỏ dấu chấm cuối để nối chuỗi gọn."""
    text = re.sub(r"\s+", " ", text).strip()
    return text.rstrip(".")


class PromptBuilder:
    def __init__(
        self,
        style: str = DEFAULT_STYLE,
        negative_prompt: str = DEFAULT_NEGATIVE,
        use_shared_characters: bool = True,
    ) -> None:
        self.style = style
        self.negative_prompt = negative_prompt
        self.use_shared_characters = use_shared_characters

    def build(self, storyboard: Storyboard) -> list[ScenePrompt]:
        if len(storyboard.scenes) != EXPECTED_SCENES:
            raise ValueError(
                f"Cần đúng {EXPECTED_SCENES} cảnh, nhận được {len(storyboard.scenes)}"
            )
        visual_by_id = {c.id: c.visual for c in storyboard.characters}
        return [self._build_scene(s, visual_by_id) for s in storyboard.scenes]

    def _build_scene(self, scene: Scene, visual_by_id: dict[str, str]) -> ScenePrompt:
        unknown = [cid for cid in scene.characters if cid not in visual_by_id]
        if unknown:
            raise ValueError(f"Cảnh {scene.index} tham chiếu nhân vật không tồn tại: {unknown}")

        parts = [_normalize(scene.image_prompt_en)]
        if self.use_shared_characters and scene.characters:
            descriptions = "; ".join(
                _normalize(visual_by_id[cid]) for cid in scene.characters
            )
            parts.append(descriptions)
        parts.append(self.style)

        return ScenePrompt(
            scene_index=scene.index,
            prompt=", ".join(parts),
            negative_prompt=self.negative_prompt,
            character_ids=scene.characters,
        )