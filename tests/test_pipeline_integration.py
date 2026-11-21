"""CPU integration với fixture repository/scripted doubles; không official dataset/inference."""

from copy import deepcopy
from dataclasses import replace
import hashlib
import json
from pathlib import Path
import subprocess
import sys
from unittest.mock import Mock

from PIL import Image
import pytest

from src.comic_renderer.renderer import ComicRenderer, RenderConfig
from src.factory import PipelineConfig, PROJECT_ROOT, build_pipeline
from src.image_generator.image_generator import MockImageGenerator
from src.image_generator.schemas import GeneratedImage
from src.pipeline import ComicPanel, PipelineContractError
from src.pipeline_adapters import ImageStageAdapter, RepairStoryStageAdapter, RenderStageAdapter, StoryStageError
from src.story_generator.mock_backend import MockStoryBackend
from src.story_generator.repair import BoundedRepairController, RepairControllerError
from src.storyboard.schema import Storyboard


@pytest.fixture
def payload():
    return json.loads((PROJECT_ROOT / 'examples/storyboard.json').read_text(encoding='utf-8'))


class Scripted:
    def __init__(self, *outputs):
        self.outputs = iter(outputs)
        self.summaries = []
        self.feedbacks = []

    def next(self):
        value = next(self.outputs)
        if isinstance(value, Exception):
            raise value
        return value

    def generate(self, summary):
        self.summaries.append(summary)
        return self.next()

    def generate_repair(self, feedback):
        self.feedbacks.append(deepcopy(feedback))
        return self.next()


def encoded(payload):
    return json.dumps(payload, ensure_ascii=False)


def components(tmp_path):
    images = Mock(wraps=MockImageGenerator(width=64, height=64))
    renderer = Mock(wraps=ComicRenderer(RenderConfig(panel_size=256)))
    prompt = Mock()
    # Dùng actual existing legacy adapter, không dựng prompt implementation thứ hai.
    from src.storyboard.compat import LegacyPromptBuilderAdapter
    from src.image_generator.prompt_builder import PromptBuilder
    prompt.build.side_effect = LegacyPromptBuilderAdapter(PromptBuilder()).build
    return dict(prompt_stage=prompt, image_backend=images, renderer_backend=renderer)


@pytest.mark.parametrize('base_seed', [42, 100, -5])
def test_real_cpu_mock_end_to_end_and_seed_alignment(tmp_path, payload, base_seed):
    deps = components(tmp_path)
    pipeline = build_pipeline(PipelineConfig(output_dir=tmp_path, base_seed=base_seed), **deps)
    result = pipeline.generate(payload['summary'])
    assert isinstance(result.storyboard, Storyboard)
    assert result.storyboard.model_dump() == payload
    assert len(result.prompts) == len(result.images) == 4
    assert [p.scene_index for p in result.prompts] == [1, 2, 3, 4]
    assert [i.scene_index for i in result.images] == [1, 2, 3, 4]
    assert [i.seed for i in result.images] == [base_seed + i for i in range(1, 5)]
    assert all(i.backend == 'mock' and isinstance(i.image, Image.Image) for i in result.images)
    deps['prompt_stage'].build.assert_called_once()
    deps['image_backend'].generate_all.assert_called_once_with(result.prompts, base_seed=base_seed)
    deps['renderer_backend'].render.assert_called_once_with(result.images, [s['caption_vi'] for s in payload['scenes']])
    deps['renderer_backend'].save.assert_called_once()
    assert result.comic_path.is_relative_to(tmp_path)
    assert sorted(p.name for p in result.comic_path.parent.iterdir()) == ['comic.png', 'panel_1.png', 'panel_2.png', 'panel_3.png', 'panel_4.png']
    with Image.open(result.comic_path) as comic:
        assert comic.format == 'PNG' and comic.size == (548, 808)
        comic.verify()


def test_default_dimensions_consecutive_runs_no_overwrite(tmp_path, payload):
    pipeline = build_pipeline(PipelineConfig(output_dir=tmp_path))
    first = pipeline.generate(payload['summary'])
    before = {p: hashlib.sha256(p.read_bytes()).hexdigest() for p in first.comic_path.parent.iterdir()}
    second = pipeline.generate(payload['summary'])
    assert first.comic_path != second.comic_path
    assert first.comic_path.parent != second.comic_path.parent
    assert all(hashlib.sha256(p.read_bytes()).hexdigest() == h for p, h in before.items())
    with Image.open(first.comic_path) as image:
        assert image.format == 'PNG' and image.size == (1060, 1320)
    assert first.storyboard == second.storyboard
    assert first.prompts == second.prompts


@pytest.mark.parametrize('failure', ['none', 'json', 'schema', 'summary', 'second'])
def test_scripted_repair_then_actual_image_render(tmp_path, payload, failure):
    original = '  ' + payload['summary'] + '\n'
    payload['summary'] = original
    bad = deepcopy(payload)
    if failure == 'schema':
        bad['scenes'].pop()
    elif failure == 'summary':
        bad['summary'] = 'Different summary'
    raw = encoded(payload)
    outputs = {'none': [raw], 'json': ['not json', raw], 'schema': [encoded(bad), raw],
               'summary': [encoded(bad), raw], 'second': ['bad', 'still bad', raw]}[failure]
    backend = Scripted(*outputs)
    controller = BoundedRepairController(backend, backend, max_retries=2)
    spy = Mock(wraps=controller)
    deps = components(tmp_path)
    result = build_pipeline(PipelineConfig(output_dir=tmp_path), story_stage=RepairStoryStageAdapter(spy), **deps).generate(original)
    spy.generate.assert_called_once_with(original)
    assert backend.summaries == [original]
    count = 0 if failure == 'none' else 2 if failure == 'second' else 1
    assert len(backend.feedbacks) == count
    assert all(f.original_summary == original for f in backend.feedbacks)
    if count:
        assert backend.feedbacks[0].previous_raw_output == outputs[0]
    if count == 2:
        assert backend.feedbacks[1].previous_raw_output == outputs[1]
    assert result.storyboard.summary == original
    assert result.storyboard.model_dump() == payload
    assert result.comic_path.is_file()
    deps['image_backend'].generate_all.assert_called_once()
    deps['renderer_backend'].render.assert_called_once()


@pytest.mark.parametrize('failure', ['exhausted', 'backend', 'repair_backend', 'wrong_output'])
def test_story_failures_keep_history_and_never_call_downstream(tmp_path, payload, failure):
    error = RuntimeError('synthetic backend failure')
    outputs = {'exhausted': ['bad'] * 3, 'backend': [error], 'repair_backend': ['bad', error], 'wrong_output': [{}]}[failure]
    backend = Scripted(*outputs)
    deps = components(tmp_path)
    pipeline = build_pipeline(PipelineConfig(output_dir=tmp_path, max_retries=2), initial_backend=backend, repair_backend=backend, **deps)
    with pytest.raises(StoryStageError) as caught:
        pipeline.generate(payload['summary'])
    e = caught.value
    assert e.category == ('budget_exhausted' if failure == 'exhausted' else 'backend_failure')
    assert e.result.status == e.category and e.result.storyboard is None
    assert len(e.attempts) == len(outputs)
    assert len(backend.summaries) == 1
    assert len(backend.feedbacks) == len(outputs) - 1
    for dep, method in [('prompt_stage', 'build'), ('image_backend', 'generate_all'), ('renderer_backend', 'render')]:
        getattr(deps[dep], method).assert_not_called()
    assert not list(tmp_path.iterdir())
    e.result.attempts[0].diagnostics.append({'caller': 'mutation'})
    assert not any(d.get('caller') for d in e.attempts[0].diagnostics)


@pytest.mark.parametrize('summary', ['', ' \t', None, True, 3, 'bad\ud800'])
def test_invalid_input_no_backend_or_downstream(tmp_path, summary):
    backend = Scripted()
    deps = components(tmp_path)
    pipeline = build_pipeline(PipelineConfig(output_dir=tmp_path), initial_backend=backend, **deps)
    with pytest.raises(StoryStageError) as caught:
        pipeline.generate(summary)
    assert caught.value.category == 'input_failure'
    assert not backend.summaries and not caught.value.attempts
    deps['prompt_stage'].build.assert_not_called()
    deps['image_backend'].generate_all.assert_not_called()
    deps['renderer_backend'].render.assert_not_called()


def test_unexpected_validator_exception_chains_partial_history(tmp_path, payload, monkeypatch):
    from src.story_generator import repair
    original = repair.StoryboardValidator.validate_raw
    calls = []
    cause = RuntimeError('synthetic validator failure')

    def validate(self, raw, **kwargs):
        calls.append(raw)
        if len(calls) == 2:
            raise cause
        return original(self, raw, **kwargs)

    monkeypatch.setattr(repair.StoryboardValidator, 'validate_raw', validate)
    backend = Scripted('bad', encoded(payload))
    deps = components(tmp_path)
    with pytest.raises(StoryStageError) as caught:
        build_pipeline(PipelineConfig(output_dir=tmp_path, max_retries=2), initial_backend=backend, repair_backend=backend, **deps).generate(payload['summary'])
    assert isinstance(caught.value.__cause__, RepairControllerError)
    assert caught.value.__cause__.__cause__ is cause
    assert len(caught.value.attempts) == 2
    assert caught.value.attempts[-1].raw_output == encoded(payload)
    deps['prompt_stage'].build.assert_not_called()


@pytest.mark.parametrize('damage', ['storyboard', 'raw', 'summary', 'missing_report', 'not_checked_json'])
def test_adapter_rejects_inconsistent_accepted_result(payload, damage):
    result = BoundedRepairController(MockStoryBackend(), max_retries=0).generate(payload['summary'])
    if damage == 'storyboard':
        result.storyboard.scenes[0].index = 9
    elif damage == 'raw':
        other = deepcopy(payload)
        other['scenes'][0]['caption_vi'] = 'Changed caption'
        result = result.model_copy(update={'attempts': (result.attempts[0].model_copy(update={'raw_output': encoded(other)}),)})
    elif damage == 'summary':
        result = result.model_copy(update={'original_summary': 'wrong'})
    elif damage == 'missing_report':
        result = result.model_copy(update={'attempts': (result.attempts[0].model_copy(update={'validation_report': None}),)})
    else:
        result.attempts[0].validation_report.json_syntax = 'not_checked'
    controller = Mock();controller.generate.return_value = result
    with pytest.raises(StoryStageError) as caught:
        RepairStoryStageAdapter(controller).generate(payload['summary'])
    assert caught.value.category == 'invalid_accepted_result'
    assert caught.value.result is not None and caught.value.__cause__ is not None
    controller.generate.assert_called_once()


def test_story_adapter_wrong_controller_type():
    controller = Mock();controller.generate.return_value = {}
    with pytest.raises(StoryStageError, match='invalid_controller_result'):
        RepairStoryStageAdapter(controller).generate('summary')
    controller.generate.assert_called_once()


def test_adapter_does_not_mutate_controller_result(payload):
    result = BoundedRepairController(MockStoryBackend(), max_retries=0).generate(payload['summary'])
    before = result.model_dump()
    controller = Mock();controller.generate.return_value = result
    board = RepairStoryStageAdapter(controller).generate(payload['summary'])
    board.characters[0].visual = 'caller mutation'
    assert result.model_dump() == before


def test_factory_accepts_dependency_injection_and_rejects_ambiguous_story_config(tmp_path, payload):
    stage = Mock();stage.generate.return_value = Storyboard.model_validate(payload)
    assert build_pipeline(PipelineConfig(output_dir=tmp_path), story_stage=stage).generate(payload['summary']).comic_path.is_file()
    stage.generate.assert_called_once_with(payload['summary'])
    for extra in [dict(initial_backend=MockStoryBackend()), dict(repair_backend=Scripted())]:
        with pytest.raises(ValueError):
            build_pipeline(story_stage=stage, **extra)
    with pytest.raises(ValueError):
        build_pipeline(PipelineConfig(max_retries=2), story_stage=stage)


@pytest.mark.parametrize('field,value', [
    ('story_backend', 'qwen'), ('story_backend', True), ('image_backend', 'sdxl'), ('device', 'cuda:0'),
    ('max_retries', True), ('max_retries', -1), ('max_retries', 1.2), ('max_retries', '2'),
    ('base_seed', True), ('base_seed', 3.2), ('base_seed', '42'), ('output_dir', ''), ('output_dir', ' \t'), ('output_dir', None),
])
def test_strict_configuration(field, value):
    with pytest.raises((TypeError, ValueError)):
        PipelineConfig(**{field: value})


def test_no_silently_ignored_config_or_implicit_repair_backend():
    with pytest.raises(TypeError):
        PipelineConfig(unknown=True)
    with pytest.raises(TypeError):
        build_pipeline({'story_backend': 'mock'})
    with pytest.raises(ValueError, match='explicit repair_backend'):
        build_pipeline(PipelineConfig(max_retries=2))
    assert PipelineConfig().max_retries == 0
    # Không thay default real controller retry policy.
    with pytest.raises(TypeError):
        BoundedRepairController(MockStoryBackend())


def test_factory_paths_do_not_depend_on_cwd_or_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv('STORY_BACKEND', 'qwen')
    monkeypatch.setenv('DEVICE', 'cuda:0')
    monkeypatch.setenv('OUTPUT_DIR', str(tmp_path))
    assert PipelineConfig().output_root == PROJECT_ROOT / 'outputs'
    assert PipelineConfig(output_dir='outputs/custom').output_root == PROJECT_ROOT / 'outputs/custom'
    assert PipelineConfig(output_dir=tmp_path).output_root == tmp_path
    # Environment được chủ đích không đọc, không đổi mock thành real.
    assert build_pipeline() is not None


@pytest.mark.parametrize('kind', ['image_exception', 'image_wrong_type', 'image_order', 'image_index_bool', 'image_payload', 'render_exception', 'render_wrong_type', 'save_exception', 'save_missing', 'save_non_png', 'save_paths'])
def test_image_render_save_failures_do_not_fallback(tmp_path, payload, kind):
    deps = components(tmp_path)
    cause = RuntimeError('synthetic stage failure')
    if kind == 'image_exception':
        deps['image_backend'].generate_all.side_effect = cause
    elif kind.startswith('image_'):
        from src.image_generator.prompt_builder import PromptBuilder
        from src.storyboard.compat import LegacyPromptBuilderAdapter
        prompts = LegacyPromptBuilderAdapter(PromptBuilder()).build(Storyboard.model_validate(payload))
        images = MockImageGenerator(64, 64).generate_all(prompts)
        if kind == 'image_wrong_type':
            images = tuple(images)
        elif kind == 'image_order':
            images.reverse()
        elif kind == 'image_index_bool':
            images[0].scene_index = True
        else:
            images[0].image = 'not Pillow'
        deps['image_backend'].generate_all.return_value = images
    elif kind == 'render_exception':
        deps['renderer_backend'].render.side_effect = cause
    elif kind == 'render_wrong_type':
        deps['renderer_backend'].render.return_value = 'wrong'
    elif kind == 'save_exception':
        deps['renderer_backend'].save.side_effect = cause
    else:
        def bad_save(result, directory):
            paths = [directory / f'panel_{i}.png' for i in range(1, 5)] + [directory / 'comic.png']
            if kind == 'save_non_png':
                for p in paths:
                    Image.new('RGB', (3, 3)).save(p, format='JPEG')
            return [] if kind == 'save_paths' else paths
        deps['renderer_backend'].save.side_effect = bad_save
    pipeline = build_pipeline(PipelineConfig(output_dir=tmp_path), **deps)
    with pytest.raises((PipelineContractError, RuntimeError)) as caught:
        pipeline.generate(payload['summary'])
    if kind in {'image_exception', 'render_exception', 'save_exception'}:
        assert caught.value is cause
    deps['image_backend'].generate_all.assert_called_once()
    if kind.startswith('image_'):
        deps['renderer_backend'].render.assert_not_called()
    else:
        deps['renderer_backend'].render.assert_called_once()
    if kind.startswith('render_'):
        deps['renderer_backend'].save.assert_not_called()


def test_image_adapter_rejects_invalid_input_without_calling_backend(payload):
    from src.image_generator.prompt_builder import PromptBuilder
    from src.storyboard.compat import LegacyPromptBuilderAdapter
    prompts = LegacyPromptBuilderAdapter(PromptBuilder()).build(Storyboard.model_validate(payload))
    for invalid in [[], tuple(prompts), list(reversed(prompts))]:
        backend = Mock()
        with pytest.raises((ValueError, PipelineContractError)):
            ImageStageAdapter(backend).generate(invalid)
        backend.generate_all.assert_not_called()
    for invalid in [True, 1.5, '42']:
        with pytest.raises(ValueError):
            ImageStageAdapter(Mock(), base_seed=invalid)


def test_render_adapter_rejects_invalid_panels_before_filesystem(tmp_path):
    backend = Mock()
    adapter = RenderStageAdapter(backend, output_root=tmp_path / 'absent')
    images = [GeneratedImage(i, Image.new('RGB', (64, 64)), None, 'fake', 0) for i in range(1, 5)]
    valid = [ComicPanel(i, 'Caption tiếng Việt.', images[i - 1]) for i in range(1, 5)]
    for invalid in [[], tuple(valid), list(reversed(valid)), [replace(valid[0], scene_index=True), *valid[1:]], [replace(valid[0], caption_vi=' '), *valid[1:]]]:
        with pytest.raises(PipelineContractError):
            adapter.render(invalid)
    backend.render.assert_not_called()
    assert not adapter.output_root.exists()


def test_wrong_story_stage_return_stops_downstream(tmp_path, payload):
    deps = components(tmp_path)
    stage = Mock();stage.generate.return_value = {}
    with pytest.raises(PipelineContractError, match='story'):
        build_pipeline(PipelineConfig(output_dir=tmp_path), story_stage=stage, **deps).generate(payload['summary'])
    deps['prompt_stage'].build.assert_not_called()


def test_cli_from_different_working_directory(tmp_path):
    p = subprocess.run([sys.executable, str(PROJECT_ROOT / 'scripts/run_pipeline.py'), '--output-dir', str(tmp_path / 'artifacts')], cwd=tmp_path, capture_output=True, text=True)
    assert p.returncode == 0, p.stderr
    path = Path(p.stdout.strip())
    assert path.is_relative_to(tmp_path / 'artifacts') and path.is_file()
    with Image.open(path) as image:
        assert image.format == 'PNG' and image.size == (1060, 1320)


def test_factory_and_full_mock_without_gpu_ui_yaml_or_network(tmp_path):
    script = '''
import sys,json
from pathlib import Path
class Block:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'torch','transformers','diffusers','gradio','yaml'}:
            raise AssertionError('Forbidden import: '+fullname)
sys.meta_path.insert(0,Block())
def audit(event,args):
    if event in {'socket.connect','socket.getaddrinfo'}:raise AssertionError('Network')
sys.addaudithook(audit)
from src.factory import PipelineConfig,build_pipeline,PROJECT_ROOT
p=json.loads((PROJECT_ROOT/'examples/storyboard.json').read_text(encoding="utf-8"))
r=build_pipeline(PipelineConfig(output_dir=Path(sys.argv[1]))).generate(p['summary'])
assert r.comic_path.is_file()
assert not any(n.split('.')[0] in {'torch','transformers','diffusers','gradio','yaml'} for n in sys.modules)
'''
    result = subprocess.run([sys.executable, '-c', script, str(tmp_path)], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
