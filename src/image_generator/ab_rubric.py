"""Phiếu chấm tổng quát cho thí nghiệm Task 6 (character consistency).

Phiếu không còn gắn với một truyện cụ thể: nhân vật cần chấm được suy ra từ chính storyboard.
Module này chỉ lo phần "chấm cái gì"; việc sinh ảnh, trộn ẩn nhãn và phân tích nằm ở ab_experiment.py.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

import csv
from pathlib import Path
from typing import Sequence

# Nhân vật chỉ chấm "nhất quán giữa các khung" khi storyboard cho nó xuất hiện ở ít nhất ngần này cảnh.
MIN_SCENES_FOR_CONSISTENCY = 2


@dataclass(frozen=True)
class RatedCharacter:
    char_no: int            # 1..k, đánh số lại trong số nhân vật được chấm (khóa ổn định, không phụ thuộc dấu/khoảng trắng)
    character_id: str       # id gốc trong storyboard, chỉ để người chấm đọc
    visual: str             # mô tả ngoại hình theo storyboard
    scenes: tuple[int, ...]  # các cảnh mà storyboard ghi nhân vật có mặt


def rated_characters(storyboard: Mapping[str, Any]) -> list[RatedCharacter]:
    """Trả về các nhân vật đủ điều kiện chấm nhất quán (xuất hiện >= MIN_SCENES_FOR_CONSISTENCY cảnh).

    Chỉ đọc cấu trúc storyboard, không đánh giá nội dung. Raise ValueError nếu id nhân vật bị trùng
    hoặc một cảnh nhắc tới id chưa khai báo (không âm thầm bỏ qua).
    """
    characters = storyboard.get("characters")
    scenes = storyboard.get("scenes")
    if not isinstance(characters, list) or not isinstance(scenes, list):
        raise ValueError("Storyboard cần có danh sách 'characters' và 'scenes'")

    visuals: dict[str, str] = {}
    for character in characters:
        character_id = character["id"]
        if character_id in visuals:
            raise ValueError(f"Id nhân vật bị trùng: {character_id!r}")
        visuals[character_id] = character["visual"]

    appearances: dict[str, list[int]] = {character_id: [] for character_id in visuals}
    for scene in scenes:
        in_scene: set[str] = set()
        for character_id in scene["characters"]:
            if character_id not in appearances:
                raise ValueError(f"Cảnh {scene['index']} nhắc tới nhân vật chưa khai báo: {character_id!r}")
            if character_id not in in_scene:
                in_scene.add(character_id)
                appearances[character_id].append(int(scene["index"]))

    eligible = [cid for cid, found in appearances.items() if len(found) >= MIN_SCENES_FOR_CONSISTENCY]
    return [
        RatedCharacter(number, cid, visuals[cid], tuple(sorted(appearances[cid])))
        for number, cid in enumerate(eligible, start=1)
    ]


# ---------------------------------------------------------------------------
# Phiếu chấm dạng long format: mỗi truyện một dòng "toàn truyện" (char_no = 0)
# và mỗi nhân vật đủ điều kiện một dòng (char_no = 1..k).
# ---------------------------------------------------------------------------

NA = "NA"
COMIC_ROW_NO = 0
COMIC_ROW_LABEL = "(toàn truyện)"


class RatingFileError(ValueError):
    """File điểm của người chấm không hợp lệ; thông báo liệt kê từng lỗi để người chấm sửa."""


@dataclass(frozen=True)
class RatingField:
    name: str
    scope: str           # "character": chấm trên dòng nhân vật; "comic": chấm trên dòng toàn truyện
    low: int
    high: int
    better: str          # "higher" hoặc "lower"
    primary: bool        # chỉ số chính (nhất quán giữa các khung) hay chỉ số phụ
    allow_na: bool
    question: str


RATING_FIELDS = (
    RatingField(
        "identity_consistency", "character", 1, 5, "higher", True, True,
        "Nhìn các khung có nhân vật này: chúng có trông như cùng MỘT nhân vật không "
        "(màu sắc, trang phục, đặc điểm nhận dạng, dáng)? 1 = mỗi khung một nhân vật khác hẳn, "
        "3 = giống một phần, 5 = rõ ràng là cùng một nhân vật. Ghi NA nếu bạn chỉ thấy nhân vật này ở dưới 2 khung.",
    ),
    RatingField(
        "panels_duplicate_figure", "comic", 0, 4, "lower", False, False,
        "Số khung (0 đến 4) có nhân vật DƯ: cùng một nhân vật xuất hiện nhiều hơn một bản "
        "so với danh sách nhân vật của truyện này.",
    ),
    RatingField(
        "panels_blended_figure", "comic", 0, 4, "lower", False, False,
        "Số khung (0 đến 4) có nhân vật bị LAI: một nhân vật mang đặc điểm của nhân vật khác "
        "(ví dụ đầu của nhân vật này, thân của nhân vật kia).",
    ),
)
FIELD_NAMES = tuple(f.name for f in RATING_FIELDS)
SHEET_COLUMNS = ("comic_id", "char_no", "character_id") + FIELD_NAMES + ("notes",)


@dataclass(frozen=True)
class SheetRow:
    comic_id: str
    char_no: int
    label: str    # id nhân vật hoặc COMIC_ROW_LABEL; chỉ để người chấm đọc, không dùng để khớp dòng


def sheet_rows_for_comic(comic_id: str, storyboard: Mapping[str, Any]) -> list[SheetRow]:
    """Các dòng phiếu của một truyện: dòng toàn truyện rồi từng nhân vật đủ điều kiện."""
    rows = [SheetRow(comic_id, COMIC_ROW_NO, COMIC_ROW_LABEL)]
    rows += [SheetRow(comic_id, c.char_no, c.character_id) for c in rated_characters(storyboard)]
    return rows


def write_rating_sheet(path: str | Path, rows: Sequence[SheetRow]) -> None:
    """Ghi phiếu trống (utf-8-sig để Excel đọc đúng tiếng Việt)."""
    with open(path, "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SHEET_COLUMNS)
        for row in rows:
            writer.writerow([row.comic_id, row.char_no, row.label] + [""] * (len(SHEET_COLUMNS) - 3))


def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1258"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _detect_delimiter(header_line: str) -> str:
    counts = {d: header_line.count(d) for d in (",", ";", "\t")}
    return max(counts, key=counts.get) if max(counts.values()) > 0 else ","


def _parse_int(raw: str) -> int | None:
    text = raw.strip().replace(",", ".")
    if not text:
        return None
    try:
        value = float(text)
    except ValueError:
        return None
    return int(value) if value.is_integer() else None


RatingTable = dict[tuple[str, int], dict[str, "int | None"]]


def read_rating_sheet(path: str | Path, *, expected_rows: Sequence[SheetRow]) -> RatingTable:
    """Đọc một phiếu đã điền. Trả về {(comic_id, char_no): {field: giá trị}}; `NA` thành None.

    Chỉ ô áp dụng cho dòng đó mới được điền; ô không áp dụng phải để trống. Mọi lỗi được gom lại
    và raise một lần để người chấm sửa hết.
    """
    lines = [line for line in _decode(Path(path).read_bytes()).splitlines() if line.strip()]
    if not lines:
        raise RatingFileError("File rỗng")
    reader = csv.reader(lines, delimiter=_detect_delimiter(lines[0]))
    header = [cell.strip().lower() for cell in next(reader)]
    required = ("comic_id", "char_no") + FIELD_NAMES
    missing_columns = [name for name in required if name not in header]
    if missing_columns:
        raise RatingFileError(f"Thiếu cột: {', '.join(missing_columns)}")
    position = {name: header.index(name) for name in header}

    expected = {(r.comic_id, r.char_no) for r in expected_rows}
    table: RatingTable = {}
    problems: list[str] = []

    def cell(cells: list[str], name: str) -> str:
        return cells[position[name]] if position[name] < len(cells) else ""

    for line_number, cells in enumerate(reader, start=2):
        comic_id = cell(cells, "comic_id").strip()
        if not comic_id:
            continue
        char_no = _parse_int(cell(cells, "char_no"))
        key = (comic_id, char_no)
        where = f"dòng {line_number} ({comic_id}, char_no {cell(cells, 'char_no').strip()!r})"
        if char_no is None or key not in expected:
            problems.append(f"{where}: dòng không có trong phiếu gốc")
            continue
        if key in table:
            problems.append(f"{where}: trùng dòng")
            continue
        scope = "comic" if char_no == COMIC_ROW_NO else "character"
        values: dict[str, int | None] = {}
        for field in RATING_FIELDS:
            raw = cell(cells, field.name).strip()
            if field.scope != scope:
                if raw:
                    problems.append(f"{where}, cột {field.name}: ô này không áp dụng cho dòng này, hãy để trống")
                continue
            if not raw:
                problems.append(f"{where}, cột {field.name}: còn trống")
            elif field.allow_na and raw.upper() == NA:
                values[field.name] = None
            else:
                number = _parse_int(raw)
                if number is None:
                    hint = f" hoặc {NA}" if field.allow_na else ""
                    problems.append(f"{where}, cột {field.name}: cần số nguyên{hint}, nhận {raw!r}")
                elif not field.low <= number <= field.high:
                    problems.append(f"{where}, cột {field.name}: {number} ngoài khoảng {field.low}-{field.high}")
                else:
                    values[field.name] = number
        table[key] = values

    for comic_id, char_no in sorted(expected - set(table)):
        if not any(f"({comic_id}, char_no {char_no}" in p for p in problems):
            problems.append(f"thiếu dòng ({comic_id}, char_no {char_no})")
    if problems:
        extra = f" (và {len(problems) - 20} lỗi khác)" if len(problems) > 20 else ""
        raise RatingFileError("; ".join(problems[:20]) + extra)
    return table