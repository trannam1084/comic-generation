"""Config/factory CPU doubles; không weights, official dataset hoặc real inference."""

from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import socket
import subprocess
import sys
from unittest.mock import Mock

import pytest

from src.configuration import ConfigurationDependencyError
from src.factory import PipelineConfig, PROJECT_ROOT, build_pipeline, load_pipeline_config
from src.pipeline_adapters import StoryStageError
from src.story_generator.qwen_backend import MODEL_ID, MODEL_REVISION, QwenStoryBackend
# Reuse scripted tokenizer/model/runtime doubles, không sửa tests baseline.
from test_qwen_repair_backend import factory as runtime_factory


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError('Network forbidden in CPU tests')
    monkeypatch.setattr(socket, 'getaddrinfo', fail)
    monkeypatch.setattr(socket.socket, 'connect', fail)


@pytest.fixture
def payload():
    return json.loads((PROJECT_ROOT / 'examples/storyboard.json').read_text())


def qconfig(tmp_path, **kwargs):
    return PipelineConfig(story_backend='qwen', story_device='cuda:0', image_device='cpu', output_dir=tmp_path, **kwargs)


@pytest.mark.parametrize('retries', [None, 0, 1, 2, 3])
def test_backend_dependent_retry_defaults_and_explicit_values(tmp_path, retries):
    assert PipelineConfig(max_retries=retries).max_retries == (0 if retries is None else retries)
    assert qconfig(tmp_path, max_retries=retries).max_retries == (2 if retries is None else retries)


def test_alias_and_independent_devices():
    old = PipelineConfig(device='cpu')
    assert old.resolved_story_device == old.resolved_image_device == 'cpu'
    c = PipelineConfig(story_backend='qwen', story_device='cuda:3', image_device='cpu')
    assert c.resolved_story_device == 'cuda:3' and c.resolved_image_device == 'cpu'
    assert PipelineConfig().resolved_story_device == PipelineConfig().resolved_image_device == 'cpu'


@pytest.mark.parametrize('kwargs', [
    {'story_backend': 'real'}, {'image_backend': 'sdxl'}, {'story_backend': 'Qwen'},
    {'story_backend': 'qwen'}, {'story_device': 'cuda:0'}, {'image_device': 'cuda:0'},
    {'device': 'cpu', 'story_device': 'cpu'}, {'device': 'cpu', 'image_device': 'cpu'},
    {'story_device': True}, {'image_device': False}, {'device': 1},
    {'max_retries': True}, {'max_retries': -1}, {'max_retries': '2'}, {'max_retries': 2.0},
    {'base_seed': True}, {'base_seed': '42'}, {'cache_dir': 'cache'},
    {'output_dir': ''}, {'output_dir': ' \t'}, {'output_dir': '\x00bad'}, {'output_dir': '\ud800'},
])
def test_invalid_settings_rejected(kwargs):
    with pytest.raises((ValueError, TypeError)):
        PipelineConfig(**kwargs)


@pytest.mark.parametrize('device', ['cpu', 'cuda', 'cuda:-1', 'cuda:1.0', 'cuda:0 ', ' cuda:0', 'gpu:0', '', True])
def test_qwen_requires_exact_cuda_device(device):
    with pytest.raises((TypeError, ValueError)):
        PipelineConfig(story_backend='qwen', story_device=device)


def test_paths_independent_of_cwd_and_unicode_preserved(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    c = qconfig(tmp_path, cache_dir='cache dữ liệu/😀')
    assert c.resolved_cache_dir == str(PROJECT_ROOT / 'cache dữ liệu/😀')
    assert PipelineConfig(output_dir='outputs/config-test').output_root == PROJECT_ROOT / 'outputs/config-test'
    assert not (PROJECT_ROOT / 'cache dữ liệu').exists()  # Config/build không tạo cache.


@pytest.mark.parametrize('failure', ['none', 'json', 'schema', 'summary', 'second', 'exhausted', 'initial_backend', 'repair_backend'])
def test_concrete_qwen_factory_with_one_shared_runtime(tmp_path, payload, runtime_factory, monkeypatch, failure):
    good = json.dumps(payload, ensure_ascii=False)
    wrong_schema = deepcopy(payload);wrong_schema['scenes'].pop()
    wrong_summary = deepcopy(payload);wrong_summary['summary'] = 'Different source'
    outputs, expected, count = {
        'none': ([good], 'accepted_initial', 1),
        'json': (['bad', good], 'accepted_after_repair', 2),
        'schema': ([json.dumps(wrong_schema), good], 'accepted_after_repair', 2),
        'summary': ([json.dumps(wrong_summary), good], 'accepted_after_repair', 2),
        'second': (['bad', 'still bad', good], 'accepted_after_repair', 3),
        'exhausted': (['bad'] * 3, 'budget_exhausted', 3),
        'initial_backend': ([RuntimeError('synthetic failure')], 'backend_failure', 1),
        'repair_backend': (['bad', RuntimeError('synthetic failure')], 'backend_failure', 2),
    }[failure]
    rig = runtime_factory(*outputs)
    import src.story_generator.qwen_backend as qmod
    from src.story_generator.repair import BoundedRepairController
    import src.factory as fmod
    instances = [];controllers = []

    def backend(**kwargs):
        b = QwenStoryBackend(**kwargs);instances.append(b);return b

    def controller(initial, repair, **kwargs):
        assert initial is repair
        c = BoundedRepairController(initial, repair, **kwargs);controllers.append(c);return c

    monkeypatch.setattr(qmod, 'QwenStoryBackend', backend)
    monkeypatch.setattr(fmod, 'BoundedRepairController', controller)
    prompt = Mock();image = Mock();renderer = Mock()
    failure_dependencies = dict(prompt_stage=prompt, image_backend=image, renderer_backend=renderer) if expected in {'budget_exhausted', 'backend_failure'} else {}
    pipeline = build_pipeline(qconfig(tmp_path, cache_dir='outputs/fake-cache'), qwen_loader=rig.loader, **failure_dependencies)
    assert len(instances) == len(controllers) == 1 and not rig.load_calls and not rig.model.calls
    if expected in {'budget_exhausted', 'backend_failure'}:
        with pytest.raises(StoryStageError) as caught:
            pipeline.generate(payload['summary'])
        assert caught.value.result.status == expected and len(caught.value.attempts) == count
        prompt.build.assert_not_called();image.generate_all.assert_not_called();renderer.render.assert_not_called()
    else:
        result = pipeline.generate(payload['summary'])
        assert result.storyboard.model_dump() == payload and result.comic_path.is_file()
        assert len(result.prompts) == len(result.images) == 4
    assert len(rig.load_calls) == 1 and len(rig.model.calls) == count
    assert rig.load_calls[0] == {'model_id': MODEL_ID, 'revision': MODEL_REVISION, 'device': 'cuda:0', 'cache_dir': str(PROJECT_ROOT / 'outputs/fake-cache')}
    b = instances[0]
    assert b.last_review is None and b.last_run['purpose'] == 'story_generation'
    if count > 1:
        assert b.last_repair['purpose'] == 'story_repair' and b.last_run['call_id'] != b.last_repair['call_id']
    for m in [b.last_run, b.last_repair]:
        if m:
            assert m['execution_mode'] == 'injected' and m.get('generation_latency_seconds') is None and m.get('peak_allocated_vram_bytes') is None
            assert m['generation_parameters']['do_sample'] is False and m['generation_parameters']['max_new_tokens'] == 1024


def test_qwen_b0_never_repairs(tmp_path, payload, runtime_factory):
    rig = runtime_factory('bad')
    with pytest.raises(StoryStageError) as caught:
        build_pipeline(qconfig(tmp_path, max_retries=0), qwen_loader=rig.loader).generate(payload['summary'])
    assert caught.value.result.status == 'budget_exhausted' and len(rig.model.calls) == 1
    assert len(rig.load_calls) == 1


@pytest.mark.parametrize('injection', ['initial_backend', 'repair_backend', 'story_stage'])
def test_selected_qwen_cannot_be_silently_overridden(tmp_path, injection):
    with pytest.raises(ValueError):
        build_pipeline(qconfig(tmp_path, max_retries=0), **{injection: Mock()})
    with pytest.raises(ValueError):
        build_pipeline(qwen_loader=lambda **kwargs: None)


def test_qwen_build_is_lazy_and_imports_no_gpu_ui_yaml(tmp_path):
    script = '''
import sys
class Block:
 def find_spec(self,fullname,path=None,target=None):
  if fullname.split('.')[0] in {'torch','transformers','diffusers','gradio','yaml'}:raise AssertionError(fullname)
sys.meta_path.insert(0,Block())
def audit(event,args):
 if event in {'socket.connect','socket.getaddrinfo'}:raise AssertionError('Network')
sys.addaudithook(audit)
from src.factory import PipelineConfig,build_pipeline
build_pipeline(PipelineConfig(story_backend='qwen',story_device='cuda:0'))
build_pipeline(PipelineConfig(device='cpu'))
assert not any(n.split('.')[0] in {'torch','transformers','diffusers','gradio','yaml'} for n in sys.modules)
'''
    r = subprocess.run([sys.executable, '-c', script], cwd=PROJECT_ROOT, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr


def test_loader_precedence_and_input_nonmutation(tmp_path):
    # Injected JSON parser is a test seam; không chứng minh parsing YAML production.
    path = tmp_path / 'config.yaml'
    raw = {'story': {'backend': 'mock'}, 'runtime': {'output_dir': 'outputs/yaml', 'max_retries': 1}, 'image': {'base_seed': 10}}
    path.write_text(json.dumps(raw))
    environment = {'OUTPUT_DIR': 'outputs/env', 'MAX_RETRIES': '0', 'BASE_SEED': '-7', 'HF_TOKEN': 'not read'}
    overrides = {'output_dir': 'outputs/explicit'}
    before = deepcopy((environment, overrides))
    c = load_pipeline_config(path, environ=environment, overrides=overrides, yaml_loader=json.loads)
    assert c.output_root == PROJECT_ROOT / 'outputs/explicit' and c.max_retries == 0 and c.base_seed == -7
    assert (environment, overrides) == before
    assert load_pipeline_config(path, yaml_loader=json.loads).max_retries == 1
    assert load_pipeline_config(environ={'STORY_BACKEND': 'qwen', 'STORY_DEVICE': 'cuda:2'}).max_retries == 2


@pytest.mark.parametrize('value,expected', [('0', 0), ('2', 2), ('auto', None)])
def test_environment_retry_auto_and_explicit(value, expected):
    c = load_pipeline_config(environ={'STORY_BACKEND': 'qwen', 'STORY_DEVICE': 'cuda:0', 'MAX_RETRIES': value})
    assert c.max_retries == (2 if expected is None else expected)


@pytest.mark.parametrize('field,value', [
    ('MAX_RETRIES', 'true'), ('MAX_RETRIES', '-1'), ('MAX_RETRIES', '2.0'), ('MAX_RETRIES', ' 2'),
    ('MAX_RETRIES', ''), ('BASE_SEED', 'auto'), ('BASE_SEED', '2.5'), ('BASE_SEED', True),
    ('STORY_BACKEND', 'unknown'), ('IMAGE_DEVICE', 'cuda:0'), ('OUTPUT_DIR', ''),
])
def test_invalid_environment_values_fail_without_echo(field, value):
    with pytest.raises((TypeError, ValueError)):
        load_pipeline_config(environ={field: value})


def test_no_ambient_environment_or_dotenv(tmp_path, monkeypatch):
    monkeypatch.setenv('STORY_BACKEND', 'qwen')
    monkeypatch.setenv('STORY_DEVICE', 'cuda:0')
    monkeypatch.chdir(tmp_path)
    (tmp_path / '.env').write_text('STORY_BACKEND=qwen\n')
    assert load_pipeline_config().story_backend == PipelineConfig().story_backend == 'mock'


def test_only_documented_environment_keys_are_read():
    class Environment(dict):
        def __getitem__(self, key):
            assert key not in {'HF_TOKEN', 'IMAGE_API_KEY'}
            return super().__getitem__(key)
    c = load_pipeline_config(environ=Environment(DEVICE='cpu', HF_TOKEN='private', IMAGE_API_KEY='private'))
    assert c.resolved_story_device == c.resolved_image_device == 'cpu'


@pytest.mark.parametrize('data', [None, [], 'scalar', {'unknown': {}}, {'story': []}, {'runtime': {'unknown': 1}}, {'story': {'backend': True}}, {'runtime': {'max_retries': True}}])
def test_yaml_shape_unknown_fields_and_strict_values(tmp_path, data):
    f = tmp_path / 'config.yaml';f.write_text('parser stub input')
    with pytest.raises((TypeError, ValueError)):
        load_pipeline_config(f, yaml_loader=lambda text: data)


def test_unknown_overrides_and_ambiguous_aliases():
    with pytest.raises(ValueError):
        load_pipeline_config(overrides={'unknown': 1})
    with pytest.raises(ValueError):
        load_pipeline_config(environ={'DEVICE': 'cpu', 'STORY_DEVICE': 'cpu'})
    with pytest.raises(TypeError):
        load_pipeline_config(environ='not mapping')
    with pytest.raises(TypeError):
        load_pipeline_config(overrides=[])
    with pytest.raises(ValueError):
        load_pipeline_config(yaml_loader=json.loads)


def test_missing_yaml_fails_clearly_without_install_or_fallback(tmp_path, monkeypatch):
    p = tmp_path / 'config.yaml';p.write_text('story:\n  backend: mock\n')
    monkeypatch.setitem(sys.modules, 'yaml', None)
    with pytest.raises(ConfigurationDependencyError, match='PyYAML'):
        load_pipeline_config(p)
    assert load_pipeline_config().story_backend == 'mock'


def test_real_yaml_repository_settings_when_dependency_available():
    pytest.importorskip('yaml', reason='PyYAML chưa cài: actual YAML parsing NOT RUN; injected parser tests không thay thế')
    c = load_pipeline_config('configs/settings.yaml')
    assert c.story_backend == c.image_backend == 'mock' and c.max_retries == 0
    assert c.resolved_story_device == c.resolved_image_device == 'cpu'


@pytest.mark.parametrize('loader', [False, {}, 'not callable'])
def test_invalid_qwen_loader_rejected_at_build(tmp_path, loader):
    with pytest.raises(TypeError, match='callable'):
        build_pipeline(qconfig(tmp_path), qwen_loader=loader)


@pytest.mark.parametrize('cache', [True, '', ' \t', '\x00bad', '\ud800'])
def test_invalid_qwen_cache_paths_rejected(tmp_path, cache):
    with pytest.raises((TypeError, ValueError)):
        qconfig(tmp_path, cache_dir=cache)


def test_yaml_environment_alias_conflict_must_be_explicitly_cleared(tmp_path):
    f = tmp_path / 'config.yaml';f.write_text('injected parser')
    parser = lambda text: {'runtime': {'device': 'cpu'}}
    env = {'STORY_BACKEND': 'qwen', 'STORY_DEVICE': 'cuda:0'}
    with pytest.raises(ValueError, match='alias'):
        load_pipeline_config(f, environ=env, yaml_loader=parser)
    c = load_pipeline_config(f, environ=env, overrides={'device': None}, yaml_loader=parser)
    assert c.resolved_story_device == 'cuda:0' and c.resolved_image_device == 'cpu' and c.max_retries == 2


@pytest.mark.parametrize('text', [
    # Hai original P1 reproductions được giữ như permanent regressions.
    'runtime:\n  max_retries: 0\n  max_retries: 2\n',
    'runtime:\n  unknown_setting: 1\nruntime:\n  max_retries: 0\n',
    'runtime:\n  max_retries: 0\n  max_retries: 0\n',
    'runtime: {}\nruntime: {}\n',
    'story:\n  backend: mock\n  backend: qwen\n',
    'story:\n  device: cpu\n  device: cpu\n',
    'runtime:\n  max_retries: 0\n  "max_retries": 2\n',
    '"runtime": {}\nruntime: {}\n',
    # Duplicate ở nested mapping ngoài schema phải fail ngay ở parser.
    'unknown:\n  deep:\n    key: 1\n    key: 2\n',
    # Constructed key semantics: YAML booleans/numbers, scalar alias.
    'unknown:\n  true: 1\n  1: 2\n',
    'unknown:\n  1: a\n  0x1: b\n',
    'unknown:\n  &key same: 1\n  *key: 2\n',
])
def test_actual_yaml_duplicate_mappings_rejected(tmp_path, text):
    import yaml
    from src.configuration import _read_yaml
    # Parser boundary được kiểm tra riêng: không nhầm unknown-field rejection là duplicate rejection.
    with pytest.raises(ValueError, match='YAML'):
        _read_yaml(text)
    path = tmp_path / 'duplicate.yaml';path.write_text(text)
    with pytest.raises(ValueError, match='YAML'):
        load_pipeline_config(path)


@pytest.mark.parametrize('text', [
    'story:\n  <<: {backend: mock}\n',
    'story:\n  <<: {backend: qwen}\n  backend: mock\n',
    'unknown:\n  base: &base {k: 1}\n  nested:\n    <<: *base\n',
    'unknown:\n  <<: [{k: 1}, {k: 2}]\n',
])
def test_actual_yaml_merge_keys_rejected(tmp_path, text):
    from src.configuration import _read_yaml
    with pytest.raises(ValueError, match='YAML'):
        _read_yaml(text)
    p = tmp_path / 'merge.yaml';p.write_text(text)
    with pytest.raises(ValueError, match='YAML'):
        load_pipeline_config(p)


@pytest.mark.parametrize('text', [
    '', 'story: [\n', '- story\n',
    '? [story, image]\n: mock\n', '? {story: mock}\n: value\n',
    '!!python/object/apply:builtins.str [0]\n',
    'story:\n  backend: null\n', 'runtime:\n  max_retries: true\n',
    'unknown: {}\n',
])
def test_actual_yaml_invalid_documents_remain_rejected(tmp_path, text):
    p = tmp_path / 'invalid.yaml';p.write_text(text)
    with pytest.raises((ValueError, TypeError)):
        load_pipeline_config(p)


def test_strict_yaml_does_not_change_global_safe_loader_and_handles_aliases():
    import yaml
    from src.configuration import _read_yaml
    before = dict(yaml.SafeLoader.yaml_constructors)
    global_method = yaml.SafeLoader.construct_mapping
    text = 'runtime:\n  max_retries: 0\n  max_retries: 2\n'
    assert yaml.safe_load(text)['runtime']['max_retries'] == 2
    with pytest.raises(ValueError):
        _read_yaml(text)
    assert yaml.safe_load(text)['runtime']['max_retries'] == 2
    assert yaml.SafeLoader.yaml_constructors == before
    assert yaml.SafeLoader.construct_mapping is global_method
    # Cùng key name trong distinct mappings không phải duplicate; mapping alias không merge.
    data = _read_yaml('first: &shared {key: value}\nsecond: *shared\nthird: {key: other}\n')
    assert data == {'first': {'key': 'value'}, 'second': {'key': 'value'}, 'third': {'key': 'other'}}
    assert data['first'] is data['second']
    with pytest.raises(ValueError):
        _read_yaml('first: &bad {key: 1, key: 2}\nsecond: *bad\n')


def test_actual_yaml_alias_devices_and_distinct_keys_valid(tmp_path):
    p = tmp_path / 'valid.yaml'
    p.write_text('story:\n  backend: &backend mock\n  device: &device cpu\nimage:\n  backend: *backend\n  device: *device\n')
    c = load_pipeline_config(p)
    assert c.story_backend == c.image_backend == 'mock'
    assert c.resolved_story_device == c.resolved_image_device == 'cpu'


def test_actual_yaml_precedence_defaults_and_explicit_budget(tmp_path):
    p = tmp_path / 'valid.yaml'
    p.write_text('story:\n  backend: mock\n  device: cpu\nimage:\n  device: cpu\nruntime:\n  max_retries: null\n  output_dir: outputs/yaml\n')
    env = {'STORY_BACKEND': 'qwen', 'STORY_DEVICE': 'cuda:0', 'OUTPUT_DIR': 'outputs/env'}
    assert load_pipeline_config(p).max_retries == 0
    c = load_pipeline_config(p, environ=env)
    assert c.max_retries == 2 and c.output_root == PROJECT_ROOT / 'outputs/env'
    for retry in [0, 1, 3]:
        c = load_pipeline_config(p, environ={**env, 'MAX_RETRIES': '2'}, overrides={'max_retries': retry, 'output_dir': 'outputs/explicit'})
        assert c.max_retries == retry and c.output_root == PROJECT_ROOT / 'outputs/explicit'
    p.write_text('runtime:\n  max_retries: 1\n')
    assert load_pipeline_config(p, environ={'MAX_RETRIES': '0'}).max_retries == 0


def test_yaml_failure_message_does_not_echo_key_or_values(tmp_path):
    p = tmp_path / 'secret-free-marker.yaml'
    for text in ['private_marker_key: 1\nprivate_marker_key: sensitive_marker_value\n', 'runtime: [sensitive_marker_value\n']:
        p.write_text(text)
        with pytest.raises(ValueError) as caught:
            load_pipeline_config(p)
        assert 'private_marker_key' not in str(caught.value)
        assert 'sensitive_marker_value' not in str(caught.value)


def test_strict_yaml_parsing_does_not_load_model_or_call_network(monkeypatch):
    from src.configuration import _read_yaml
    monkeypatch.setattr(QwenStoryBackend, 'load', lambda *a: pytest.fail('Model load during YAML parsing'))
    monkeypatch.setattr(QwenStoryBackend, 'generate', lambda *a: pytest.fail('Generation during YAML parsing'))
    assert _read_yaml('story: {backend: qwen, device: "cuda:0"}\n')['story']['backend'] == 'qwen'
