"""Gradio UI cho AI Comic Generation.

UI chỉ phụ thuộc vào một hợp đồng duy nhất do nhóm trưởng chốt:
    result = pipeline.generate(summary)
với result.comic_path, result.storyboard, result.images (và result.prompts).
UI không tự dựng Story Generator hay Comic Pipeline riêng.

Chạy thử giao diện bằng pipeline giả (chỉ để phát triển UI, không phải pipeline thật):
    python app.py --demo
"""

from __future__ import annotations

import argparse
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.pipeline import ComicResult, PipelineContractError

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
EXAMPLE_STORYBOARD = ROOT / "examples" / "storyboard.json"

BUSY_MESSAGE = "Đang tạo truyện tranh... Khi chạy model thật bước này có thể mất vài phút."


class PipelineLike(Protocol):
    def generate(self, summary: str) -> ComicResult:
        """Hợp đồng duy nhất mà UI dùng."""
        ...


@dataclass(frozen=True)
class UIOutput:
    """Dữ liệu đã định dạng sẵn cho các thành phần giao diện."""

    ok: bool
    status: str
    gallery: list[tuple[Any, str]]
    comic_path: str | None
    storyboard_json: str
    prompts_text: str
    run_info: str


def _error(message: str) -> UIOutput:
    return UIOutput(False, f"LỖI: {message}", [], None, "", "", "")


def _format_result(result: ComicResult, elapsed_sec: float) -> UIOutput:
    images_by_index = {g.scene_index: g for g in result.images}

    gallery: list[tuple[Any, str]] = []
    info_lines: list[str] = []
    for scene in result.storyboard.scenes:
        generated = images_by_index[scene.index]
        gallery.append((generated.image, f"Cảnh {scene.index}: {scene.caption_vi}"))
        info_lines.append(
            f"Cảnh {scene.index}: backend={generated.backend}, seed={generated.seed}, "
            f"thời gian={generated.elapsed_sec:.2f}s, params={generated.params}"
        )
    info_lines.append(f"Tổng thời gian toàn pipeline: {elapsed_sec:.2f}s")

    prompts_text = "\n\n".join(
        f"[Cảnh {p.scene_index}]\nPrompt: {p.prompt}\nNegative: {p.negative_prompt}"
        for p in result.prompts
    )
    return UIOutput(
        ok=True,
        status=f"Hoàn thành trong {elapsed_sec:.2f}s.",
        gallery=gallery,
        comic_path=str(result.comic_path),
        storyboard_json=result.storyboard.model_dump_json(indent=2),
        prompts_text=prompts_text,
        run_info="\n".join(info_lines),
    )


def run_generation(pipeline: PipelineLike, summary: object) -> UIOutput:
    """Gọi pipeline và định dạng kết quả. Mọi lỗi đều được báo rõ, không thay bằng ảnh giả."""
    if not isinstance(summary, str) or not summary.strip():
        return _error("Vui lòng nhập tóm tắt truyện trước khi tạo.")

    start = time.perf_counter()
    try:
        # Truyền nguyên văn: pipeline so khớp summary với input gốc nên UI không strip hay chuẩn hóa.
        result = pipeline.generate(summary)
    except PipelineContractError as exc:
        logger.exception("Pipeline trả dữ liệu sai hợp đồng")
        return _error(f"Dữ liệu giữa các bước không hợp lệ ({exc}).")
    except Exception as exc:  # noqa: BLE001 - hiển thị lỗi thật cho người dùng, không nuốt lỗi
        logger.exception("Pipeline thất bại")
        return _error(f"Không tạo được truyện tranh ({type(exc).__name__}): {exc}")

    elapsed = time.perf_counter() - start
    try:
        return _format_result(result, elapsed)
    except Exception as exc:  # noqa: BLE001
        logger.exception("Không đọc được kết quả pipeline")
        return _error(f"Pipeline trả kết quả không đọc được ({type(exc).__name__}): {exc}")


def load_example_summary() -> str | None:
    """Lấy summary mẫu từ fixture chuẩn của nhóm để làm ví dụ bấm nhanh."""
    import json

    try:
        data = json.loads(EXAMPLE_STORYBOARD.read_text(encoding="utf-8"))
        summary = data["summary"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return summary if isinstance(summary, str) else None


def create_demo(pipeline: PipelineLike):
    """Dựng giao diện Gradio quanh một pipeline. Import gradio trễ để test CPU không cần gradio."""
    import gradio as gr

    with gr.Blocks(title="AI Comic Generation") as demo:
        gr.Markdown(
            "# AI Comic Generation\n"
            "Nhập tóm tắt truyện bằng tiếng Việt, hệ thống tạo truyện tranh đúng 4 khung."
        )
        summary_box = gr.Textbox(
            label="Tóm tắt truyện (tiếng Việt)",
            lines=5,
            placeholder="Ví dụ: Thỏ thách rùa thi chạy...",
        )
        example = load_example_summary()
        if example is not None:
            gr.Examples(examples=[[example]], inputs=summary_box, label="Ví dụ")
        run_button = gr.Button("Tạo truyện tranh", variant="primary")
        status_box = gr.Textbox(label="Trạng thái", interactive=False)

        gallery = gr.Gallery(label="4 khung truyện", columns=4, object_fit="contain", height=360)
        comic_image = gr.Image(label="Truyện tranh 2×2", type="filepath", interactive=False)
        download = gr.File(label="Tải ảnh truyện tranh (PNG)", interactive=False)

        with gr.Accordion("Storyboard và prompts", open=False):
            storyboard_box = gr.Code(label="Storyboard JSON", language="json", interactive=False)
            prompts_box = gr.Textbox(label="Image prompts", lines=10, interactive=False)
        info_box = gr.Textbox(label="Thông tin lần chạy (model, seed, thời gian)", lines=6, interactive=False)

        outputs = [status_box, gallery, comic_image, download, storyboard_box, prompts_box, info_box]

        def on_click(summary: str):
            yield BUSY_MESSAGE, [], None, None, "", "", ""
            out = run_generation(pipeline, summary)
            yield (
                out.status,
                out.gallery,
                out.comic_path,
                out.comic_path,
                out.storyboard_json,
                out.prompts_text,
                out.run_info,
            )

        run_button.click(on_click, inputs=summary_box, outputs=outputs, concurrency_limit=1)
    return demo


# ---------------------------------------------------------------------------
# CHỈ DÙNG ĐỂ PHÁT TRIỂN UI. Xóa khi ComicPipeline thật (Task 07B của TV1) sẵn sàng.
# ---------------------------------------------------------------------------
class _DemoPipeline:
    """Pipeline giả: fixture storyboard + ảnh mock + renderer thật. Không phải Comic Pipeline của nhóm."""

    def __init__(self, output_dir: Path = OUTPUT_DIR / "demo_ui") -> None:
        self._output_dir = output_dir

    def generate(self, summary: str) -> ComicResult:
        from src.comic_renderer.renderer import ComicRenderer
        from src.image_generator.image_generator import MockImageGenerator
        from src.image_generator.prompt_builder import PromptBuilder
        from src.image_generator.schemas import Storyboard as LegacyStoryboard
        from src.storyboard.schema import Storyboard

        storyboard = Storyboard.model_validate_json(EXAMPLE_STORYBOARD.read_text(encoding="utf-8"))
        if summary != storyboard.summary:
            raise ValueError(
                "Chế độ demo chỉ hỗ trợ đúng tóm tắt mẫu (bấm ví dụ bên dưới ô nhập)."
            )

        prompts = PromptBuilder().build(LegacyStoryboard.from_dict(storyboard.model_dump()))
        images = MockImageGenerator().generate_all(prompts)
        renderer = ComicRenderer()
        rendered = renderer.render(images, [scene.caption_vi for scene in storyboard.scenes])

        run_dir = self._output_dir / time.strftime("run_%Y%m%d_%H%M%S")
        comic_path = renderer.save(rendered, run_dir)[-1]
        return ComicResult(storyboard, prompts, images, comic_path)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gradio UI cho AI Comic Generation")
    parser.add_argument("--demo", action="store_true", help="dùng pipeline giả để thử giao diện")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.demo:
        raise SystemExit(
            "Chưa có pipeline thật để gắn vào UI (chờ TV1 tích hợp ở Task 07B). "
            "Dùng `python app.py --demo` để thử giao diện."
        )

    demo = create_demo(_DemoPipeline())
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    demo.launch(server_port=args.port, allowed_paths=[str(OUTPUT_DIR)])


if __name__ == "__main__":
    main()