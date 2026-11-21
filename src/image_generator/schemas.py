from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Character:
    id: str
    visual: str


@dataclass(frozen=True)
class Scene:
    index: int
    caption_vi: str
    image_prompt_en: str
    characters: tuple[str, ...]


@dataclass(frozen=True)
class Storyboard:
    summary: str
    characters: tuple[Character, ...]
    scenes: tuple[Scene, ...]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Storyboard":
        try:
            characters = tuple(
                Character(id=c["id"], visual=c["visual"]) for c in data["characters"]
            )
            scenes = tuple(
                Scene(
                    index=s["index"],
                    caption_vi=s["caption_vi"],
                    image_prompt_en=s["image_prompt_en"],
                    characters=tuple(s["characters"]),
                )
                for s in data["scenes"]
            )
            return cls(summary=data["summary"], characters=characters, scenes=scenes)
        except KeyError as e:
            raise ValueError(f"Storyboard thiếu trường bắt buộc: {e}") from e


@dataclass(frozen=True)
class ScenePrompt:
    """Kết quả của Prompt Builder cho một cảnh. Đầu vào của Image Generator."""
    scene_index: int
    prompt: str
    negative_prompt: str
    character_ids: tuple[str, ...]


@dataclass
class GeneratedImage:
    """Kết quả của Image Generator cho một cảnh."""
    scene_index: int
    image: Any                      # PIL.Image.Image
    seed: int | None
    backend: str                    # "mock" hoặc "sdxl"
    elapsed_sec: float
    params: dict[str, Any] = field(default_factory=dict)