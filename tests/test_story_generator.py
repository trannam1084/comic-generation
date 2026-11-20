"""Kiểm thử Mock Story Generator trên CPU, không model/API hoặc auto repair."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys

import pytest
from pydantic import ValidationError

from src.story_generator.backend import StoryBackend
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.story_generator import (
    StoryBackendError,
    StoryGenerator,
    StoryInputError,
    StoryOutputError,
)
from src.storyboard.schema import Storyboard


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "storyboard.json"


@pytest.fixture
def payload():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


class FakeBackend:
    """Fake nhỏ không kế thừa Protocol; ghi lại calls để phát hiện retry."""

    def __init__(self, output=None, error=None):
        self.output = output
        self.error = error
        self.calls = []

    def generate(self, summary: str) -> str:
        self.calls.append(summary)
        if self.error is not None:
            raise self.error
        return self.output


def test_mock_returns_original_raw_json(payload):
    backend: StoryBackend = MockStoryBackend()
    raw = backend.generate(payload["summary"])
    assert isinstance(raw, str)
    assert raw == FIXTURE.read_text(encoding="utf-8")
    assert json.loads(raw) == payload


def test_generator_returns_valid_storyboard_and_preserves_all_content(payload):
    original = deepcopy(payload)
    result = StoryGenerator(MockStoryBackend()).generate(payload["summary"])
    assert isinstance(result, Storyboard)
    assert len(result.scenes) == 4
    assert result.model_dump() == original
    assert payload == original


def test_same_input_is_deterministic_and_results_do_not_share_mutation(payload):
    backend = MockStoryBackend()
    generator = StoryGenerator(backend)
    first = generator.generate(payload["summary"])
    second = generator.generate(payload["summary"])
    assert first == second
    assert backend.generate(payload["summary"]) == backend.generate(payload["summary"])
    first.scenes[0].caption_vi = "Đã thay đổi ở caller."
    assert second.model_dump() == payload
    assert generator.generate(payload["summary"]).model_dump() == payload


@pytest.mark.parametrize("summary", ["", " \t\n", "\u2003", None, 123, True, [], {}, b"story"])
def test_invalid_input_is_rejected_without_backend_call(summary):
    backend = FakeBackend(error=AssertionError("Backend không được gọi"))
    with pytest.raises(StoryInputError):
        StoryGenerator(backend).generate(summary)
    assert backend.calls == []


@pytest.mark.parametrize("transform", [lambda s: "Truyện khác.", lambda s: " " + s, lambda s: s + "\n"])
def test_mock_rejects_unsupported_or_normalized_summary(payload, transform):
    summary = transform(payload["summary"])
    backend = MockStoryBackend()
    with pytest.raises(ValueError, match="fixture"):
        backend.generate(summary)
    with pytest.raises(StoryBackendError) as caught:
        StoryGenerator(backend).generate(summary)
    assert isinstance(caught.value.__cause__, ValueError)
    assert not isinstance(caught.value.__cause__, ValidationError)


def test_custom_fixture_path_and_default_path_work_from_other_cwd(payload, tmp_path, monkeypatch):
    custom = deepcopy(payload)
    custom["summary"] = "Summary riêng của test."
    fixture_path = tmp_path / "custom.json"
    raw = json.dumps(custom, ensure_ascii=False)
    fixture_path.write_text(raw, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert MockStoryBackend(fixture_path).generate(custom["summary"]) == raw
    assert MockStoryBackend().generate(payload["summary"]) == FIXTURE.read_text(encoding="utf-8")


def test_mock_holds_fixture_snapshot(payload, tmp_path):
    fixture_path = tmp_path / "snapshot.json"
    raw = json.dumps(payload, ensure_ascii=False)
    fixture_path.write_text(raw, encoding="utf-8")
    backend = MockStoryBackend(fixture_path)
    fixture_path.write_text("broken JSON", encoding="utf-8")
    assert backend.generate(payload["summary"]) == raw


def test_missing_fixture_reports_original_file_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        MockStoryBackend(tmp_path / "missing.json")


@pytest.mark.parametrize("fixture_kind", ["malformed", "three_scenes", "missing_summary"])
def test_invalid_fixture_fails_at_initialization(payload, tmp_path, fixture_kind):
    if fixture_kind == "malformed":
        raw = "{"
    else:
        if fixture_kind == "three_scenes":
            payload["scenes"].pop()
        else:
            del payload["summary"]
        raw = json.dumps(payload, ensure_ascii=False)
    fixture_path = tmp_path / "invalid.json"
    fixture_path.write_text(raw, encoding="utf-8")
    with pytest.raises(ValidationError):
        MockStoryBackend(fixture_path)


@pytest.mark.parametrize(
    "case,location,error_type",
    [
        ("malformed", (), "json_invalid"),
        ("three_scenes", ("scenes",), "too_short"),
        ("string_index", ("scenes", 0, "index"), "int_type"),
        ("unknown_reference", (), "value_error"),
    ],
)
def test_invalid_backend_json_preserves_validation_cause_and_does_not_retry(
    payload, case, location, error_type
):
    if case == "malformed":
        raw = "{"
    else:
        if case == "three_scenes":
            payload["scenes"].pop()
        elif case == "string_index":
            payload["scenes"][0]["index"] = "1"
        else:
            payload["scenes"][0]["characters"] = ["unknown"]
        raw = json.dumps(payload, ensure_ascii=False)
    backend = FakeBackend(output=raw)
    with pytest.raises(StoryOutputError) as caught:
        StoryGenerator(backend).generate(payload["summary"])
    assert backend.calls == [payload["summary"]]
    assert caught.value.raw_output is raw
    cause = caught.value.__cause__
    assert isinstance(cause, ValidationError)
    assert cause.errors()[0]["loc"] == location
    assert cause.errors()[0]["type"] == error_type


@pytest.mark.parametrize("transform", [lambda s: "Khác input.", lambda s: s + " "])
def test_different_output_summary_is_rejected_without_overwrite(payload, transform):
    summary = payload["summary"]
    payload["summary"] = transform(summary)
    raw = json.dumps(payload, ensure_ascii=False)
    backend = FakeBackend(output=raw)
    with pytest.raises(StoryOutputError, match="Summary") as caught:
        StoryGenerator(backend).generate(summary)
    assert backend.calls == [summary]
    assert caught.value.raw_output == raw
    assert json.loads(caught.value.raw_output)["summary"] == payload["summary"]


def test_backend_exception_keeps_original_cause_and_never_falls_back(payload):
    original = RuntimeError("Fake backend failure")
    backend = FakeBackend(error=original)
    with pytest.raises(StoryBackendError) as caught:
        StoryGenerator(backend).generate(payload["summary"])
    assert caught.value.__cause__ is original
    assert backend.calls == [payload["summary"]]


@pytest.mark.parametrize("raw", [None, 123, True, {}, [], b"{}"])
def test_wrong_output_type_is_rejected_without_coercion(payload, raw):
    backend = FakeBackend(output=raw)
    with pytest.raises(StoryOutputError, match="str") as caught:
        StoryGenerator(backend).generate(payload["summary"])
    assert caught.value.raw_output is raw
    assert backend.calls == [payload["summary"]]


def test_dependency_injection_uses_only_supplied_backend_once(payload):
    payload["summary"] = "Summary do backend được inject hỗ trợ."
    backend: StoryBackend = FakeBackend(output=json.dumps(payload, ensure_ascii=False))
    result = StoryGenerator(backend).generate(payload["summary"])
    assert result.model_dump() == payload
    assert backend.calls == [payload["summary"]]


def test_import_and_generation_work_without_gpu_packages_or_network(tmp_path):
    # Process mới tránh false PASS do modules đã nằm trong sys.modules của pytest.
    script = '''
import builtins
import json
from pathlib import Path
import sys

sys.path.insert(0, sys.argv[1])
original_import = builtins.__import__
blocked = {"torch", "transformers", "diffusers", "accelerate", "huggingface_hub",
           "requests", "httpx"}
def guarded_import(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise AssertionError("Unexpected import: " + name)
    return original_import(name, *args, **kwargs)
builtins.__import__ = guarded_import

# Cho phép import standard library socket qua Pydantic/importlib.metadata,
# nhưng chặn sử dụng socket hoặc gửi urllib request thật.
def deny_network(event, args):
    if event.startswith("socket.") or event == "urllib.Request":
        raise AssertionError("Unexpected network operation: " + event)
sys.addaudithook(deny_network)

from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.story_generator import StoryGenerator
fixture = Path(sys.argv[1]) / "examples" / "storyboard.json"
summary = json.loads(fixture.read_text(encoding="utf-8"))["summary"]
result = StoryGenerator(MockStoryBackend()).generate(summary)
assert len(result.scenes) == 4
assert not blocked.intersection(sys.modules)
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(ROOT)],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
