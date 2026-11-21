"""Adapters thuộc TV1 cho production controller và image/renderer interfaces TV2."""

from copy import deepcopy
from pathlib import Path
from tempfile import mkdtemp

from PIL import Image

from src.comic_renderer.renderer import ComicRenderer, RenderResult
from src.image_generator.image_generator import BaseImageGenerator, validate_scene_prompts
from src.image_generator.schemas import GeneratedImage, ScenePrompt
from src.pipeline import ComicPanel, PipelineContractError
from src.story_generator.repair import BoundedRepairController, RepairAttempt, RepairResult
from src.storyboard.schema import Storyboard


class StoryStageError(RuntimeError):
    """Failure có snapshot result/history; unexpected cause giữ bằng exception chaining."""

    def __init__(self, category: str, *, result: RepairResult | None = None,
                 attempts: tuple[RepairAttempt, ...] = ()) -> None:
        super().__init__(f"Story stage thất bại: {category}.")
        self.category = category
        self.result = deepcopy(result)
        self.attempts = deepcopy(result.attempts if result is not None else attempts)


class RepairStoryStageAdapter:
    """Stateless adapter: một controller invocation, không retry/fallback/last-result state."""

    def __init__(self, controller: BoundedRepairController) -> None:
        self._controller = controller

    def generate(self, summary: str) -> Storyboard:
        """Chỉ expose accepted board có raw/history nhất quán; không sửa dữ liệu."""
        try:
            result = self._controller.generate(summary)
        except Exception as exc:
            raise StoryStageError("controller_exception", attempts=getattr(exc, "attempts", ())) from exc
        if not isinstance(result, RepairResult):
            raise StoryStageError("invalid_controller_result")
        if result.status not in {"accepted_initial", "accepted_after_repair"}:
            raise StoryStageError(result.status, result=result)
        try:
            if result.storyboard is None or not result.attempts or result.original_summary != summary:
                raise ValueError("Accepted result thiếu storyboard/history hoặc summary không khớp.")
            last = result.attempts[-1]
            if (last.validation_report is None or last.validation_report.production_success is not True
                    or any(getattr(last.validation_report, field) != "passed"
                           for field in ("json_syntax", "structural_validity", "summary_matching"))):
                raise ValueError("Accepted attempt không có successful deterministic report.")
            if (result.status == "accepted_initial") != (last.attempt_index == 0):
                raise ValueError("Status không khớp accepted attempt index.")
            board = Storyboard.model_validate(result.storyboard)
            parsed = Storyboard.model_validate_json(last.raw_output)
            if board.summary != summary or board.model_dump() != parsed.model_dump():
                raise ValueError("Accepted board không khớp input/accepted raw output.")
        except Exception as exc:
            raise StoryStageError("invalid_accepted_result", result=result) from exc
        return board


class ImageStageAdapter:
    """Một generate_all call, giữ TV2 seed=base_seed+scene_index và thứ tự input."""

    def __init__(self, backend: BaseImageGenerator, *, base_seed: int = 42) -> None:
        if type(base_seed) is not int:
            raise ValueError("base_seed phải là integer, không nhận bool.")
        self._backend, self._base_seed = backend, base_seed

    def generate(self, prompts: list[ScenePrompt]) -> list[GeneratedImage]:
        """Validate trước handoff; backend exception propagate nguyên trạng."""
        if not isinstance(prompts, list):
            raise PipelineContractError("images", "prompts phải là list.")
        validate_scene_prompts(prompts)
        return self._backend.generate_all(prompts, base_seed=self._base_seed)


class RenderStageAdapter:
    """Lưu PNG qua TV2 renderer trong atomic unique directory, giữ partial files khi lỗi."""

    def __init__(self, backend: ComicRenderer, *, output_root: Path) -> None:
        if not isinstance(output_root, Path):
            raise TypeError("output_root phải là pathlib.Path.")
        self._backend, self.output_root = backend, output_root.resolve()

    def render(self, panels: list[ComicPanel]) -> Path:
        """Không sort panels; render/save một lần, kiểm tra năm PNG trước success."""
        if not isinstance(panels, list) or len(panels) != 4 or any(not isinstance(p, ComicPanel) for p in panels):
            raise PipelineContractError("render", "Cần list đúng bốn ComicPanel.")
        for index, panel in enumerate(panels, 1):
            generated = panel.generated_image
            if (type(panel.scene_index) is not int or panel.scene_index != index
                    or not isinstance(generated, GeneratedImage)
                    or type(generated.scene_index) is not int or generated.scene_index != index
                    or not isinstance(generated.image, Image.Image)
                    or not isinstance(panel.caption_vi, str) or not panel.caption_vi.strip()):
                raise PipelineContractError("render", "Panel index/caption/Pillow image không hợp lệ.")
        self.output_root.mkdir(parents=True, exist_ok=True)
        run_dir = Path(mkdtemp(prefix="comic-", dir=self.output_root))
        if not run_dir.resolve().is_relative_to(self.output_root):
            raise PipelineContractError("render", "Run directory nằm ngoài output root.")
        rendered = self._backend.render([p.generated_image for p in panels], [p.caption_vi for p in panels])
        if (not isinstance(rendered, RenderResult) or len(rendered.panels) != 4
                or not isinstance(rendered.comic, Image.Image)):
            raise PipelineContractError("render", "Renderer phải trả RenderResult gồm bốn panels và comic.")
        saved = self._backend.save(rendered, run_dir)
        expected = [run_dir / f"panel_{i}.png" for i in range(1, 5)] + [run_dir / "comic.png"]
        if not isinstance(saved, list) or saved != expected:
            raise PipelineContractError("render", "save phải trả bốn panel paths và comic.png trong run directory.")
        for path in expected:
            if path.is_symlink() or not path.resolve().is_relative_to(run_dir.resolve()) or not path.is_file() or path.stat().st_size == 0:
                raise PipelineContractError("render", "PNG thiếu/rỗng hoặc path không an toàn.")
            with Image.open(path) as image:
                if image.format != "PNG":
                    raise PipelineContractError("render", "Artifact phải đúng định dạng PNG.")
                image.verify()
        with Image.open(expected[-1]) as image:
            if image.size != rendered.comic.size:
                raise PipelineContractError("render", "Saved comic dimensions không khớp RenderResult.")
        return expected[-1]
