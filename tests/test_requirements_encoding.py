from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REQUIREMENT_FILES = sorted(ROOT.glob("requirements*.txt"))


def test_requirement_files_exist():
    names = {path.name for path in REQUIREMENT_FILES}
    assert {"requirements.txt", "requirements-ui.txt"} <= names


@pytest.mark.parametrize("path", REQUIREMENT_FILES, ids=lambda p: p.name)
def test_requirement_files_are_pure_ascii(path):
    """pip tren Windows doc file bang bang ma mac dinh cua he dieu hanh (vi du cp1258),
    nen ky tu khac ASCII (ke ca trong comment) co the gay UnicodeDecodeError."""
    data = path.read_bytes()
    try:
        data.decode("ascii")
    except UnicodeDecodeError as exc:
        line = data[: exc.start].count(b"\n") + 1
        pytest.fail(f"{path.name} co ky tu khac ASCII o dong {line}")


def test_ui_requirements_pin_gradio_and_include_base_file():
    lines = [l.strip() for l in (ROOT / "requirements-ui.txt").read_text(encoding="ascii").splitlines()
             if l.strip() and not l.lstrip().startswith("#")]
    assert "-r requirements.txt" in lines
    assert "gradio==6.32.0" in lines