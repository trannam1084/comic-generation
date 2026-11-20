import json
from pathlib import Path

import pytest
from PIL import Image

import app
from app import UIOutput, _DemoPipeline, load_example_summary, run_generation
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


def test_unreadable_result_is_reported():
    out = run_generation(SpyPipeline(result=object()), SUMMARY)
    assert not out.ok and "không đọc được" in out.status


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


def test_gradio_interface_builds(result):
    gr = pytest.importorskip("gradio")
    demo = app.create_demo(SpyPipeline(result))
    assert isinstance(demo, gr.Blocks)