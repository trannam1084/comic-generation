"""CPU injected doubles chỉ chứng minh wiring, không Qwen repair effectiveness."""

from copy import deepcopy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys
from types import SimpleNamespace

import pytest

# Tái sử dụng tensor/tokenizer/runtime doubles đã có; không sửa tests baseline.
from test_qwen_backend import FakeModel, FakeRuntime, FakeTokenizer
from src.story_generator.prompts import PROMPT_VERSION, build_story_messages
from src.story_generator.qwen_backend import MODEL_ID, MODEL_REVISION, QwenStoryBackend
from src.story_generator.repair import BoundedRepairController, RepairFeedback
from src.story_generator.repair_prompts import REPAIR_PROMPT_VERSION, build_repair_messages
from src.storyboard.schema import Storyboard
from src.storyboard.semantic_prompts import (
    EVIDENCE_FIRST_PROMPT_VERSION, SEMANTIC_PROMPT_VERSION, build_semantic_messages,
)
from src.storyboard.validator import ValidationIssue


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def forbidden(*args, **kwargs):
        raise AssertionError("Network forbidden in injected CPU tests")
    monkeypatch.setattr(socket, "getaddrinfo", forbidden)
    for method in ["connect", "connect_ex", "sendto"]:
        monkeypatch.setattr(socket.socket, method, forbidden)


@pytest.fixture
def payload():
    # Synthetic orchestration fixture, không historical pilot hay official dataset.
    return {
        "summary": "Một người trồng cây, tưới nước và thu hoạch.", "characters": [],
        "scenes": [
            {"index": i, "caption_vi": f"Cảnh tổng hợp {i}.",
             "image_prompt_en": f"Synthetic scene {i}.", "characters": []}
            for i in range(1, 5)
        ],
    }


def encode(payload):
    return json.dumps(payload, ensure_ascii=False)


def feedback(summary="Một người trồng cây.", index=1, previous="{broken"):
    return RepairFeedback(original_summary=summary, previous_raw_output=previous, attempt_index=index,
                          errors=[ValidationIssue(code="INVALID_JSON", severity="error", location=(),
                                                  message="Invalid JSON.", evidence={"decoder": "synthetic"})])


class ScriptedModel(FakeModel):
    def __init__(self, runtime, tokenizer, outputs):
        super().__init__(runtime)
        self.tokenizer = tokenizer
        self.outputs = list(outputs)

    def generate(self, **kwargs):
        tokens = super().generate(**kwargs)
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        self.tokenizer.raw = output
        return tokens


@pytest.fixture
def factory():
    def make(*outputs):
        runtime = FakeRuntime()
        tokenizer = FakeTokenizer(None)
        model = ScriptedModel(runtime, tokenizer, outputs)
        load_calls = []

        def loader(**kwargs):
            load_calls.append(kwargs)
            return tokenizer, model, runtime

        return SimpleNamespace(runtime=runtime, tokenizer=tokenizer, model=model, load_calls=load_calls,
                               backend=QwenStoryBackend(loader=loader), loader=loader)
    return make


def message_hash(messages):
    return hashlib.sha256(json.dumps(messages, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def test_raw_continuation_and_repair_metadata(factory):
    raw = " \n```json\n{still broken}\n```\n "
    rig = factory(raw)
    f = feedback()
    assert rig.backend.last_repair is None and not rig.load_calls
    assert rig.backend.generate_repair(f) == raw
    assert len(rig.model.calls) == 1 and len(rig.load_calls) == 1
    assert rig.tokenizer.decode_calls == [([901, 902, 903], {
        "skip_special_tokens": True, "clean_up_tokenization_spaces": False,
    })]
    meta = rig.backend.last_repair
    assert meta["purpose"] == "story_repair" and meta["prompt_version"] == REPAIR_PROMPT_VERSION
    assert meta["messages"] == build_repair_messages(f)
    assert meta["prompt_sha256"] == message_hash(meta["messages"])
    assert meta["raw_output"] == raw and meta["validation_outcome"] == "not_checked"
    assert meta["model_id"] == MODEL_ID and meta["revision"] == MODEL_REVISION
    assert meta["execution_mode"] == "injected" and meta["call_id"]
    assert meta["device"] == "cuda:0" and meta["precision"] == "float16" and meta["batch_size"] == 1
    assert meta["input_tokens"] == meta["generated_tokens"] == 3  # Synthetic IDs, không Qwen token metrics.
    assert meta["generation_latency_seconds"] is meta["peak_allocated_vram_bytes"] is meta["gpu_model"] is None
    assert meta["error_category"] is None and meta["hit_max_new_tokens"] is False
    assert meta["package_versions"]["python"]
    assert rig.backend.last_run is rig.backend.last_review is None
    json.dumps(meta, ensure_ascii=False, allow_nan=False).encode("utf-8")


def test_initial_and_two_repairs_share_one_load_and_unchanged_defaults(factory, payload):
    rig = factory("bad initial", "bad repair", encode(payload))
    result = BoundedRepairController(rig.backend, rig.backend).generate(payload["summary"])
    assert result.status == "accepted_after_repair" and len(result.attempts) == 3
    assert len(rig.load_calls) == rig.model.eval_calls == len(rig.model.devices) == 1
    assert rig.load_calls == [{"model_id": MODEL_ID, "revision": MODEL_REVISION,
                               "device": "cuda:0", "cache_dir": None}]
    assert len(rig.model.calls) == rig.runtime.context_entries == 3
    expected_parameters = {
        "do_sample": False, "max_new_tokens": 1024, "num_beams": 1, "num_return_sequences": 1,
        "repetition_penalty": 1.0, "return_dict_in_generate": False, "output_scores": False,
    }
    assert rig.backend.generation_parameters == expected_parameters
    for call in rig.model.calls:
        assert {k: call[k] for k in expected_parameters} == expected_parameters
    messages = [c[0] for c in rig.tokenizer.chat_calls]
    assert messages[0] == build_story_messages(payload["summary"])
    assert [json.loads(m[1]["content"])["previous_raw_output"] for m in messages[1:]] == ["bad initial", "bad repair"]
    assert [json.loads(m[1]["content"])["attempt_index"] for m in messages[1:]] == [1, 2]
    assert rig.backend.last_run["raw_output"] == "bad initial"
    assert rig.backend.last_run["prompt_version"] == PROMPT_VERSION
    assert rig.backend.last_run["prompt_sha256"] == message_hash(build_story_messages(payload["summary"]))
    assert rig.backend.last_repair["raw_output"] == encode(payload)
    assert [a.backend_metadata["purpose"] for a in result.attempts] == ["story_generation", "story_repair", "story_repair"]
    assert len({a.backend_metadata["call_id"] for a in result.attempts}) == 3
    assert all(a.metadata_status == "captured" for a in result.attempts)
    assert result.storyboard.model_dump() == json.loads(result.attempts[-1].raw_output)


@pytest.mark.parametrize("failure", ["none", "json", "schema", "summary", "exhausted", "initial_backend", "repair_backend"])
def test_controller_with_concrete_repair_method(factory, payload, failure):
    good = encode(payload)
    bad_schema = deepcopy(payload)
    bad_schema["scenes"].pop()
    bad_summary = deepcopy(payload)
    bad_summary["summary"] = "Một nguồn khác."
    outputs, expected, count = {
        "none": ([good], "accepted_initial", 1),
        "json": (["broken", good], "accepted_after_repair", 2),
        "schema": ([encode(bad_schema), good], "accepted_after_repair", 2),
        "summary": ([encode(bad_summary), good], "accepted_after_repair", 2),
        "exhausted": (["bad"] * 3, "budget_exhausted", 3),
        "initial_backend": ([RuntimeError("synthetic infrastructure failure")], "backend_failure", 1),
        "repair_backend": (["bad", RuntimeError("synthetic infrastructure failure")], "backend_failure", 2),
    }[failure]
    rig = factory(*outputs)
    result = BoundedRepairController(rig.backend, rig.backend).generate(payload["summary"])
    assert result.status == expected and len(result.attempts) == count
    assert len(rig.model.calls) == count and len(rig.load_calls) == 1
    assert (result.storyboard is not None) == expected.startswith("accepted")
    if count == 1:
        assert rig.backend.last_repair is None
    assert rig.backend.last_review is None


@pytest.mark.parametrize("version", [SEMANTIC_PROMPT_VERSION, EVIDENCE_FIRST_PROMPT_VERSION])
def test_generation_review_repair_metadata_are_independent(factory, payload, version):
    rig = factory("initial", "review", "repair", "initial again", "review again")
    rig.backend.generate(payload["summary"])
    original_run = rig.backend.last_run
    messages = build_semantic_messages(payload["summary"], Storyboard.model_validate(payload), prompt_version=version)
    rig.backend.review(messages, prompt_version=version)
    original_review = rig.backend.last_review
    rig.backend.generate_repair(feedback())
    repair_snapshot = rig.backend.last_repair
    assert rig.backend.last_run == original_run and rig.backend.last_review == original_review
    assert original_review["messages"] == messages and original_review["prompt_sha256"] == message_hash(messages)
    rig.backend.generate(payload["summary"])
    rig.backend.review(messages, prompt_version=version)
    assert rig.backend.last_repair == repair_snapshot
    repair_snapshot["messages"][0]["content"] = "mutated"
    repair_snapshot["generation_parameters"]["max_new_tokens"] = 1
    assert rig.backend.last_repair["messages"] == build_repair_messages(feedback())
    assert rig.backend.last_repair["generation_parameters"]["max_new_tokens"] == 1024
    assert len(rig.load_calls) == 1 and len(rig.model.calls) == 5


@pytest.mark.parametrize("invalid", [None, {}, True, "feedback", "unicode_summary", "unicode_raw", "unicode_evidence", "mutated"])
def test_invalid_feedback_fails_before_load_and_no_stale_metadata(factory, invalid):
    rig = factory("prior success")
    rig.backend.generate_repair(feedback())
    prior = rig.backend.last_repair
    f = invalid
    if isinstance(invalid, str) and invalid in {"unicode_summary", "unicode_raw", "unicode_evidence", "mutated"}:
        f = feedback()
        if invalid == "unicode_summary":
            f = f.model_copy(update={"original_summary": "summary\ud800"})
        elif invalid == "unicode_raw":
            f = f.model_copy(update={"previous_raw_output": "raw\udfff"})
        elif invalid == "unicode_evidence":
            f.errors[0].evidence = {"nested": {"\ud800": "bad key"}}
        else:
            f.errors[0].severity = "warning"
    with pytest.raises((TypeError, ValueError)):
        rig.backend.generate_repair(f)
    current = rig.backend.last_repair
    assert current["call_id"] != prior["call_id"] and current["error_category"] == "input_error"
    assert current["purpose"] == "story_repair" and current["prompt_version"] == REPAIR_PROMPT_VERSION
    assert current["raw_output"] is None and "prompt_sha256" not in current
    assert "messages" not in current
    assert len(rig.model.calls) == len(rig.load_calls) == 1  # Chỉ prior call; invalid invocation không load/generate.
    json.dumps(current, ensure_ascii=False, allow_nan=False).encode("utf-8")


def test_invalid_feedback_on_fresh_instance_does_not_load(factory):
    rig = factory()
    with pytest.raises(TypeError):
        rig.backend.generate_repair(None)
    assert not rig.load_calls and not rig.model.calls
    assert rig.backend.last_repair["error_category"] == "input_error"


def test_prompt_construction_error_is_input_error_and_stops_controller(factory, payload, monkeypatch):
    from src.story_generator import qwen_backend
    rig = factory("bad")

    def broken(*args, **kwargs):
        raise RuntimeError("synthetic builder failure")

    monkeypatch.setattr(qwen_backend, "build_repair_messages", broken)
    result = BoundedRepairController(rig.backend, rig.backend).generate(payload["summary"])
    assert result.status == "backend_failure" and len(result.attempts) == 2
    assert len(rig.model.calls) == len(rig.load_calls) == 1
    assert rig.backend.last_repair["error_category"] == "input_error"
    assert result.attempts[-1].backend_metadata["error_category"] == "input_error"
    assert rig.backend.last_repair["raw_output"] is None


def test_loading_failure_has_fresh_metadata_and_no_retry():
    calls = []
    error = RuntimeError("synthetic loading failure")

    def loader(**kwargs):
        calls.append(kwargs)
        raise error

    backend = QwenStoryBackend(loader=loader)
    with pytest.raises(RuntimeError) as caught:
        backend.generate_repair(feedback())
    assert caught.value is error and len(calls) == 1
    assert backend.last_repair["error_category"] == "load_error"
    assert backend.last_repair["raw_output"] is None and backend.last_run is backend.last_review is None


@pytest.mark.parametrize("phase", ["tokenization", "generation", "decode"])
def test_runtime_failures_replace_only_repair_metadata_and_never_retry(factory, phase, monkeypatch):
    rig = factory("successful repair", "next candidate")
    rig.backend.generate_repair(feedback())
    previous = rig.backend.last_repair
    error = RuntimeError("synthetic runtime failure")

    def fail(*args, **kwargs):
        raise error

    if phase == "tokenization":
        monkeypatch.setattr(rig.tokenizer, "apply_chat_template", fail)
    elif phase == "generation":
        rig.model.error = error
    else:
        monkeypatch.setattr(rig.tokenizer, "decode", fail)
    with pytest.raises(RuntimeError) as caught:
        rig.backend.generate_repair(feedback(index=2))
    current = rig.backend.last_repair
    assert caught.value is error
    assert current["call_id"] != previous["call_id"]
    assert current["error_category"] == f"{phase}_error" and current["raw_output"] is None
    assert previous["raw_output"] == "successful repair"
    assert len(rig.load_calls) == 1
    assert len(rig.model.calls) == (1 if phase == "tokenization" else 2)
    assert rig.backend.last_run is rig.backend.last_review is None


@pytest.mark.parametrize("purpose", ["unsupported", "", None, [], "story_repairs"])
def test_unsupported_internal_purpose_rejected_before_prepare_or_load(factory, purpose):
    rig = factory()
    prepared = []
    # Internal routing contract test; production consumers dùng public methods.
    with pytest.raises(ValueError, match="purpose"):
        rig.backend._generate_messages(lambda: prepared.append(True), purpose=purpose, prompt_version="invalid")
    assert not prepared and not rig.load_calls
    assert rig.backend.last_run is rig.backend.last_review is rig.backend.last_repair is None


@pytest.mark.parametrize("attribute,wrong_purpose", [("last_run", "story_repair"), ("last_repair", "semantic_review")])
def test_controller_discards_wrong_purpose_metadata(factory, payload, monkeypatch, attribute, wrong_purpose):
    rig = factory(encode(payload)) if attribute == "last_run" else factory("bad", encode(payload))
    # Mô phỏng backend contract bug qua public snapshot getter, không đổi accepted raw.
    original_getter = getattr(QwenStoryBackend, attribute).fget

    def wrong_getter(self):
        value = original_getter(self)
        if value:
            value["purpose"] = wrong_purpose
        return value

    monkeypatch.setattr(QwenStoryBackend, attribute, property(wrong_getter))
    result = BoundedRepairController(rig.backend, rig.backend).generate(payload["summary"])
    assert result.status.startswith("accepted")
    assert result.attempts[-1].metadata_status == "discarded"
    assert result.attempts[-1].backend_metadata is None


def test_import_repair_and_invalid_call_without_gpu_packages_or_network():
    root = Path(__file__).resolve().parents[1]
    script = '''
import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'transformers', 'diffusers'}:
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
def audit(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise AssertionError(event)
sys.addaudithook(audit)
from src.story_generator.qwen_backend import QwenStoryBackend
b = QwenStoryBackend()
assert b.last_repair is None
try: b.generate_repair(None)
except TypeError: pass
else: raise AssertionError('invalid feedback must fail')
assert b.last_repair['error_category'] == 'input_error'
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_failed_repair_leaves_generation_and_review_snapshots_untouched(factory, payload):
    rig = factory("initial", "review", "prior repair")
    rig.backend.generate(payload["summary"])
    board = Storyboard.model_validate(payload)
    rig.backend.review(build_semantic_messages(payload["summary"], board), prompt_version=SEMANTIC_PROMPT_VERSION)
    rig.backend.generate_repair(feedback())
    initial, review, previous = rig.backend.last_run, rig.backend.last_review, rig.backend.last_repair
    with pytest.raises(TypeError):
        rig.backend.generate_repair(None)
    assert rig.backend.last_run == initial and rig.backend.last_review == review
    assert rig.backend.last_repair["call_id"] != previous["call_id"]
    assert rig.backend.last_repair["error_category"] == "input_error"
    assert len(rig.model.calls) == 3 and len(rig.load_calls) == 1


def test_unsupported_purpose_does_not_overwrite_existing_slots(factory, payload):
    rig = factory("initial", "review", "repair")
    rig.backend.generate(payload["summary"])
    rig.backend.review(build_semantic_messages(payload["summary"], Storyboard.model_validate(payload)),
                       prompt_version=SEMANTIC_PROMPT_VERSION)
    rig.backend.generate_repair(feedback())
    before = rig.backend.last_run, rig.backend.last_review, rig.backend.last_repair
    with pytest.raises(ValueError):
        rig.backend._generate_messages(lambda: [], purpose="unknown", prompt_version="unknown")
    assert (rig.backend.last_run, rig.backend.last_review, rig.backend.last_repair) == before
    assert len(rig.model.calls) == 3 and len(rig.load_calls) == 1
