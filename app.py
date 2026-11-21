"""Gradio UI cho AI Comic Generation.

UI chỉ phụ thuộc vào một hợp đồng duy nhất do nhóm trưởng chốt:
    result = pipeline.generate(summary)
với result.comic_path, result.storyboard, result.images (và result.prompts).
UI không tự dựng Story Generator hay Comic Pipeline riêng.

Chế độ demo dùng pipeline dùng chung của nhóm (src.factory.build_pipeline) với backend mock:
    python app.py --demo
"""

from __future__ import annotations

import argparse
import logging
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from src.configuration import PipelineConfig
from src.factory import build_pipeline
from src.pipeline import ComicPipeline, ComicResult, PipelineContractError
from src.pipeline_adapters import StoryStageError

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent
OUTPUT_DIR = ROOT / "outputs"
DEMO_OUTPUT_DIR = OUTPUT_DIR / "demo_ui"
EXAMPLE_STORYBOARD = ROOT / "examples" / "storyboard.json"

EXPECTED_PANELS = 4
MAX_ERROR_CHARS = 300

BUSY_MESSAGE = "Đang tạo truyện tranh... Khi chạy model thật bước này có thể mất vài phút."
DEMO_BANNER = (
    "## CHẾ ĐỘ DEMO\n"
    "Đang dùng **backend mock dùng chung** của nhóm: story mock (storyboard mẫu cố định) và "
    "**ảnh mock** (không phải kết quả từ LLM hay model sinh ảnh thật). "
    "Với backend mock, hãy dùng ví dụ bên dưới ô nhập."
)


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


class _InvalidResult(ValueError):
    """Kết quả pipeline không đạt kiểm tra tối thiểu của UI."""


# ---------------------------------------------------------------------------
# Lọc thông tin nhạy cảm trước khi đưa lỗi lên giao diện hoặc ghi log
# ---------------------------------------------------------------------------
_URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
_WINDOWS_PATH_RE = re.compile(r"(?:[A-Za-z]:[\\/]|\\\\)[^\s'\"<>|]*")
_POSIX_PATH_RE = re.compile(r"(?<![\w:/.\-])/(?:[\w.\-+@~]+/)*[\w.\-+@~]+")
_BEARER_RE = re.compile(r"\bbearer\s+[A-Za-z0-9\-._~+/]+=*", re.IGNORECASE)
_KEY_VALUE_RE = re.compile(
    r"\b(api[_-]?key|access[_-]?token|token|secret|password|passwd|authorization|credentials?)\b"
    r"(\s*[:=]\s*)(\S+)",
    re.IGNORECASE,
)
_TOKEN_RE = re.compile(
    r"\b(?:hf_|ghp_|gho_|ghs_|github_pat_|sk-|xox[abprs]-)[A-Za-z0-9_\-]{8,}|\bAKIA[0-9A-Z]{12,}\b"
)


def sanitize_message(text: object) -> str:
    """Che đường dẫn nội bộ, URL, token và mật khẩu; gộp xuống dòng và cắt ngắn."""
    cleaned = str(text)
    cleaned = _URL_RE.sub("<url>", cleaned)
    cleaned = _WINDOWS_PATH_RE.sub("<đường dẫn>", cleaned)
    cleaned = _BEARER_RE.sub("Bearer <đã ẩn>", cleaned)
    cleaned = _KEY_VALUE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}<đã ẩn>", cleaned)
    cleaned = _TOKEN_RE.sub("<đã ẩn>", cleaned)
    cleaned = _POSIX_PATH_RE.sub("<đường dẫn>", cleaned)
    cleaned = " ".join(cleaned.split())
    if len(cleaned) > MAX_ERROR_CHARS:
        cleaned = cleaned[:MAX_ERROR_CHARS].rstrip() + "…"
    return cleaned


def _error(message: str) -> UIOutput:
    return UIOutput(False, f"LỖI: {message}", [], None, "", "", "")


def _describe(exc: BaseException) -> str:
    """Tên loại lỗi cộng thông điệp đã lọc (không bao giờ dùng str(exc) thô)."""
    safe = sanitize_message(exc)
    return f"{type(exc).__name__}: {safe}" if safe else type(exc).__name__


def _validate_result(result: object) -> None:
    """Kiểm tra tối thiểu trước khi báo thành công. Thông báo lỗi không chứa đường dẫn."""
    comic_path = getattr(result, "comic_path", None)
    try:
        path = Path(comic_path)  # type: ignore[arg-type]
        usable = path.is_file() and path.stat().st_size > 0
    except (TypeError, OSError):
        usable = False
    if not usable:
        raise _InvalidResult("comic_path không tồn tại hoặc là file rỗng")

    for name in ("images", "prompts"):
        items = getattr(result, name, None)
        if not isinstance(items, (list, tuple)) or len(items) != EXPECTED_PANELS:
            got = len(items) if isinstance(items, (list, tuple)) else "không phải danh sách"
            raise _InvalidResult(f"cần đúng {EXPECTED_PANELS} {name}, nhận {got}")

    scenes = getattr(getattr(result, "storyboard", None), "scenes", None)
    if not isinstance(scenes, (list, tuple)) or len(scenes) != EXPECTED_PANELS:
        raise _InvalidResult(f"storyboard cần đúng {EXPECTED_PANELS} cảnh")


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
    """Gọi pipeline và định dạng kết quả. Lỗi được báo rõ nhưng đã lọc, không thay bằng ảnh giả."""
    if not isinstance(summary, str) or not summary.strip():
        return _error("Vui lòng nhập tóm tắt truyện trước khi tạo.")

    start = time.perf_counter()
    # Chỉ ghi độ dài, không ghi nội dung tóm tắt của người dùng.
    logger.info("Gọi pipeline.generate một lần (độ dài tóm tắt: %d ký tự)", len(summary))
    try:
        # Truyền nguyên văn: pipeline so khớp summary với input gốc nên UI không strip hay chuẩn hóa.
        result = pipeline.generate(summary)
    except StoryStageError as exc:
        # Không bao giờ dùng str(exc), exc.result, exc.attempts hay __cause__: có thể chứa raw output.
        category = sanitize_message(getattr(exc, "category", "không rõ"))
        logger.error("Bước tạo truyện thất bại (loại: %s)", category)
        return _error(
            f"Bước tạo truyện thất bại (loại: {category}). "
            "Chi tiết không được hiển thị để tránh lộ dữ liệu."
        )
    except PipelineContractError as exc:
        # Chỉ ghi thông điệp đã lọc, không ghi traceback (có thể chứa đường dẫn nội bộ).
        logger.error("Pipeline trả dữ liệu sai hợp đồng: %s", _describe(exc))
        return _error(f"Dữ liệu giữa các bước không hợp lệ ({sanitize_message(exc)}).")
    except Exception as exc:  # noqa: BLE001 - hiển thị lỗi (đã lọc) cho người dùng, không nuốt lỗi
        logger.error("Pipeline thất bại: %s", _describe(exc))
        return _error(f"Không tạo được truyện tranh ({_describe(exc)})")

    elapsed = time.perf_counter() - start
    try:
        _validate_result(result)
        return _format_result(result, elapsed)
    except _InvalidResult as exc:
        logger.error("Kết quả pipeline không đạt kiểm tra tối thiểu: %s", sanitize_message(exc))
        return _error(f"Kết quả pipeline không hợp lệ ({sanitize_message(exc)}).")
    except Exception as exc:  # noqa: BLE001
        logger.error("Không đọc được kết quả pipeline: %s", _describe(exc))
        return _error(f"Pipeline trả kết quả không đọc được ({_describe(exc)})")


def load_example_summary() -> str | None:
    """Lấy summary mẫu từ fixture chuẩn của nhóm để làm ví dụ bấm nhanh."""
    import json

    try:
        data = json.loads(EXAMPLE_STORYBOARD.read_text(encoding="utf-8"))
        summary = data["summary"]
    except (OSError, ValueError, KeyError, TypeError):
        return None
    return summary if isinstance(summary, str) else None


def create_demo(pipeline: PipelineLike, *, demo_mode: bool):
    """Dựng giao diện Gradio quanh một pipeline. Import gradio trễ để test CPU không cần gradio.

    demo_mode bắt buộc (keyword-only): người gọi phải quyết định có hiện biểu ngữ DEMO hay không.
    """
    import gradio as gr

    is_demo = bool(demo_mode)
    status_prefix = "[DEMO] " if is_demo else ""

    with gr.Blocks(title="AI Comic Generation (DEMO)" if is_demo else "AI Comic Generation") as demo:
        gr.Markdown(
            "# AI Comic Generation\n"
            "Nhập tóm tắt truyện bằng tiếng Việt, hệ thống tạo truyện tranh đúng 4 khung."
        )
        if is_demo:
            gr.Markdown(DEMO_BANNER)
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
            yield status_prefix + BUSY_MESSAGE, [], None, None, "", "", ""
            out = run_generation(pipeline, summary)
            yield (
                status_prefix + out.status,
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
# Chế độ demo: pipeline dùng chung của nhóm với backend mock
# ---------------------------------------------------------------------------
def build_demo_pipeline() -> tuple[ComicPipeline, PipelineConfig]:
    """Dựng pipeline dùng chung (src.factory.build_pipeline) với backend mock, ghi vào outputs/demo_ui.

    Không truyền image_backend nên factory dùng ảnh mock mặc định. Từ chối chạy nếu cấu hình mặc định
    không còn là story mock, để biểu ngữ DEMO không bao giờ nói sai.
    """
    config = PipelineConfig(output_dir=DEMO_OUTPUT_DIR)
    if config.story_backend != "mock":
        raise RuntimeError("Chế độ demo chỉ chạy với story backend mock.")
    return build_pipeline(config), config


def launch_kwargs(port: int, output_root: Path) -> dict[str, Any]:
    """Tham số launch của chế độ demo: chỉ cho phép phục vụ file trong thư mục output của demo."""
    return {"server_port": port, "allowed_paths": [str(Path(output_root).resolve())]}


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Gradio UI cho AI Comic Generation")
    parser.add_argument("--demo", action="store_true", help="dùng pipeline dùng chung với backend mock")
    parser.add_argument("--port", type=int, default=7860)
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if not args.demo:
        raise SystemExit(
            "Chưa có cấu hình pipeline thật cho UI (chờ TV1 tích hợp). "
            "Dùng `python app.py --demo` để chạy với backend mock."
        )

    pipeline, config = build_demo_pipeline()
    demo = create_demo(pipeline, demo_mode=True)
    Path(config.output_root).mkdir(parents=True, exist_ok=True)
    demo.launch(**launch_kwargs(args.port, config.output_root))


if __name__ == "__main__":
    main()