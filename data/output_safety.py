"""Safe output helpers for optional dataset-preparation utilities.

Existing metadata is protected by default. Intentional replacement requires an
explicit --overwrite flag in the calling script.
"""
from __future__ import annotations

import os
import tempfile
from pathlib import Path
from collections.abc import Iterable


def ensure_outputs_available(paths: Iterable[Path], *, overwrite: bool = False) -> None:
    """Fail before a job starts if any target already exists and overwrite is off."""
    targets = sorted({Path(path).expanduser().resolve() for path in paths}, key=str)
    existing = [path for path in targets if path.exists()]
    if existing and not overwrite:
        joined = "\n".join(f" - {path}" for path in existing)
        raise FileExistsError(
            "Refusing to overwrite existing output file(s):\n"
            f"{joined}\nUse a different output path or pass --overwrite explicitly."
        )


def atomic_write_text(
    path: Path,
    content: str,
    *,
    encoding: str = "utf-8",
    overwrite: bool = False,
) -> Path:
    """Write text via a same-directory temporary file without clobbering by default."""
    target = Path(path).expanduser().resolve()
    if not isinstance(content, str):
        raise TypeError("content must be str")
    target.parent.mkdir(parents=True, exist_ok=True)
    ensure_outputs_available([target], overwrite=overwrite)

    fd, temporary_name = tempfile.mkstemp(
        prefix=f".{target.name}.", suffix=".tmp", dir=str(target.parent)
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(fd, "w", encoding=encoding, newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())

        if overwrite:
            os.replace(temporary, target)
        else:
            # Hard-link creation is atomic and fails if the destination appeared
            # after the initial preflight; it never replaces an existing target.
            os.link(temporary, target)
            temporary.unlink()
    finally:
        if temporary.exists():
            temporary.unlink()
    return target
