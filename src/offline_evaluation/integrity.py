"""Strict JSON, hash verification và write-once local artifacts; không mở dataset paths."""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _transport(value: Any) -> None:
    if isinstance(value, str):
        value.encode("utf-8")
    elif isinstance(value, float) and not math.isfinite(value):
        raise ValueError("Non-finite JSON number.")
    elif isinstance(value, dict):
        for key, item in value.items():
            _transport(key)
            _transport(item)
    elif isinstance(value, (list, tuple)):
        for item in value:
            _transport(item)


def json_bytes(value: Any) -> bytes:
    """Canonical evaluation serialization; không thay thế hash của original raw bytes."""
    def plain(item):
        if isinstance(item, BaseModel):
            # Python mode giữ bool thay vì serializer của Optional[int] đổi True -> 1.
            return plain(item.model_dump(mode="python", exclude_computed_fields=True))
        if isinstance(item, dict):
            if any(type(key) is not str for key in item):
                raise ValueError("JSON object keys must be strings.")
            return {key: plain(child) for key, child in item.items()}
        if isinstance(item, (list, tuple)):
            return [plain(child) for child in item]
        return item

    value = plain(value)
    _transport(value)
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"),
                      allow_nan=False).encode("utf-8")


def _pairs(items: list) -> dict:
    result = {}
    for key, value in items:
        if key in result:
            raise ValueError("Duplicate JSON object key.")
        result[key] = value
    return result


def _constant(value: str):
    raise ValueError("Non-finite JSON constant.")


def parse_record(raw: bytes, model: type[T]) -> T:
    """Duplicate/Unicode/finite guards chỉ áp dụng evaluation records, không đổi Task09A parser."""
    data = json.loads(raw.decode("utf-8"), object_pairs_hook=_pairs, parse_constant=_constant)
    _transport(data)
    return model.model_validate_json(json_bytes(data))


def checked_copy(value: T, model: type[T]) -> T:
    if not isinstance(value, model):
        raise TypeError("Expected a typed evaluation record instance.")
    data = value.model_dump(mode="python", exclude_computed_fields=True)
    _transport(data)
    checked = model.model_validate(data, strict=True)
    return parse_record(json_bytes(checked), model)


def verify_reference(reference, payload: bytes) -> None:
    """Caller cung cấp bytes; không follow path trong untrusted reference."""
    if sha256_bytes(payload) != reference.sha256:
        raise ValueError("Artifact SHA-256 mismatch.")


def write_session(parent: Path, artifacts: dict[str, bytes]) -> Path:
    """Atomic unique directory; exclusive member writes, manifest hashes original bytes.

    Nếu ghi lỗi, giữ partial session để audit; không xóa hoặc overwrite prior sessions.
    Caller chỉ cung cấp sanitized outputs, không environment/raw logs/credentials.
    """
    import tempfile

    for name, payload in artifacts.items():
        if (not name or Path(name).name != name or name in (".", "..", "checksums.json")
                or "/" in name or "\\" in name or ":" in name or type(payload) is not bytes):
            raise ValueError("Only flat explicit artifact names with bytes are supported.")
    parent = parent.resolve()
    parent.mkdir(parents=True, exist_ok=True)
    session = Path(tempfile.mkdtemp(prefix="evaluation-", dir=parent))
    for name, payload in artifacts.items():
        with (session / name).open("xb") as stream:
            stream.write(payload)
    checksums = {name: sha256_bytes(payload) for name, payload in artifacts.items()}
    with (session / "checksums.json").open("xb") as stream:
        stream.write(json_bytes(checksums))
    return session
