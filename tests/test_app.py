import dataclasses
import json
import logging
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from PIL import Image

import app
from app import _DemoPipeline, load_example_summary, run_generation, sanitize_message
from src.pipeline import PipelineContractError

SUMMARY = load_example_summary()


class SpyPipeline:
    """Giả lập ComicPipeline: ghi lại input, trả kết quả hoặc ném lỗi đã chọn."""

    def __init__(self, result=None, error=None):
        self.result = result
        self.error = error
        self.calls = []

    def generate(self, summary):
        self.calls.append(summary)
        if self.error is not None:
            raise self.error
        return self.result


@pytest.fixture
def result(tmp_path):
    return _DemoPipeline(tmp_path).generate(SUMMARY)


def test_example_summary_available():
    assert isinstance(SUMMARY, str) and SUMMARY.strip()


def test_success_formats_all_outputs(result):
    out = run_generation(SpyPipeline(result), SUMMARY)
    assert out.ok
    assert len(out.gallery) == 4
    captions = [caption for _, caption in out.gallery]
    expected = [f"Cảnh {s.index}: {s.caption_vi}" for s in result.storyboard.scenes]
    assert captions == expected
    assert all(isinstance(image, Image.Image) for image, _ in out.gallery)
    assert Path(out.comic_path).is_file()
    assert json.loads(out.storyboard_json) == result.storyboard.model_dump()
    for i in range(1, 5):
        assert f"[Cảnh {i}]" in out.prompts_text
    assert out.run_info.count("backend=mock") == 4
    assert "Tổng thời gian" in out.run_info
    assert "Hoàn thành" in out.status


@pytest.mark.parametrize("blank", ["", "   ", "\n\t", None, 123])
def test_blank_summary_is_rejected_without_calling_pipeline(blank, result):
    spy = SpyPipeline(result)
    out = run_generation(spy, blank)
    assert not out.ok and out.status.startswith("LỖI")
    assert out.gallery == [] and out.comic_path is None
    assert spy.calls == []


def test_summary_is_passed_verbatim_to_pipeline(result):
    raw = "  " + SUMMARY + "\n"
    spy = SpyPipeline(result)
    run_generation(spy, raw)
    assert spy.calls == [raw]


def test_contract_error_is_reported_with_stage():
    spy = SpyPipeline(error=PipelineContractError("images", "Cần list có đúng bốn phần tử."))
    out = run_generation(spy, SUMMARY)
    assert not out.ok
    assert "images" in out.status and "không hợp lệ" in out.status
    assert out.comic_path is None


@pytest.mark.parametrize("error", [ValueError("sai dữ liệu"), RuntimeError("hết VRAM"), KeyError("x")])
def test_backend_failure_shows_real_error_and_no_fake_output(error):
    out = run_generation(SpyPipeline(error=error), SUMMARY)
    assert not out.ok
    assert type(error).__name__ in out.status
    assert out.gallery == [] and out.comic_path is None
    assert out.storyboard_json == "" and out.prompts_text == ""


def test_demo_pipeline_rejects_other_summary(tmp_path):
    out = run_generation(_DemoPipeline(tmp_path), "Một câu chuyện khác hẳn.")
    assert not out.ok and "demo" in out.status.lower()


def test_demo_pipeline_end_to_end(tmp_path):
    out = run_generation(_DemoPipeline(tmp_path), SUMMARY)
    assert out.ok
    with Image.open(out.comic_path) as comic:
        assert comic.format == "PNG"
        assert comic.size == (1060, 1320)


def test_main_without_demo_refuses_to_start():
    with pytest.raises(SystemExit):
        app.main([])


# ---------- Review #27, mục 1: thư mục demo không bao giờ bị ghi đè ----------

def test_two_demo_runs_in_same_second_use_different_directories(tmp_path, monkeypatch):
    monkeypatch.setattr(app.time, "strftime", lambda fmt: "run_FIXED_TIMESTAMP")
    pipeline = _DemoPipeline(tmp_path)

    first = pipeline.generate(SUMMARY)
    first_bytes = first.comic_path.read_bytes()
    second = pipeline.generate(SUMMARY)

    assert first.comic_path != second.comic_path
    assert first.comic_path.parent != second.comic_path.parent
    assert first.comic_path.is_file() and second.comic_path.is_file()
    assert first.comic_path.read_bytes() == first_bytes  # lượt đầu còn nguyên


def test_existing_run_directory_is_never_overwritten(tmp_path, monkeypatch):
    monkeypatch.setattr(app.time, "strftime", lambda fmt: "run_FIXED_TIMESTAMP")
    monkeypatch.setattr(app.uuid, "uuid4", lambda: uuid.UUID(int=1))
    pipeline = _DemoPipeline(tmp_path)

    first = pipeline.generate(SUMMARY)
    first_bytes = first.comic_path.read_bytes()
    with pytest.raises(FileExistsError):
        pipeline.generate(SUMMARY)
    assert first.comic_path.read_bytes() == first_bytes


# ---------- Review #27, mục 2: allowed_paths chỉ gồm outputs/demo_ui ----------

def test_launch_allows_only_demo_output_directory():
    kwargs = app.launch_kwargs(7860)
    assert kwargs["allowed_paths"] == [str(app.DEMO_OUTPUT_DIR)]
    assert str(app.OUTPUT_DIR) not in kwargs["allowed_paths"]
    assert app.DEMO_OUTPUT_DIR.parent == app.OUTPUT_DIR


# ---------- Review #27, mục 3: không đưa chi tiết nhạy cảm lên UI hoặc log ----------

LEAKY_ERRORS = [
    (FileNotFoundError(r"Không tìm thấy font: C:\Users\hoang\Desktop\secret_project\NotoSans.ttf"), ["hoang", "secret_project", "C:\\"]),
    (RuntimeError("không ghi được /kaggle/working/private_run/comic.png"), ["private_run", "/kaggle"]),
    (RuntimeError("401 khi gọi https://huggingface.co/api/models?token=hf_abcdefgh12345678"), ["hf_abcdefgh", "huggingface.co"]),
    (RuntimeError("Authorization: Bearer abc.def.ghi-SECRETVALUE"), ["SECRETVALUE", "abc.def"]),
    (RuntimeError("cấu hình sai api_key=TOPSECRET123456 và password: hunter2pass"), ["TOPSECRET", "hunter2pass"]),
    (ValueError("UNC \\\\fileserver\\share\\private\\data.bin bị lỗi"), ["fileserver", "private"]),
]


@pytest.mark.parametrize("error,secrets", LEAKY_ERRORS)
def test_backend_error_is_sanitized_in_ui_and_logs(error, secrets, caplog):
    with caplog.at_level(logging.DEBUG):
        out = run_generation(SpyPipeline(error=error), SUMMARY)
    assert not out.ok and type(error).__name__ in out.status
    for secret in secrets:
        assert secret not in out.status
        assert secret not in caplog.text
    assert all(record.exc_info is None for record in caplog.records)  # không ghi traceback thô


def test_contract_error_message_is_sanitized(caplog):
    error = PipelineContractError("render", r"Lỗi ở C:\Users\hoang\x.png token=abc12345")
    with caplog.at_level(logging.DEBUG):
        out = run_generation(SpyPipeline(error=error), SUMMARY)
    assert "hoang" not in out.status and "abc12345" not in out.status
    assert "hoang" not in caplog.text and "abc12345" not in caplog.text


def test_sanitize_keeps_ordinary_messages_and_truncates():
    plain = "Chế độ demo chỉ hỗ trợ đúng tóm tắt mẫu (bấm ví dụ bên dưới ô nhập)."
    assert sanitize_message(plain) == plain
    long = "lỗi " * 500
    assert len(sanitize_message(long)) <= app.MAX_ERROR_CHARS + 1
    assert "\n" not in sanitize_message("a\nb\n\nc")


def test_sanitize_error_with_empty_message_still_names_type():
    out = run_generation(SpyPipeline(error=RuntimeError()), SUMMARY)
    assert "RuntimeError" in out.status


# ---------- Review #27, mục 5: kiểm tra tối thiểu trước khi báo thành công ----------

def test_missing_comic_file_is_not_success(result):
    bad = dataclasses.replace(result, comic_path=result.comic_path.parent / "khong_ton_tai.png")
    out = run_generation(SpyPipeline(bad), SUMMARY)
    assert not out.ok and "comic_path" in out.status and out.gallery == []
    assert "khong_ton_tai" not in out.status  # không lộ đường dẫn


def test_empty_comic_file_is_not_success(result, tmp_path):
    empty = tmp_path / "empty.png"
    empty.write_bytes(b"")
    out = run_generation(SpyPipeline(dataclasses.replace(result, comic_path=empty)), SUMMARY)
    assert not out.ok and "comic_path" in out.status


def test_directory_as_comic_path_is_not_success(result, tmp_path):
    out = run_generation(SpyPipeline(dataclasses.replace(result, comic_path=tmp_path)), SUMMARY)
    assert not out.ok


@pytest.mark.parametrize("count", [0, 3, 5])
def test_wrong_number_of_images_is_not_success(result, count):
    images = (list(result.images) * 2)[:count]
    out = run_generation(SpyPipeline(dataclasses.replace(result, images=images)), SUMMARY)
    assert not out.ok and "images" in out.status and out.comic_path is None


@pytest.mark.parametrize("count", [0, 3, 5])
def test_wrong_number_of_prompts_is_not_success(result, count):
    prompts = (list(result.prompts) * 2)[:count]
    out = run_generation(SpyPipeline(dataclasses.replace(result, prompts=prompts)), SUMMARY)
    assert not out.ok and "prompts" in out.status


def test_non_list_images_is_not_success(result):
    out = run_generation(SpyPipeline(dataclasses.replace(result, images=None)), SUMMARY)
    assert not out.ok and "images" in out.status


def test_result_without_expected_fields_is_not_success():
    out = run_generation(SpyPipeline(object()), SUMMARY)
    assert not out.ok and "không hợp lệ" in out.status


def test_unreadable_but_complete_result_is_reported(result):
    broken = SimpleNamespace(
        comic_path=result.comic_path,
        images=result.images,
        prompts=result.prompts,
        storyboard=SimpleNamespace(scenes=[1, 2, 3, 4]),
    )
    out = run_generation(SpyPipeline(broken), SUMMARY)
    assert not out.ok and "không đọc được" in out.status


# ---------- Review #27, mục 4: biểu ngữ DEMO MODE ----------

def _markdown_texts(demo):
    return [str(getattr(block, "value", "")) for block in demo.blocks.values()
            if type(block).__name__ == "Markdown"]


def test_gradio_interface_builds_and_shows_demo_banner(tmp_path):
    gr = pytest.importorskip("gradio")
    demo = app.create_demo(_DemoPipeline(tmp_path))
    assert isinstance(demo, gr.Blocks)
    assert any("CHẾ ĐỘ DEMO" in text for text in _markdown_texts(demo))
    assert "DEMO" in (demo.title or "")


def test_gradio_interface_has_no_demo_banner_for_other_pipelines(result):
    pytest.importorskip("gradio")
    demo = app.create_demo(SpyPipeline(result))
    assert not any("CHẾ ĐỘ DEMO" in text for text in _markdown_texts(demo))