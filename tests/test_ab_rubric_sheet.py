import pytest

from src.image_generator.ab_rubric import (
    COMIC_ROW_LABEL, SHEET_COLUMNS, RatingFileError, SheetRow,
    read_rating_sheet, sheet_rows_for_comic, write_rating_sheet,
)

ROWS = [SheetRow("C01", 0, COMIC_ROW_LABEL), SheetRow("C01", 1, "BÀ CON"), SheetRow("C01", 2, "DU KHÁCH"),
        SheetRow("C02", 0, COMIC_ROW_LABEL)]
HEADER = "comic_id,char_no,character_id,identity_consistency,panels_duplicate_figure,panels_blended_figure,notes"
GOOD = [
    "C01,0,(toàn truyện),,1,0,",
    "C01,1,BÀ CON,4,,,",
    "C01,2,DU KHÁCH,NA,,,",
    "C02,0,(toàn truyện),,0,0,",
]


def _file(tmp_path, lines, header=HEADER, delimiter=",", encoding="utf-8-sig"):
    path = tmp_path / "r.csv"
    text = "\n".join([header] + lines)
    if delimiter != ",":
        text = text.replace(",", delimiter)
    path.write_bytes(text.encode(encoding))
    return path


def test_sheet_rows_follow_storyboard():
    sb = {"characters": [{"id": "a", "visual": "v"}, {"id": "b", "visual": "v"}],
          "scenes": [{"index": i, "caption_vi": "x", "image_prompt_en": "y", "characters": c}
                     for i, c in enumerate([["a", "b"], ["a"], ["a"], []], 1)]}
    rows = sheet_rows_for_comic("C07", sb)
    assert [(r.char_no, r.label) for r in rows] == [(0, COMIC_ROW_LABEL), (1, "a")]


def test_blank_sheet_has_expected_columns(tmp_path):
    path = tmp_path / "blank.csv"
    write_rating_sheet(path, ROWS)
    assert path.read_text(encoding="utf-8-sig").splitlines()[0] == ",".join(SHEET_COLUMNS)


def test_valid_sheet_with_na(tmp_path):
    table = read_rating_sheet(_file(tmp_path, GOOD), expected_rows=ROWS)
    assert table[("C01", 1)] == {"identity_consistency": 4}
    assert table[("C01", 2)] == {"identity_consistency": None}
    assert table[("C01", 0)] == {"panels_duplicate_figure": 1, "panels_blended_figure": 0}


def test_semicolon_and_cp1258_and_decimal_are_accepted(tmp_path):
    text = "\n".join([
        HEADER.replace(",", ";"),
        "C01;0;(toàn truyện);;1;0;",
        "C01;1;BÀ CON;4,0;;;",          # Excel tiếng Việt: dấu ; và số thập phân dùng dấu phẩy
        "C01;2;DU KHÁCH;NA;;;",
        "C02;0;(toàn truyện);;0;0;",
    ])
    path = tmp_path / "r.csv"
    path.write_bytes(text.encode("cp1258", errors="replace"))  # cột nhãn không dùng để khớp nên ký tự lạ không ảnh hưởng
    table = read_rating_sheet(path, expected_rows=ROWS)
    assert table[("C01", 1)]["identity_consistency"] == 4


def test_blank_required_cell_is_reported(tmp_path):
    lines = list(GOOD); lines[1] = "C01,1,BÀ CON,,,,"
    with pytest.raises(RatingFileError, match="còn trống"):
        read_rating_sheet(_file(tmp_path, lines), expected_rows=ROWS)


def test_out_of_range_and_non_integer(tmp_path):
    lines = list(GOOD); lines[1] = "C01,1,BÀ CON,6,,,"; lines[3] = "C02,0,x,,abc,0,"
    with pytest.raises(RatingFileError) as err:
        read_rating_sheet(_file(tmp_path, lines), expected_rows=ROWS)
    assert "ngoài khoảng 1-5" in str(err.value) and "cần số nguyên" in str(err.value)


def test_na_not_allowed_on_comic_fields(tmp_path):
    lines = list(GOOD); lines[0] = "C01,0,x,,NA,0,"
    with pytest.raises(RatingFileError, match="cần số nguyên"):
        read_rating_sheet(_file(tmp_path, lines), expected_rows=ROWS)


def test_filling_non_applicable_cell_is_reported(tmp_path):
    lines = list(GOOD); lines[1] = "C01,1,BÀ CON,4,0,,"
    with pytest.raises(RatingFileError, match="không áp dụng"):
        read_rating_sheet(_file(tmp_path, lines), expected_rows=ROWS)


def test_missing_unknown_and_duplicate_rows(tmp_path):
    with pytest.raises(RatingFileError, match="thiếu dòng"):
        read_rating_sheet(_file(tmp_path, GOOD[:3]), expected_rows=ROWS)
    with pytest.raises(RatingFileError, match="không có trong phiếu gốc"):
        read_rating_sheet(_file(tmp_path, GOOD + ["C99,0,x,,0,0,"]), expected_rows=ROWS)
    with pytest.raises(RatingFileError, match="trùng dòng"):
        read_rating_sheet(_file(tmp_path, GOOD + [GOOD[0]]), expected_rows=ROWS)


def test_missing_column_and_empty_file(tmp_path):
    with pytest.raises(RatingFileError, match="Thiếu cột"):
        read_rating_sheet(_file(tmp_path, GOOD, header="comic_id,char_no"), expected_rows=ROWS)
    empty = tmp_path / "e.csv"; empty.write_text("")
    with pytest.raises(RatingFileError, match="rỗng"):
        read_rating_sheet(empty, expected_rows=ROWS)