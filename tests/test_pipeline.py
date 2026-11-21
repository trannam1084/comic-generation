"""Orchestration trên CPU; image/render doubles chỉ tồn tại trong tests."""

from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import subprocess
import sys
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import GeneratedImage, ScenePrompt
from src.pipeline import ComicPipeline, ComicResult, PipelineContractError
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.story_generator import StoryGenerator
from src.storyboard.compat import LegacyPromptBuilderAdapter
from src.storyboard.schema import Storyboard


ROOT = Path(__file__).resolve().parents[1]


class Spy:
    """Ghi arguments/thứ tự gọi; action thay được để kiểm tra failure boundaries."""

    def __init__(self, name, events, action):
        self.name, self.events, self.action = name, events, action
        self.calls = []

    def __call__(self, *args):
        self.events.append(self.name)
        self.calls.append(args)
        return self.action(*args)


def fake_images(prompts):
    """Payload text dùng kiểm thử, không phải ảnh hoặc Mock Image Generator thật."""
    return [
        GeneratedImage(p.scene_index, f"test-payload-{p.scene_index}", None, "test-double", 0.0)
        for p in prompts
    ]


@pytest.fixture
def rig(tmp_path):
    payload = json.loads((ROOT / "examples/storyboard.json").read_text(encoding="utf-8"))
    events = []
    artifact = tmp_path / "test-artifact.json"

    def fake_render(panels):
        # Artifact kiểm thử alignment, không phải comic ảnh thật.
        artifact.write_text(
            json.dumps(
                [{"index": p.scene_index, "caption": p.caption_vi} for p in panels],
                ensure_ascii=False,
            ),
            encoding="utf-8",
        )
        return artifact

    story = Spy("story", events, StoryGenerator(MockStoryBackend()).generate)
    prompts = Spy("prompts", events, LegacyPromptBuilderAdapter(PromptBuilder()).build)
    images = Spy("images", events, fake_images)
    render = Spy("render", events, fake_render)
    pipeline = ComicPipeline(
        SimpleNamespace(generate=story), SimpleNamespace(build=prompts),
        SimpleNamespace(generate=images), SimpleNamespace(render=render),
    )
    return SimpleNamespace(
        pipeline=pipeline, story=story, prompts=prompts, images=images, render=render,
        payload=payload, summary=payload["summary"], events=events, artifact=artifact,
    )


def test_success_uses_real_story_generator_and_prompt_builder(rig):
    original = deepcopy(rig.payload)
    result = rig.pipeline.generate(rig.summary)
    assert isinstance(result, ComicResult)
    assert result.storyboard.model_dump() == original
    assert rig.events == ["story", "prompts", "images", "render"]
    assert all(len(stage.calls) == 1 for stage in [rig.story, rig.prompts, rig.images, rig.render])
    assert rig.story.calls == [(rig.summary,)]
    assert rig.prompts.calls[0][0].model_dump() == original
    assert len(result.prompts) == len(result.images) == 4
    assert all(isinstance(p, ScenePrompt) for p in result.prompts)
    assert all(isinstance(i, GeneratedImage) for i in result.images)
    assert [p.scene_index for p in result.prompts] == [1, 2, 3, 4]
    assert [i.scene_index for i in result.images] == [1, 2, 3, 4]
    assert rig.images.calls[0][0] == result.prompts
    assert "red scarf" in result.prompts[0].prompt
    panels = rig.render.calls[0][0]
    assert [p.scene_index for p in panels] == [1, 2, 3, 4]
    for panel, scene, image in zip(panels, result.storyboard.scenes, result.images):
        assert panel.caption_vi == scene.caption_vi
        assert panel.generated_image is image
        assert panel.generated_image.scene_index == scene.index
    assert result.comic_path == rig.artifact
    assert json.loads(result.comic_path.read_text(encoding="utf-8")) == [
        {"index": s["index"], "caption": s["caption_vi"]} for s in original["scenes"]
    ]


def test_storyboard_from_caller_is_not_shared_or_mutated(rig):
    source = Storyboard.model_validate(rig.payload)
    rig.story.action = lambda _: source
    result = rig.pipeline.generate(rig.summary)
    assert result.storyboard is not source
    assert rig.prompts.calls[0][0] is not source
    assert result.storyboard.model_dump() == source.model_dump() == rig.payload
    result.storyboard.scenes[0].caption_vi = "Caller mutation"
    assert source.model_dump() == rig.payload


def test_mutating_builder_is_rejected_and_caller_storyboard_is_preserved(rig):
    source = Storyboard.model_validate(rig.payload)
    rig.story.action = lambda _: source

    def mutate(storyboard):
        prompts = LegacyPromptBuilderAdapter(PromptBuilder()).build(storyboard)
        storyboard.scenes[0].caption_vi = "Mutation by dependency"
        return prompts

    rig.prompts.action = mutate
    with pytest.raises(PipelineContractError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value.stage == "prompts"
    assert rig.events == ["story", "prompts"]
    assert source.model_dump() == rig.payload


def test_adapter_preserves_every_field_and_explicitly_uses_tuples(rig):
    captured = []

    class RecordingBuilder(PromptBuilder):
        def build(self, storyboard):
            captured.append(storyboard)
            return super().build(storyboard)

    source = Storyboard.model_validate(rig.payload)
    prompts = LegacyPromptBuilderAdapter(RecordingBuilder()).build(source)
    legacy = captured[0]
    assert isinstance(legacy.characters, tuple) and isinstance(legacy.scenes, tuple)
    assert all(isinstance(scene.characters, tuple) for scene in legacy.scenes)
    assert legacy.summary == source.summary
    assert [asdict(c) for c in legacy.characters] == rig.payload["characters"]
    for old, new in zip(legacy.scenes, source.scenes):
        assert old.index == new.index
        assert old.caption_vi == new.caption_vi
        assert old.image_prompt_en == new.image_prompt_en
        assert list(old.characters) == new.characters
    assert all(isinstance(p.character_ids, tuple) for p in prompts)
    source.scenes[0].characters.append("unknown")
    with pytest.raises(ValidationError):
        LegacyPromptBuilderAdapter(RecordingBuilder()).build(source)
    assert len(captured) == 1


@pytest.mark.parametrize("stage", ["prompts", "images"])
@pytest.mark.parametrize("count", [0, 3, 5])
def test_wrong_count_stops_before_next_stage(rig, stage, count):
    original = getattr(rig, stage).action

    def wrong_count(value):
        output = original(value)
        return (output + [output[0]])[:count]

    getattr(rig, stage).action = wrong_count
    with pytest.raises(PipelineContractError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value.stage == stage
    expected = ["story", "prompts"] if stage == "prompts" else ["story", "prompts", "images"]
    assert rig.events == expected
    assert not rig.artifact.exists()


@pytest.mark.parametrize("stage", ["prompts", "images"])
@pytest.mark.parametrize("indices", [[1, 1, 3, 4], [4, 3, 2, 1], [0, 1, 2, 3], [1, 2, 3, 5], [True, 2, 3, 4], [1.0, 2, 3, 4], ["1", 2, 3, 4]])
def test_wrong_index_is_rejected_without_sorting(rig, stage, indices):
    original = getattr(rig, stage).action
    returned = []

    def wrong_indices(value):
        output = [replace(item, scene_index=index) for item, index in zip(original(value), indices)]
        returned.extend(output)
        return output

    getattr(rig, stage).action = wrong_indices
    with pytest.raises(PipelineContractError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value.stage == stage
    assert [item.scene_index for item in returned] == indices
    assert rig.events == (["story", "prompts"] if stage == "prompts" else ["story", "prompts", "images"])
    assert not rig.artifact.exists()


@pytest.mark.parametrize("stage", ["prompts", "images"])
@pytest.mark.parametrize("kind", ["tuple", "none", "wrong_item"])
def test_wrong_collection_or_item_type_is_rejected(rig, stage, kind):
    original = getattr(rig, stage).action

    def invalid(value):
        output = original(value)
        return {"tuple": tuple(output), "none": None, "wrong_item": [object()] * 4}[kind]

    getattr(rig, stage).action = invalid
    with pytest.raises(PipelineContractError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value.stage == stage
    assert rig.events == (["story", "prompts"] if stage == "prompts" else ["story", "prompts", "images"])


@pytest.mark.parametrize("stage", ["story", "prompts", "images", "render"])
def test_dependency_failure_propagates_same_exception_without_retry_or_fallback(rig, stage):
    original = RuntimeError(f"{stage} failure")

    def fail(_):
        raise original

    getattr(rig, stage).action = fail
    with pytest.raises(RuntimeError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value is original
    order = ["story", "prompts", "images", "render"]
    assert rig.events == order[:order.index(stage) + 1]
    for name in order:
        assert len(getattr(rig, name).calls) == (1 if name in rig.events else 0)
    assert not rig.artifact.exists()


@pytest.mark.parametrize("kind", ["wrong_type", "mismatched_summary", "mutated_invalid"])
def test_invalid_story_stage_output_stops_before_prompts(rig, kind):
    source = Storyboard.model_validate(rig.payload)
    if kind == "wrong_type":
        source = rig.payload
    elif kind == "mismatched_summary":
        source.summary = "Khác input"
    else:
        source.scenes[0].index = True
    rig.story.action = lambda _: source
    with pytest.raises((PipelineContractError, ValidationError)):
        rig.pipeline.generate(rig.summary)
    assert rig.events == ["story"]


def test_missing_image_payload_is_not_success(rig):
    rig.images.action = lambda prompts: [replace(i, image=None) for i in fake_images(prompts)]
    with pytest.raises(PipelineContractError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value.stage == "images"
    assert rig.events == ["story", "prompts", "images"]


@pytest.mark.parametrize("kind", ["missing", "empty", "directory", "string", "none"])
def test_renderer_must_return_path_to_nonempty_file(rig, kind, tmp_path):
    empty = tmp_path / "empty.txt"
    empty.touch()
    outputs = {"missing": tmp_path / "missing.txt", "empty": empty,
               "directory": tmp_path, "string": str(empty), "none": None}
    rig.render.action = lambda _: outputs[kind]
    with pytest.raises(PipelineContractError) as caught:
        rig.pipeline.generate(rig.summary)
    assert caught.value.stage == "render"
    assert rig.events == ["story", "prompts", "images", "render"]
    assert len(rig.render.calls) == 1


def test_dependencies_can_be_replaced_without_changing_pipeline(rig):
    rig.prompts.action = lambda storyboard: [
        ScenePrompt(s.index, f"custom-{s.index}", "", tuple(s.characters))
        for s in storyboard.scenes
    ]
    rig.images.action = lambda prompts: [
        GeneratedImage(p.scene_index, object(), 42, "alternate-test-double", 0.0)
        for p in prompts
    ]
    result = rig.pipeline.generate(rig.summary)
    assert result.prompts[0].prompt == "custom-1"
    assert all(i.backend == "alternate-test-double" for i in result.images)


def test_pipeline_import_and_run_without_gpu_packages_or_network(tmp_path):
    script = '''
import builtins, json, sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, sys.argv[1])
original_import = builtins.__import__
blocked = {"torch", "transformers", "diffusers", "accelerate", "huggingface_hub", "requests", "httpx"}
def guarded_import(name, *args, **kwargs):
    if name.split(".")[0] in blocked:
        raise AssertionError("Unexpected import: " + name)
    return original_import(name, *args, **kwargs)
def deny_network(event, args):
    if event.startswith("socket.") or event == "urllib.Request":
        raise AssertionError("Unexpected network operation: " + event)
builtins.__import__ = guarded_import
sys.addaudithook(deny_network)
from src.pipeline import ComicPipeline
from src.story_generator.story_generator import StoryGenerator
from src.story_generator.mock_backend import MockStoryBackend
from src.storyboard.compat import LegacyPromptBuilderAdapter
from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import GeneratedImage
artifact = Path(sys.argv[2]) / "test-artifact.txt"
def render(panels):
    assert [p.scene_index for p in panels] == [1, 2, 3, 4]
    artifact.write_text("orchestration test only", encoding="utf-8")
    return artifact
images = SimpleNamespace(generate=lambda prompts: [
    GeneratedImage(p.scene_index, object(), None, "test-double", 0.0) for p in prompts
])
summary = json.loads((Path(sys.argv[1]) / "examples/storyboard.json").read_text(encoding="utf-8"))["summary"]
result = ComicPipeline(StoryGenerator(MockStoryBackend()), LegacyPromptBuilderAdapter(PromptBuilder()), images,
                       SimpleNamespace(render=render)).generate(summary)
assert result.comic_path.is_file()
assert not blocked.intersection(sys.modules)
'''
    result = subprocess.run(
        [sys.executable, "-B", "-c", script, str(ROOT), str(tmp_path)],
        cwd=tmp_path, capture_output=True, text=True, timeout=30,
    )
    assert result.returncode == 0, result.stdout + result.stderr
