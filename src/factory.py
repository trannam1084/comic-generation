"""Shared mock/Qwen story factory; build không load model hoặc đọc ambient config."""

from collections.abc import Callable
from dataclasses import fields
from typing import Any

from src.configuration import PipelineConfig, PROJECT_ROOT, load_pipeline_config

from src.comic_renderer.renderer import ComicRenderer
from src.image_generator.image_generator import BaseImageGenerator, MockImageGenerator
from src.image_generator.prompt_builder import PromptBuilder
from src.pipeline import ComicPipeline, PromptStage, StoryStage
from src.pipeline_adapters import ImageStageAdapter, RepairStoryStageAdapter, RenderStageAdapter
from src.story_generator.backend import StoryBackend
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.repair import BoundedRepairController, RepairBackend
from src.storyboard.compat import LegacyPromptBuilderAdapter


def build_pipeline(
    config: PipelineConfig | None = None, *,
    initial_backend: StoryBackend | None = None,
    repair_backend: RepairBackend | None = None,
    story_stage: StoryStage | None = None,
    prompt_stage: PromptStage | None = None,
    image_backend: BaseImageGenerator | None = None,
    renderer_backend: ComicRenderer | None = None,
    qwen_loader: Callable[..., tuple[Any, Any, Any]] | None = None,
) -> ComicPipeline:
    """Explicit dependencies ưu tiên default constructors; config không đọc environment/YAML."""
    if qwen_loader is not None and not callable(qwen_loader):
        raise TypeError("qwen_loader phải là callable test loader.")
    if config is None:
        config = PipelineConfig()
    if not isinstance(config, PipelineConfig):
        raise TypeError("config phải là PipelineConfig; không nhận mapping/YAML path.")
    # Revalidate frozen dataclass để phát hiện caller bypass __init__.
    config = PipelineConfig(**{field.name: getattr(config, field.name) for field in fields(PipelineConfig)})
    if story_stage is not None and (initial_backend is not None or repair_backend is not None or config.max_retries != 0):
        raise ValueError("story_stage explicit không được kết hợp story backends/retry config.")
    if config.story_backend == "qwen":
        if story_stage is not None or initial_backend is not None or repair_backend is not None:
            raise ValueError("Qwen selection không nhận story-stage/backend override; dùng qwen_loader test seam.")
        # Import module nhẹ khi được chọn; constructor không load GPU packages/weights.
        from src.story_generator.qwen_backend import QwenStoryBackend
        qwen = QwenStoryBackend(device=config.resolved_story_device, cache_dir=config.resolved_cache_dir, loader=qwen_loader)
        initial_backend = repair_backend = qwen
    elif qwen_loader is not None:
        raise ValueError("qwen_loader chỉ dùng với explicit qwen mode.")
    if story_stage is None:
        if config.max_retries > 0 and repair_backend is None:
            raise ValueError("Repair budget dương cần explicit repair_backend; không có mock fallback repair.")
        initial = initial_backend if initial_backend is not None else MockStoryBackend()
        story_stage = RepairStoryStageAdapter(BoundedRepairController(initial, repair_backend, max_retries=config.max_retries))
    return ComicPipeline(
        story_stage,
        prompt_stage if prompt_stage is not None else LegacyPromptBuilderAdapter(PromptBuilder()),
        ImageStageAdapter(image_backend if image_backend is not None else MockImageGenerator(), base_seed=config.base_seed),
        RenderStageAdapter(renderer_backend if renderer_backend is not None else ComicRenderer(), output_root=config.output_root),
    )
