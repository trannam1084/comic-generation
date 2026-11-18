"""Fakes xác nhận wiring/API trên CPU, không chứng minh Qwen inference thật."""

from contextlib import contextmanager
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.story_generator.backend import StoryBackend
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.prompts import PROMPT_VERSION
from src.story_generator.qwen_backend import MODEL_ID, MODEL_REVISION, QwenStoryBackend
from src.story_generator.story_generator import StoryBackendError, StoryGenerator, StoryOutputError


ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network operation forbidden in CPU unit tests")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    for method in ["connect", "connect_ex", "sendto"]:
        monkeypatch.setattr(socket.socket, method, forbidden)


class FakeTokens:
    def __init__(self, values):
        self.values = list(values)

    def numel(self):
        return len(self.values)


class FakeTensor:
    def __init__(self, rows):
        self.rows = rows
        self.shape = (len(rows), len(rows[0]))

    def __getitem__(self, key):
        row, columns = key
        return FakeTokens(self.rows[row][columns])


class FakeBatch(dict):
    def __init__(self):
        super().__init__(input_ids=FakeTensor([[10, 11, 12]]), attention_mask=FakeTensor([[1, 1, 1]]))
        self.devices = []

    def to(self, device):
        self.devices.append(device)
        return self


class FakeRuntime:
    def __init__(self):
        self.active = False
        self.context_entries = 0

    @contextmanager
    def inference_mode(self):
        self.context_entries += 1
        self.active = True
        try:
            yield
        finally:
            self.active = False


class FakeTokenizer:
    eos_token_id = 999

    def __init__(self, raw):
        self.raw = raw
        self.chat_calls = []
        self.token_calls = []
        self.decode_calls = []
        self.batch = FakeBatch()

    def apply_chat_template(self, messages, **kwargs):
        self.chat_calls.append((messages, kwargs))
        return "fake rendered chat"

    def __call__(self, text, **kwargs):
        self.token_calls.append((text, kwargs))
        return self.batch

    def decode(self, tokens, **kwargs):
        self.decode_calls.append((tokens.values, kwargs))
        return self.raw


class FakeModel:
    def __init__(self, runtime):
        self.runtime = runtime
        self.devices = []
        self.eval_calls = 0
        self.calls = []
        self.error = None

    def to(self, device):
        self.devices.append(device)
        return self

    def eval(self):
        self.eval_calls += 1
        return self

    def generate(self, **kwargs):
        assert self.runtime.active, "generate must run inside inference_mode"
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        # Chỉ là IDs tổng hợp cho slicing tests, không phải tokens của Qwen.
        continuation = [901, 902, 903][:kwargs["max_new_tokens"]]
        return FakeTensor([kwargs["input_ids"].rows[0] + continuation])


@pytest.fixture
def rig():
    payload = json.loads((ROOT / "examples/storyboard.json").read_text(encoding="utf-8"))
    runtime = FakeRuntime()
    tokenizer = FakeTokenizer(json.dumps(payload, ensure_ascii=False))
    model = FakeModel(runtime)
    load_calls = []

    def loader(**kwargs):
        load_calls.append(kwargs)
        return tokenizer, model, runtime

    return SimpleNamespace(payload=payload, runtime=runtime, tokenizer=tokenizer,
                           model=model, loader=loader, load_calls=load_calls)


def test_lazy_load_chat_template_and_pinned_configuration(rig):
    backend: StoryBackend = QwenStoryBackend(loader=rig.loader)
    assert rig.load_calls == [] and backend.last_run is None
    raw = backend.generate(rig.payload["summary"])
    assert raw == rig.tokenizer.raw
    assert rig.load_calls == [{"model_id": MODEL_ID, "revision": MODEL_REVISION,
                               "device": "cuda:0", "cache_dir": None}]
    assert rig.model.devices == ["cuda:0"] and rig.model.eval_calls == 1
    messages, options = rig.tokenizer.chat_calls[0]
    assert options == {"tokenize": False, "add_generation_prompt": True}
    assert [m["role"] for m in messages] == ["system", "user"]
    assert json.loads(messages[1]["content"])["summary"] == rig.payload["summary"]
    assert rig.tokenizer.token_calls == [("fake rendered chat", {"return_tensors": "pt", "add_special_tokens": False})]
    assert rig.tokenizer.batch.devices == ["cuda:0"]
    kwargs = rig.model.calls[0]
    assert kwargs["do_sample"] is False and kwargs["max_new_tokens"] == 1024
    assert kwargs["num_beams"] == kwargs["num_return_sequences"] == 1
    assert kwargs["pad_token_id"] == rig.tokenizer.eos_token_id
    assert "device_map" not in kwargs and "temperature" not in kwargs
    assert rig.runtime.context_entries == 1 and not rig.runtime.active


def test_default_loader_pins_both_hf_loaders_without_auto_placement(rig, monkeypatch):
    token_calls, model_calls = [], []
    runtime = rig.runtime
    runtime.float16 = object()
    runtime.cuda = SimpleNamespace(is_available=lambda: True, device_count=lambda: 1)

    def tokenizer_load(*args, **kwargs):
        token_calls.append((args, kwargs))
        return rig.tokenizer

    def model_load(*args, **kwargs):
        model_calls.append((args, kwargs))
        return rig.model

    monkeypatch.setitem(sys.modules, "torch", runtime)
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=tokenizer_load),
        AutoModelForCausalLM=SimpleNamespace(from_pretrained=model_load),
    ))
    backend = QwenStoryBackend(cache_dir="/test/cache")
    backend.load()
    backend.load()
    assert len(token_calls) == len(model_calls) == 1
    for calls in [token_calls, model_calls]:
        args, kwargs = calls[0]
        assert args == (MODEL_ID,)
        assert kwargs["revision"] == MODEL_REVISION
        assert kwargs["trust_remote_code"] is False
        assert kwargs["cache_dir"] == "/test/cache"
        assert "device_map" not in kwargs and "quantization_config" not in kwargs
    assert model_calls[0][1]["dtype"] is runtime.float16
    assert model_calls[0][1]["use_safetensors"] is True


def test_unavailable_gpu_fails_before_tokenizer_or_weights_load(monkeypatch):
    monkeypatch.setitem(sys.modules, "torch", SimpleNamespace(
        cuda=SimpleNamespace(is_available=lambda: False, device_count=lambda: 0)))
    with pytest.raises(RuntimeError, match="không khả dụng"):
        QwenStoryBackend().load()


def test_decode_only_continuation_preserves_raw_output(rig):
    rig.tokenizer.raw = "  ```json\n{not repaired}\n```\n  "
    backend = QwenStoryBackend(loader=rig.loader)
    assert backend.generate(rig.payload["summary"]) == rig.tokenizer.raw
    assert rig.tokenizer.decode_calls == [
        ([901, 902, 903], {"skip_special_tokens": True, "clean_up_tokenization_spaces": False})
    ]
    assert backend.last_run["raw_output"] == rig.tokenizer.raw


def test_model_loads_once_and_each_generate_calls_model_once(rig):
    backend = QwenStoryBackend(loader=rig.loader)
    backend.load()
    backend.generate(rig.payload["summary"])
    backend.generate(rig.payload["summary"])
    assert len(rig.load_calls) == rig.model.eval_calls == 1
    assert len(rig.model.calls) == 2


def test_token_budget_and_metadata_do_not_claim_real_fake_performance(rig):
    rig.model.generation_config = SimpleNamespace(to_dict=lambda: {"do_sample": True, "eos_token_id": [999]})
    backend = QwenStoryBackend(loader=rig.loader, max_new_tokens=2, repetition_penalty=1.1)
    backend.generate(rig.payload["summary"])
    metadata = backend.last_run
    assert rig.model.calls[0]["max_new_tokens"] == 2
    assert rig.model.calls[0]["repetition_penalty"] == 1.1
    assert rig.tokenizer.decode_calls[0][0] == [901, 902]
    assert metadata["input_tokens"] == 3 and metadata["generated_tokens"] == 2
    assert metadata["hit_max_new_tokens"] is True
    assert metadata["execution_mode"] == "injected"
    assert metadata["generation_latency_seconds"] is None
    assert metadata["peak_allocated_vram_bytes"] is None and metadata["gpu_model"] is None
    assert metadata["validation_outcome"] == "not_checked"
    assert metadata["prompt_version"] == PROMPT_VERSION
    assert metadata["model_generation_config"] == {"do_sample": True, "eos_token_id": [999]}
    assert metadata["generation_parameters"]["do_sample"] is False  # Override baseline rõ ràng.
    assert metadata["model_id"] == MODEL_ID and metadata["revision"] == MODEL_REVISION
    assert len(metadata["prompt_sha256"]) == 64
    json.dumps(metadata)  # Có thể lưu manifest, không chứa tensor/model objects.
    metadata["generation_parameters"]["max_new_tokens"] = 999
    assert backend.last_run["generation_parameters"]["max_new_tokens"] == 2


def test_shorter_generation_does_not_report_budget_hit(rig):
    backend = QwenStoryBackend(loader=rig.loader)
    backend.generate(rig.payload["summary"])
    assert backend.last_run["hit_max_new_tokens"] is False


def test_backend_is_compatible_with_existing_story_generator(rig):
    backend = QwenStoryBackend(loader=rig.loader)
    assert StoryGenerator(backend).generate(rig.payload["summary"]).model_dump() == rig.payload
    assert len(rig.model.calls) == 1
    # Backend không parse, nên outcome của lớp StoryGenerator chưa tự ghi vào metadata.
    assert backend.last_run["validation_outcome"] == "not_checked"


@pytest.mark.parametrize("raw", ["{", "```json\n{}\n```", "not JSON"])
def test_invalid_json_goes_through_story_output_error_without_retry(rig, raw):
    rig.tokenizer.raw = raw
    backend = QwenStoryBackend(loader=rig.loader)
    with pytest.raises(StoryOutputError) as caught:
        StoryGenerator(backend).generate(rig.payload["summary"])
    assert isinstance(caught.value.__cause__, ValidationError)
    assert caught.value.raw_output == raw == backend.last_run["raw_output"]
    assert len(rig.model.calls) == 1
    assert backend.last_run["error_category"] is None


def test_generation_failure_keeps_cause_and_does_not_fallback(rig):
    failure = RuntimeError("fake generation failure")
    rig.model.error = failure
    backend = QwenStoryBackend(loader=rig.loader)
    with pytest.raises(StoryBackendError) as caught:
        StoryGenerator(backend).generate(rig.payload["summary"])
    assert caught.value.__cause__ is failure
    assert len(rig.load_calls) == len(rig.model.calls) == 1
    assert backend.last_run["error_category"] == "generation_error"
    assert backend.last_run["raw_output"] is None
    assert not rig.runtime.active


def test_load_failure_does_not_retry_within_generate(rig):
    failure = OSError("fake load failure")
    calls = []

    def fail(**kwargs):
        calls.append(kwargs)
        raise failure

    backend = QwenStoryBackend(loader=fail)
    with pytest.raises(OSError) as caught:
        backend.generate(rig.payload["summary"])
    assert caught.value is failure and len(calls) == 1
    assert backend.last_run["error_category"] == "load_error"
    assert rig.model.calls == []


@pytest.mark.parametrize("summary", ["", " \n", None, 123])
def test_invalid_input_does_not_load_model(rig, summary):
    backend = QwenStoryBackend(loader=rig.loader)
    with pytest.raises(ValueError):
        backend.generate(summary)
    assert rig.load_calls == []
    assert backend.last_run["error_category"] == "input_error"


@pytest.mark.parametrize("parameters", [
    {"max_new_tokens": 0}, {"max_new_tokens": True}, {"max_new_tokens": "1024"},
    {"repetition_penalty": 0}, {"repetition_penalty": float("nan")},
    {"device": "auto"}, {"device": "cpu"}, {"device": "cuda"},
])
def test_invalid_configuration_rejected_before_loading(parameters):
    with pytest.raises(ValueError):
        QwenStoryBackend(**parameters)


def test_mock_still_works_without_inference_dependencies(rig):
    result = StoryGenerator(MockStoryBackend()).generate(rig.payload["summary"])
    assert result.model_dump() == rig.payload


def test_import_and_constructor_are_offline_without_gpu_packages(tmp_path):
    script = '''
import builtins, sys
sys.path.insert(0, sys.argv[1])
original_import = builtins.__import__
blocked = {"torch", "transformers", "diffusers", "accelerate", "huggingface_hub", "requests", "httpx"}
def guarded(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise AssertionError("Unexpected import/load: " + name)
    return original_import(name, *args, **kwargs)
def no_network(event, args):
    if event.startswith("socket.") or event == "urllib.Request":
        raise AssertionError("Unexpected network operation: " + event)
builtins.__import__ = guarded
sys.addaudithook(no_network)
from src.story_generator.qwen_backend import QwenStoryBackend
backend = QwenStoryBackend()
assert backend.last_run is None
assert not blocked.intersection(sys.modules)
'''
    result = subprocess.run([sys.executable, "-B", "-c", script, str(ROOT)], cwd=tmp_path,
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stdout + result.stderr
