"""Orchestration bằng Dependency Injection; không cài đặt image/render backend."""

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from src.image_generator.schemas import GeneratedImage, ScenePrompt
from src.storyboard.schema import Storyboard


class StoryStage(Protocol):
    def generate(self, summary: str) -> Storyboard:
        """Sinh shared Storyboard; lỗi được propagate tới caller."""
        ...


class PromptStage(Protocol):
    def build(self, storyboard: Storyboard) -> list[ScenePrompt]:
        """Nhận shared schema; dùng adapter rõ ràng nếu builder còn legacy."""
        ...


class ImageStage(Protocol):
    def generate(self, prompts: list[ScenePrompt]) -> list[GeneratedImage]:
        """Interface đề xuất cho TV2, chưa có image backend trong module này."""
        ...


@dataclass(frozen=True)
class ComicPanel:
    """Envelope ghép ảnh/caption cho renderer, không phải Storyboard schema mới."""

    scene_index: int
    caption_vi: str
    generated_image: GeneratedImage


class RenderStage(Protocol):
    def render(self, panels: list[ComicPanel]) -> Path:
        """Tạo artifact và trả Path tới file không rỗng; cần thống nhất với TV2."""
        ...


@dataclass(frozen=True)
class ComicResult:
    """Kết quả orchestration; không khẳng định chất lượng ảnh hoặc nội dung."""

    storyboard: Storyboard
    prompts: list[ScenePrompt]
    images: list[GeneratedImage]
    comic_path: Path


class PipelineContractError(ValueError):
    """Dependency trả dữ liệu không đúng interface; stage xác định điểm lỗi."""

    def __init__(self, stage: str, message: str) -> None:
        super().__init__(f"{stage}: {message}")
        self.stage = stage


def _check_indexed_list(
    values: object,
    expected_type: type[ScenePrompt] | type[GeneratedImage],
    stage: str,
) -> None:
    """Không ép collection, sort, bỏ hoặc thêm phần tử để che lỗi alignment."""
    if not isinstance(values, list) or len(values) != 4:
        raise PipelineContractError(stage, "Cần list có đúng bốn phần tử.")
    if not all(isinstance(value, expected_type) for value in values):
        raise PipelineContractError(stage, f"Mọi phần tử phải là {expected_type.__name__}.")
    indices = [value.scene_index for value in values]
    if any(type(index) is not int for index in indices) or indices != [1, 2, 3, 4]:
        raise PipelineContractError(stage, "Scene index phải đúng thứ tự [1, 2, 3, 4].")


class ComicPipeline:
    """Mỗi stage được gọi tối đa một lần; không retry, repair hoặc fallback."""

    def __init__(
        self,
        story_generator: StoryStage,
        prompt_builder: PromptStage,
        image_generator: ImageStage,
        renderer: RenderStage,
    ) -> None:
        self._story_generator = story_generator
        self._prompt_builder = prompt_builder
        self._image_generator = image_generator
        self._renderer = renderer

    def generate(self, summary: str) -> ComicResult:
        """Giữ nguyên exception từ dependencies; chỉ thêm lỗi kiểm tra contract."""
        generated = self._story_generator.generate(summary)
        if not isinstance(generated, Storyboard):
            raise PipelineContractError("story", "Story Generator phải trả shared Storyboard.")
        # Revalidate và tạo bản riêng, không giao instance của caller cho stage sau.
        storyboard = Storyboard.model_validate(generated)
        if storyboard.summary != summary:
            raise PipelineContractError("story", "Summary không khớp input gốc.")

        builder_input = Storyboard.model_validate(storyboard)
        prompts = self._prompt_builder.build(builder_input)
        if builder_input.model_dump() != storyboard.model_dump():
            raise PipelineContractError("prompts", "PromptBuilder đã mutate Storyboard input.")
        _check_indexed_list(prompts, ScenePrompt, "prompts")

        images = self._image_generator.generate(list(prompts))
        _check_indexed_list(images, GeneratedImage, "images")
        if any(image.image is None for image in images):
            raise PipelineContractError("images", "GeneratedImage.image không được là None.")

        images_by_index = {image.scene_index: image for image in images}
        panels = [
            ComicPanel(
                scene_index=scene.index,
                caption_vi=scene.caption_vi,
                generated_image=images_by_index[scene.index],
            )
            for scene in storyboard.scenes
        ]
        comic_path = self._renderer.render(panels)
        if not isinstance(comic_path, Path):
            raise PipelineContractError("render", "Renderer phải trả pathlib.Path.")
        if not comic_path.is_file() or comic_path.stat().st_size == 0:
            raise PipelineContractError("render", "Artifact phải là file tồn tại và không rỗng.")

        return ComicResult(storyboard, prompts, images, comic_path)
