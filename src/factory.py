"""Factory CPU mock; explicit Python config, không tự đọc YAML/.env hoặc load model."""

from dataclasses import dataclass
from pathlib import Path

from src.comic_renderer.renderer import ComicRenderer
from src.image_generator.image_generator import BaseImageGenerator, MockImageGenerator
from src.image_generator.prompt_builder import PromptBuilder
from src.pipeline import ComicPipeline, PromptStage, StoryStage
from src.pipeline_adapters import ImageStageAdapter, RepairStoryStageAdapter, RenderStageAdapter
from src.story_generator.backend import StoryBackend
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.repair import BoundedRepairController, RepairBackend
from src.storyboard.compat import LegacyPromptBuilderAdapter

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class PipelineConfig:
    """Chỉ mock/mock/cpu; retry default0 riêng cho mock smoke, không đổi real policy2."""

    story_backend: str = "mock"
    image_backend: str = "mock"
    device: str = "cpu"
    output_dir: str | Path = "outputs"
    max_retries: int = 0
    base_seed: int = 42

    def __post_init__(self) -> None:
        for name, expected in [("story_backend", "mock"), ("image_backend", "mock"), ("device", "cpu")]:
            value = getattr(self, name)
            if type(value) is not str or value != expected:
                raise ValueError(f"{name} hiện chỉ hỗ trợ {expected!r}; không fallback.")
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError("max_retries phải là integer không âm, không nhận bool.")
        if type(self.base_seed) is not int:
            raise ValueError("base_seed phải là integer, không nhận bool.")
        if not isinstance(self.output_dir, (str, Path)):
            raise TypeError("output_dir phải là str hoặc pathlib.Path.")
        if isinstance(self.output_dir, str) and not self.output_dir.strip():
            raise ValueError("output_dir không được rỗng.")

    @property
    def output_root(self) -> Path:
        """Đường dẫn tương đối luôn tính từ project root, không từ working directory."""
        path = Path(self.output_dir)
        return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


def build_pipeline(
    config: PipelineConfig | None = None, *,
    initial_backend: StoryBackend | None = None,
    repair_backend: RepairBackend | None = None,
    story_stage: StoryStage | None = None,
    prompt_stage: PromptStage | None = None,
    image_backend: BaseImageGenerator | None = None,
    renderer_backend: ComicRenderer | None = None,
) -> ComicPipeline:
    """Explicit dependencies ưu tiên default constructors; config không đọc environment/YAML."""
    if config is None:
        config = PipelineConfig()
    if not isinstance(config, PipelineConfig):
        raise TypeError("config phải là PipelineConfig; không nhận mapping/YAML path.")
    # Revalidate frozen dataclass để phát hiện caller bypass __init__.
    config = PipelineConfig(**{name: getattr(config, name) for name in PipelineConfig.__dataclass_fields__})
    if story_stage is not None and (initial_backend is not None or repair_backend is not None or config.max_retries != 0):
        raise ValueError("story_stage explicit không được kết hợp story backends/retry config.")
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
