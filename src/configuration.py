"""Strict pipeline config; YAML/environment chỉ đọc qua explicit loader, không dotenv."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass, fields
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _path(value: object, name: str) -> Path:
    if not isinstance(value, (str, Path)):
        raise TypeError(f"{name} phải là str hoặc pathlib.Path.")
    text = str(value)
    if not text.strip() or '\x00' in text:
        raise ValueError(f"{name} không được rỗng hoặc chứa NUL.")
    try:
        text.encode('utf-8')
    except UnicodeError:
        raise ValueError(f"{name} không có UTF-8 transport hợp lệ.") from None
    path = Path(value)
    return (path if path.is_absolute() else PROJECT_ROOT / path).resolve()


@dataclass(frozen=True)
class PipelineConfig:
    """Retry None là auto: mock0/qwen2; explicit0 được giữ. Không tự chọn GPU."""

    story_backend: str = 'mock'
    image_backend: str = 'mock'
    device: str | None = None  # Alias cũ cho cả hai stages; không trộn với split fields.
    output_dir: str | Path = 'outputs'
    max_retries: int | None = None
    base_seed: int = 42
    story_device: str | None = None
    image_device: str | None = None
    cache_dir: str | Path | None = None

    def __post_init__(self) -> None:
        if type(self.story_backend) is not str or self.story_backend not in {'mock', 'qwen'}:
            raise ValueError('story_backend chỉ hỗ trợ mock hoặc qwen.')
        if type(self.image_backend) is not str or self.image_backend != 'mock':
            raise ValueError('image_backend hiện chỉ hỗ trợ mock; không fallback.')
        if self.device is not None and (self.story_device is not None or self.image_device is not None):
            raise ValueError('Không kết hợp device alias và story_device/image_device.')
        for name in ['device', 'story_device', 'image_device']:
            value = getattr(self, name)
            if value is not None and type(value) is not str:
                raise TypeError(f'{name} phải là string hoặc None.')
        story = self.resolved_story_device
        if self.story_backend == 'mock':
            if story != 'cpu':
                raise ValueError('Mock story chỉ hỗ trợ cpu.')
        elif re.fullmatch(r'cuda:[0-9]+', story) is None:
            raise ValueError('Qwen cần explicit story_device dạng cuda:N; không tự đổi CPU sang GPU.')
        if self.resolved_image_device != 'cpu':
            raise ValueError('Mock image chỉ hỗ trợ cpu.')
        if self.max_retries is None:
            object.__setattr__(self, 'max_retries', 2 if self.story_backend == 'qwen' else 0)
        if type(self.max_retries) is not int or self.max_retries < 0:
            raise ValueError('max_retries phải là integer không âm, không nhận bool.')
        if type(self.base_seed) is not int:
            raise ValueError('base_seed phải là integer, không nhận bool.')
        _path(self.output_dir, 'output_dir')
        if self.cache_dir is not None:
            _path(self.cache_dir, 'cache_dir')
            if self.story_backend != 'qwen':
                raise ValueError('cache_dir chỉ áp dụng cho qwen; không silently ignore trong mock mode.')

    @property
    def resolved_story_device(self) -> str:
        return self.story_device if self.story_device is not None else self.device if self.device is not None else 'cpu'

    @property
    def resolved_image_device(self) -> str:
        return self.image_device if self.image_device is not None else self.device if self.device is not None else 'cpu'

    @property
    def output_root(self) -> Path:
        return _path(self.output_dir, 'output_dir')

    @property
    def resolved_cache_dir(self) -> str | None:
        return str(_path(self.cache_dir, 'cache_dir')) if self.cache_dir is not None else None


YAML_KEYS = {
    'story': {'backend': 'story_backend', 'device': 'story_device', 'cache_dir': 'cache_dir'},
    'image': {'backend': 'image_backend', 'device': 'image_device', 'base_seed': 'base_seed'},
    'runtime': {'device': 'device', 'output_dir': 'output_dir', 'max_retries': 'max_retries'},
}
ENV_KEYS = {
    'STORY_BACKEND': 'story_backend', 'IMAGE_BACKEND': 'image_backend', 'DEVICE': 'device',
    'STORY_DEVICE': 'story_device', 'IMAGE_DEVICE': 'image_device', 'OUTPUT_DIR': 'output_dir',
    'MAX_RETRIES': 'max_retries', 'BASE_SEED': 'base_seed', 'STORY_CACHE_DIR': 'cache_dir',
}


class ConfigurationDependencyError(RuntimeError):
    """YAML requested nhưng optional PyYAML chưa sẵn sàng; không tự cài hoặc fallback."""


def _read_yaml(text: str) -> object:
    try:
        import yaml
    except ModuleNotFoundError as exc:
        if exc.name != 'yaml':
            raise
        raise ConfigurationDependencyError('Đọc YAML cần PyYAML (requirements.txt, chưa pin); hãy xin quyền cài riêng.') from None
    class _StrictMappingError(yaml.constructor.ConstructorError):
        """Chỉ chứa fixed reason và parser mark; không echo document/key/value."""

    class _StrictSafeLoader(yaml.SafeLoader):
        """Private per-call subclass; không sửa PyYAML constructors/global state."""

        def construct_mapping(self, node, deep=False):
            if not isinstance(node, yaml.MappingNode):
                raise _StrictMappingError(None, None, 'Invalid mapping.', node.start_mark)
            seen = set()
            # Scan constructed keys trước khi base constructor tạo dict/overwrite values.
            for key_node, _ in node.value:
                if key_node.tag == 'tag:yaml.org,2002:merge':
                    raise _StrictMappingError(None, None, 'YAML merge keys are not supported.', key_node.start_mark)
                key = self.construct_object(key_node, deep=True)
                try:
                    duplicate = key in seen
                    seen.add(key)
                except TypeError:
                    raise _StrictMappingError(None, None, 'Unhashable mapping key.', key_node.start_mark) from None
                if duplicate:
                    raise _StrictMappingError(None, None, 'Duplicate YAML mapping key.', key_node.start_mark)
            return super().construct_mapping(node, deep=deep)

    try:
        return yaml.load(text, Loader=_StrictSafeLoader)
    except _StrictMappingError as exc:
        mark = exc.problem_mark
        raise ValueError(f"YAML không hợp lệ: {exc.problem} (line {mark.line + 1}, column {mark.column + 1}).") from None
    except yaml.YAMLError:
        # Không đưa document fragments/credential values vào display message.
        raise ValueError('YAML không hợp lệ; kiểm tra file cấu hình local.') from None


def load_pipeline_config(
    yaml_path: str | Path | None = None, *,
    environ: Mapping[str, str] | None = None,
    overrides: Mapping[str, object] | None = None,
    yaml_loader: Callable[[str], object] | None = None,
) -> PipelineConfig:
    """Defaults → YAML → documented environ keys → flat overrides; validate sau merge.

    Không đọc ambient os.environ hoặc .env. Caller opt-in bằng environ=os.environ.
    yaml_loader là test seam cho parser đã tin cậy; không phải parser YAML tự viết.
    """
    values: dict[str, object] = {}
    if yaml_loader is not None and yaml_path is None:
        raise ValueError('yaml_loader cần yaml_path explicit.')
    if yaml_path is not None:
        text = _path(yaml_path, 'yaml_path').read_text(encoding='utf-8')
        data = (yaml_loader if yaml_loader is not None else _read_yaml)(text)
        if not isinstance(data, Mapping):
            raise TypeError('YAML root phải là mapping, không nhận empty document/list/scalar.')
        for section, section_values in data.items():
            if type(section) is not str or section not in YAML_KEYS:
                raise ValueError('YAML có section không được hỗ trợ.')
            if not isinstance(section_values, Mapping):
                raise TypeError('YAML section phải là mapping.')
            for key, value in section_values.items():
                if type(key) is not str or key not in YAML_KEYS[section]:
                    raise ValueError('YAML có setting không được hỗ trợ.')
                values[YAML_KEYS[section][key]] = value
    if environ is not None:
        if not isinstance(environ, Mapping):
            raise TypeError('environ phải là mapping; không parse .env files.')
        # Chỉ lookup documented keys, không dump/read credential values hay whole environment.
        for name, field in ENV_KEYS.items():
            if name not in environ:
                continue
            value = environ[name]
            if type(value) is not str:
                raise TypeError(f'{name} phải là string environment value.')
            if field in {'max_retries', 'base_seed'}:
                if field == 'max_retries' and value == 'auto':
                    value = None
                elif re.fullmatch(r'-?[0-9]+', value) is not None:
                    value = int(value)
                else:
                    raise ValueError(f'{name} phải là integer text' + (' hoặc auto.' if field == 'max_retries' else '.'))
            elif field == 'cache_dir' and value == '':
                value = None
            values[field] = value
    if overrides is not None:
        if not isinstance(overrides, Mapping):
            raise TypeError('overrides phải là flat mapping PipelineConfig fields.')
        known = {field.name for field in fields(PipelineConfig)}
        if any(type(k) is not str or k not in known for k in overrides):
            raise ValueError('Explicit overrides có setting không được hỗ trợ.')
        values.update(overrides)
    return PipelineConfig(**values)
