"""Scripted CPU doubles; synthetic cases không thuộc official dataset hoặc benchmark."""

from copy import deepcopy
import json
from pathlib import Path
import subprocess
import sys
import unicodedata

import pytest

from src.story_generator.repair import BoundedRepairController, RepairControllerError
from src.storyboard.schema import Storyboard


@pytest.fixture
def payload():
    # Synthetic story dùng riêng cho kiểm thử orchestration, không expected semantic labels.
    return {
        "summary": "Một người gieo hạt, chăm cây và thu hoạch quả.",
        "characters": [{"id": "grower", "visual": "An adult wearing a blue shirt."}],
        "scenes": [
            {"index": i, "caption_vi": caption, "image_prompt_en": prompt, "characters": ["grower"]}
            for i, caption, prompt in [
                (1, "Người làm vườn gieo hạt.", "A gardener planting a seed."),
                (2, "Người làm vườn tưới nước.", "A gardener watering a seedling."),
                (3, "Cây lớn và ra quả.", "A gardener beside a fruit tree."),
                (4, "Người làm vườn thu hoạch.", "A gardener harvesting fruit."),
            ]
        ],
    }


def dump(payload):
    return json.dumps(payload, ensure_ascii=False)


class ScriptedBackend:
    def __init__(self, *outputs):
        self.outputs = list(outputs)
        self.initial_calls = []
        self.repair_calls = []

    def _next(self):
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        return output

    def generate(self, summary):
        self.initial_calls.append(summary)
        return self._next()

    def generate_repair(self, feedback):
        self.repair_calls.append(feedback)
        return self._next()


def run(payload, *outputs, max_retries=2):
    backend = ScriptedBackend(*outputs)
    result = BoundedRepairController(backend, backend, max_retries=max_retries).generate(payload["summary"])
    return result, backend


def assert_transport(result, tmp_path):
    text = result.model_dump_json()
    json.loads(text)
    path = tmp_path / "report.json"
    path.write_text(text, encoding="utf-8")
    assert path.read_text(encoding="utf-8") == text
    json.dumps(result.model_dump(mode="json"), ensure_ascii=False, allow_nan=False).encode("utf-8")


def test_initial_success(payload, tmp_path):
    original = deepcopy(payload)
    result, backend = run(payload, dump(payload))
    assert result.status == "accepted_initial"
    assert isinstance(result.storyboard, Storyboard)
    assert result.storyboard.model_dump() == original == payload
    assert backend.initial_calls == [payload["summary"]]
    assert backend.repair_calls == []
    assert len(result.attempts) == 1
    attempt = result.attempts[0]
    assert attempt.attempt_index == 0 and attempt.generation_kind == "initial"
    assert attempt.raw_output == dump(payload)
    assert attempt.backend_metadata is None and attempt.metadata_status == "not_available"
    assert attempt.validation_report.production_success is True
    assert attempt.validation_report.semantic_validity == "not_checked"
    assert 0 <= attempt.elapsed_seconds <= result.elapsed_seconds
    assert_transport(result, tmp_path)


@pytest.mark.parametrize("failure", ["json", "fences", "count", "index", "reference", "summary"])
def test_one_repair_from_deterministic_error(payload, failure, tmp_path):
    bad = deepcopy(payload)
    if failure == "count":
        bad["scenes"].pop()
    elif failure == "index":
        bad["scenes"][0]["index"] = "1"
    elif failure == "reference":
        bad["scenes"][0]["characters"] = ["unknown"]
    elif failure == "summary":
        bad["summary"] += " Khác."
    raw = {"json": "{broken", "fences": "```json\n" + dump(payload) + "\n```"}.get(failure, dump(bad))
    result, backend = run(payload, raw, dump(payload))
    assert result.status == "accepted_after_repair"
    assert [a.attempt_index for a in result.attempts] == [0, 1]
    assert [a.generation_kind for a in result.attempts] == ["initial", "repair"]
    feedback = backend.repair_calls[0]
    assert feedback.original_summary == payload["summary"]
    assert feedback.previous_raw_output == raw == result.attempts[0].raw_output
    assert feedback.attempt_index == 1
    code = "INVALID_JSON" if failure in {"json", "fences"} else "SUMMARY_MISMATCH" if failure == "summary" else "SCHEMA_VIOLATION"
    assert {issue.code for issue in feedback.errors} == {code}
    assert all(issue.severity == "error" for issue in feedback.errors)
    if failure == "index":
        assert feedback.errors[0].location == ("scenes", 0, "index")
        assert feedback.errors[0].evidence == {"validation_type": "int_type"}
    assert len(backend.initial_calls) == len(backend.repair_calls) == 1
    assert result.storyboard.model_dump() == payload
    assert_transport(result, tmp_path)


def test_second_repair_success(payload):
    bad = deepcopy(payload)
    bad["scenes"].pop()
    result, backend = run(payload, "not json", dump(bad), dump(payload))
    assert result.status == "accepted_after_repair"
    assert len(backend.initial_calls) == 1 and len(backend.repair_calls) == 2
    assert [a.validation_report.structural_validity for a in result.attempts] == ["not_checked", "failed", "passed"]
    assert backend.repair_calls[1].previous_raw_output == dump(bad)
    assert backend.repair_calls[1].attempt_index == 2


@pytest.mark.parametrize("budget", [0, 1, 2, 4])
def test_budget_exhausted_keeps_all_attempts(payload, budget):
    raws = [f"invalid {i}" for i in range(budget + 1)]
    result, backend = run(payload, *raws, max_retries=budget)
    assert result.status == "budget_exhausted" and result.storyboard is None
    assert len(result.attempts) == budget + 1
    assert [a.raw_output for a in result.attempts] == raws
    assert len(backend.initial_calls) == 1 and len(backend.repair_calls) == budget
    assert all(a.validation_report.production_success is False for a in result.attempts)


def test_baseline_needs_no_repair_backend(payload):
    backend = ScriptedBackend(dump(payload))
    assert BoundedRepairController(backend, max_retries=0).generate(payload["summary"]).status == "accepted_initial"


@pytest.mark.parametrize("budget", [True, False, -1, 1.0, "2", None, [], {}])
def test_invalid_retry_configuration(budget):
    with pytest.raises(ValueError, match="max_retries"):
        BoundedRepairController(ScriptedBackend(), ScriptedBackend(), max_retries=budget)


def test_invalid_backend_interfaces():
    with pytest.raises(TypeError, match="initial_backend"):
        BoundedRepairController(object(), max_retries=0)
    with pytest.raises(TypeError, match="repair_backend"):
        BoundedRepairController(ScriptedBackend())


@pytest.mark.parametrize("summary", [None, 12, True, [], {}, b"story", "", " \t\n"])
def test_input_failure_no_calls(summary, tmp_path):
    backend = ScriptedBackend()
    result = BoundedRepairController(backend, backend).generate(summary)
    assert result.status == "input_failure" and result.failure_category == "invalid_summary"
    assert result.attempts == () and result.storyboard is None
    assert not backend.initial_calls and not backend.repair_calls
    assert_transport(result, tmp_path)


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
def test_source_unicode_failure_no_call(surrogate, tmp_path):
    backend = ScriptedBackend()
    result = BoundedRepairController(backend, backend).generate("Truyện" + surrogate)
    assert result.status == "input_failure" and result.failure_category == "invalid_summary_unicode"
    assert result.original_summary is None and not result.attempts
    assert result.diagnostics[0]["representation"] == "python_unicode_escape"
    assert result.diagnostics[0]["original_utf8_preserved"] is False
    assert not backend.initial_calls and not backend.repair_calls
    assert_transport(result, tmp_path)


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_original_summary_preserved_exactly(payload, form):
    payload["summary"] = "  " + unicodedata.normalize(form, payload["summary"]) + " 😀\n"
    result, backend = run(payload, "invalid", "invalid again", dump(payload))
    assert result.status == "accepted_after_repair"
    assert backend.initial_calls == [payload["summary"]]
    assert all(f.original_summary == payload["summary"] for f in backend.repair_calls)
    assert result.storyboard.summary == payload["summary"]


def test_warnings_only_do_not_repair(payload):
    payload["characters"].append({"id": "unused", "visual": payload["characters"][0]["visual"]})
    payload["scenes"][1]["caption_vi"] = payload["scenes"][0]["caption_vi"]
    result, backend = run(payload, dump(payload))
    assert result.status == "accepted_initial" and not backend.repair_calls
    assert {i.code for i in result.attempts[0].validation_report.issues} == {
        "UNUSED_CHARACTER", "DUPLICATE_VISUAL_DESCRIPTION", "DUPLICATE_SCENE_CAPTION",
    }
    assert all(i.severity == "warning" for i in result.attempts[0].validation_report.issues)


def test_feedback_excludes_warnings_and_protects_canonical_history(payload):
    bad = deepcopy(payload)
    bad["summary"] = "Sai summary."
    bad["characters"].append({"id": "unused", "visual": "A second person."})

    class MutatingRepair:
        def generate_repair(self, feedback):
            assert [i.code for i in feedback.errors] == ["SUMMARY_MISMATCH"]
            feedback.errors[0].evidence["expected"] = "mutated"
            feedback.errors.clear()
            return dump(payload)

    result = BoundedRepairController(ScriptedBackend(dump(bad)), MutatingRepair()).generate(payload["summary"])
    assert result.status == "accepted_after_repair"
    assert result.attempts[0].validation_report.issues[0].evidence["expected"] == payload["summary"]
    assert result.attempts[1].feedback.errors[0].evidence["expected"] == payload["summary"]
    assert len(result.attempts[0].validation_report.issues) == 2


@pytest.mark.parametrize("stage", ["initial", "repair"])
def test_backend_exception_stops_without_retry(payload, stage, tmp_path):
    outputs = [RuntimeError("sensitive error message not copied")]
    if stage == "repair":
        outputs.insert(0, "invalid")
    result, backend = run(payload, *outputs)
    assert result.status == "backend_failure" and result.failure_category == "backend_exception"
    assert result.storyboard is None
    assert len(backend.initial_calls) == 1 and len(backend.repair_calls) == (stage == "repair")
    last = result.attempts[-1]
    assert last.validation_report is None
    assert last.diagnostics[-1]["exception_types"] == ["RuntimeError"]
    assert "sensitive error message" not in result.model_dump_json()
    assert_transport(result, tmp_path)


@pytest.mark.parametrize("stage", ["initial", "repair"])
@pytest.mark.parametrize("output", [None, 42, True, {}, [], b"{}"])
def test_wrong_backend_output_contract_stops(payload, stage, output, tmp_path):
    outputs = [output] if stage == "initial" else ["invalid", output]
    result, backend = run(payload, *outputs)
    assert result.status == "backend_failure" and result.failure_category == "backend_output_type"
    assert result.storyboard is None and result.attempts[-1].raw_output is None
    assert len(backend.repair_calls) == (stage == "repair")
    assert_transport(result, tmp_path)


@pytest.mark.parametrize("surrogate", ["\ud800", "\udfff"])
@pytest.mark.parametrize("stage", ["initial", "repair"])
def test_literal_raw_surrogate_not_silently_repaired(payload, surrogate, stage, tmp_path):
    raw = '{"summary":"' + surrogate + '"}'
    outputs = [raw] if stage == "initial" else ["bad", raw]
    result, backend = run(payload, *outputs)
    assert result.status == "backend_failure" and result.failure_category == "invalid_output_unicode"
    attempt = result.attempts[-1]
    assert attempt.raw_output is None and attempt.raw_output_preservation == "escaped_diagnostic"
    assert attempt.diagnostics[0]["escaped_text"] == raw.encode("unicode_escape").decode("ascii")
    assert len(backend.repair_calls) == (stage == "repair")
    assert_transport(result, tmp_path)


def test_escaped_surrogate_raw_stays_raw_and_uses_existing_parser(payload, tmp_path):
    raw = r'{"summary":"\ud800"}'
    result, backend = run(payload, raw, dump(payload))
    assert result.status == "accepted_after_repair"
    assert result.attempts[0].raw_output == raw == backend.repair_calls[0].previous_raw_output
    assert result.attempts[0].validation_report.issues[0].code == "INVALID_JSON"
    assert_transport(result, tmp_path)


def test_no_sort_add_scenes_or_summary_overwrite(payload):
    bad = deepcopy(payload)
    bad["scenes"].reverse()
    bad["summary"] = "Khác nguồn."
    result, _ = run(payload, dump(bad), max_retries=0)
    assert result.status == "budget_exhausted" and result.storyboard is None
    assert result.attempts[0].raw_output == dump(bad)
    assert payload["scenes"][0]["index"] == 1


def test_structural_acceptance_does_not_claim_semantic_correctness(payload):
    payload["scenes"][-1]["caption_vi"] = "Một sự kiện không có trong nguồn."
    result, _ = run(payload, dump(payload))
    assert result.status == "accepted_initial"
    assert result.attempts[0].validation_report.semantic_validity == "not_checked"


class MetadataBackend(ScriptedBackend):
    def __init__(self, *outputs):
        super().__init__(*outputs)
        self.last_run = None
        self.last_repair = None

    def generate(self, summary):
        output = super().generate(summary)
        self.last_run = {"call_id": "initial-1", "raw_output": output, "purpose": "story_generation",
                         "generation_parameters": {"max_new_tokens": 1024, "unapproved": "omit"},
                         "unapproved": "omit"}
        return output

    def generate_repair(self, feedback):
        output = super().generate_repair(feedback)
        self.last_repair = {"call_id": f"repair-{len(self.repair_calls)}", "raw_output": output, "purpose": "repair"}
        return output


def test_fresh_metadata_snapshots_are_isolated_and_allowlisted(payload):
    backend = MetadataBackend("bad", dump(payload))
    result = BoundedRepairController(backend, backend).generate(payload["summary"])
    assert [a.backend_metadata["call_id"] for a in result.attempts] == ["initial-1", "repair-1"]
    assert all(a.metadata_status == "captured" for a in result.attempts)
    assert "unapproved" not in result.model_dump_json()
    backend.last_run["generation_parameters"]["max_new_tokens"] = 1
    assert result.attempts[0].backend_metadata["generation_parameters"]["max_new_tokens"] == 1024
    assert result.attempts[1].feedback.model_dump().keys() == {
        "original_summary", "previous_raw_output", "attempt_index", "errors",
    }


@pytest.mark.parametrize("mode", ["stale", "wrong_raw", "nan", "unicode", "missing_id", "getter_error"])
def test_unsafe_or_stale_metadata_discarded(payload, mode):
    class UnsafeMetadata(ScriptedBackend):
        @property
        def last_run(self):
            if mode == "getter_error":
                raise RuntimeError("do not leak")
            value = {"call_id": "old" if mode == "stale" or not self.initial_calls else "new",
                     "raw_output": "different" if mode == "wrong_raw" else dump(payload)}
            if mode == "nan":
                value["generation_latency_seconds"] = float("nan")
            if mode == "unicode":
                value["prompt_version"] = "\ud800"
            if mode == "missing_id":
                value.pop("call_id")
            return value

    backend = UnsafeMetadata(dump(payload))
    result = BoundedRepairController(backend, max_retries=0).generate(payload["summary"])
    assert result.status == "accepted_initial"
    assert result.attempts[0].metadata_status == "discarded"
    assert result.attempts[0].backend_metadata is None


def test_backend_error_keeps_only_fresh_partial_raw(payload):
    class PartialBackend:
        last_run = {"call_id": "old", "raw_output": "stale"}

        def generate(self, summary):
            self.last_run = {"call_id": "new", "raw_output": "partial output", "error_category": "decode_failure"}
            raise RuntimeError("failed")

    result = BoundedRepairController(PartialBackend(), max_retries=0).generate(payload["summary"])
    assert result.status == "backend_failure"
    assert result.attempts[0].raw_output == "partial output"
    assert result.attempts[0].validation_report is None


def test_unexpected_validator_failure_keeps_partial_history_and_chain(payload, monkeypatch):
    from src.story_generator import repair

    backend = ScriptedBackend(dump(payload))

    def broken(*args, **kwargs):
        raise RuntimeError("validator failed")

    monkeypatch.setattr(repair.StoryboardValidator, "validate_raw", broken)
    with pytest.raises(RepairControllerError) as caught:
        BoundedRepairController(backend, backend).generate(payload["summary"])
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert caught.value.failure_category == "validation_failure"
    assert caught.value.attempts[0].raw_output == dump(payload)
    assert len(backend.initial_calls) == 1 and not backend.repair_calls


def test_import_and_execution_without_gpu_network_or_semantic_review():
    root = Path(__file__).resolve().parents[1]
    script = '''
import sys
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch', 'transformers', 'diffusers', 'requests', 'httpx'} or fullname.startswith('src.storyboard.semantic'):
            raise AssertionError(fullname)
sys.meta_path.insert(0, Block())
def audit(event, args):
    if event in {'socket.connect', 'socket.getaddrinfo'}:
        raise AssertionError(event)
sys.addaudithook(audit)
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.repair import BoundedRepairController
import json
from pathlib import Path
summary = json.loads(Path('examples/storyboard.json').read_text(encoding="utf-8"))['summary']
r = BoundedRepairController(MockStoryBackend(), max_retries=0).generate(summary)
assert r.status == 'accepted_initial'
'''
    completed = subprocess.run([sys.executable, "-c", script], cwd=root, capture_output=True, text=True)
    assert completed.returncode == 0, completed.stderr


@pytest.mark.parametrize("raw", ["null", "[]", "42", '"text"', "{", "NaN", "Infinity", '{"index":1e999}'])
def test_malformed_and_wrong_shape_outputs_are_validated_from_scratch(payload, raw, tmp_path):
    result, backend = run(payload, raw, dump(payload))
    assert result.status == "accepted_after_repair"
    report = result.attempts[0].validation_report
    assert report.production_success is False
    assert {i.code for i in report.issues} <= {"INVALID_JSON", "SCHEMA_VIOLATION"}
    assert report.raw_output == raw
    assert backend.repair_calls[0].previous_raw_output == raw
    assert_transport(result, tmp_path)


@pytest.mark.parametrize("form", ["NFC", "NFD"])
def test_nfc_nfd_difference_is_summary_mismatch_not_normalized(payload, form):
    original = unicodedata.normalize(form, payload["summary"])
    payload["summary"] = unicodedata.normalize("NFD" if form == "NFC" else "NFC", original)
    assert payload["summary"] != original
    backend = ScriptedBackend(dump(payload))
    result = BoundedRepairController(backend, max_retries=0).generate(original)
    assert result.status == "budget_exhausted"
    assert result.attempts[0].validation_report.issues[0].code == "SUMMARY_MISMATCH"
    assert result.attempts[0].raw_output == dump(payload)


def test_stale_partial_metadata_is_not_used_on_backend_failure(payload):
    class FailedBackend:
        last_run = {"call_id": "previous", "raw_output": dump(payload)}

        def generate(self, summary):
            raise RuntimeError("failure before new metadata")

    result = BoundedRepairController(FailedBackend(), max_retries=0).generate(payload["summary"])
    assert result.status == "backend_failure"
    assert result.attempts[0].raw_output is None
    assert result.attempts[0].backend_metadata is None
    assert result.attempts[0].metadata_status == "discarded"


def test_materialization_failure_keeps_history_and_does_not_repair(payload, monkeypatch):
    from src.story_generator import repair

    backend = ScriptedBackend(dump(payload))

    def broken(*args, **kwargs):
        raise RuntimeError("materialization failed")

    monkeypatch.setattr(repair.Storyboard, "model_validate_json", broken)
    with pytest.raises(RepairControllerError) as caught:
        BoundedRepairController(backend, backend).generate(payload["summary"])
    assert isinstance(caught.value.__cause__, RuntimeError)
    assert len(caught.value.attempts) == 1
    assert caught.value.attempts[0].raw_output == dump(payload)
    assert caught.value.attempts[0].validation_report.production_success is True
    assert not backend.repair_calls
