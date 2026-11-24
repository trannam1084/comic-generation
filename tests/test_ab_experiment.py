import csv
import json
import re
import unicodedata
from pathlib import Path

import pytest
from PIL import Image

from scripts import run_ab_experiment as cli
from src.image_generator import ab_experiment as ab
from src.image_generator.image_generator import BaseImageGenerator, MockImageGenerator

ROOT = Path(__file__).resolve().parent.parent
STORYBOARD = json.loads((ROOT / "examples" / "storyboard.json").read_text(encoding="utf-8"))
SEEDS = (100, 200, 300, 400)


class FailingBackend(BaseImageGenerator):
    name = "failing"

    def generate(self, prompt, seed):
        raise RuntimeError("hết VRAM")


@pytest.fixture
def results(tmp_path):
    """Kết quả sinh ảnh bằng pipeline dùng chung với backend mock (không cần GPU)."""
    out = tmp_path / "results"
    records = ab.run_ab_generation(
        MockImageGenerator(), storyboard=STORYBOARD, base_seeds=SEEDS, out_dir=out
    )
    return out, records


@pytest.fixture
def pack(tmp_path, results):
    results_dir, _ = results
    key = ab.build_blind_pack(ab.load_records(results_dir), tmp_path / "pack", shuffle_seed=2026)
    return tmp_path / "pack", key


def fill_sheet(path, ids, value_fn, *, delimiter=",", encoding="utf-8-sig", notes=""):
    with open(path, "w", encoding=encoding, newline="") as handle:
        writer = csv.writer(handle, delimiter=delimiter)
        writer.writerow(ab.SHEET_COLUMNS)
        for cid in ids:
            writer.writerow([cid] + [value_fn(cid, f) for f in ab.RATING_FIELDS] + [notes])

def to_cp1258_form(text: str) -> str:
    """Dạng chữ Excel tiếng Việt (cp1258): giữ ơ/ư/â/ê/ô/ă dựng sẵn, chỉ tách dấu thanh."""
    out = []
    for ch in unicodedata.normalize("NFC", text):
        try:
            ch.encode("cp1258")
            out.append(ch)
            continue
        except UnicodeEncodeError:
            pass
        decomposed = unicodedata.normalize("NFD", ch)
        for k in range(len(decomposed) - 1, 0, -1):
            base = unicodedata.normalize("NFC", decomposed[:k])
            try:
                base.encode("cp1258")
            except UnicodeEncodeError:
                continue
            out.append(base + decomposed[k:])
            break
        else:
            raise ValueError(f"không biểu diễn được {ch!r} trong cp1258")
    return "".join(out)

def mid(cid, field):
    return (field.low + field.high) // 2


# ---------- Seed ----------

def test_default_seeds_are_valid_and_avoid_pilot_seeds():
    seeds = ab.validate_base_seeds(ab.DEFAULT_BASE_SEEDS)
    used = {b + i for b in seeds for i in range(1, 5)}
    assert len(seeds) == 8 and not used & {43, 44, 45, 46}


@pytest.mark.parametrize("bad", [(), (100, 100), (100, 103), (-1, 200), (True, 200), (1.5, 200), ("100", 200)])
def test_invalid_base_seeds_are_rejected(bad):
    with pytest.raises(ValueError):
        ab.validate_base_seeds(bad)


def test_seeds_four_apart_do_not_overlap():
    assert ab.validate_base_seeds((100, 104)) == (100, 104)


# ---------- Sinh cặp truyện ----------

def test_generation_creates_one_pair_per_seed(results):
    out, records = results
    assert sorted((r.arm, r.base_seed) for r in records) == sorted((a, s) for a in "AB" for s in SEEDS)
    assert all((out / r.comic_path).is_file() for r in records)
    assert (out / "manifest.json").is_file()
    for arm in "AB":
        for seed in SEEDS:
            assert len(list((out / f"{arm}_seed{seed}" / "raw").glob("scene_*.png"))) == 4


def test_both_arms_share_seeds_and_inference_settings(results):
    out, _ = results
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    by_key = {(r["arm"], r["base_seed"]): r for r in manifest["runs"]}
    for seed in SEEDS:
        a, b = by_key[("A", seed)], by_key[("B", seed)]
        assert [s["seed"] for s in a["scenes"]] == [s["seed"] for s in b["scenes"]] == [seed + i for i in range(1, 5)]
        assert [s["negative_prompt"] for s in a["scenes"]] == [s["negative_prompt"] for s in b["scenes"]]


def test_only_arm_b_contains_character_descriptions(results):
    out, _ = results
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    visuals = [c["visual"] for c in STORYBOARD["characters"]]
    for run in manifest["runs"]:
        for scene in run["scenes"]:
            has_visuals = all(v in scene["prompt"] for v in visuals)
            assert has_visuals == (run["arm"] == "B")
            assert ab.E0_STYLE in scene["prompt"]
    assert manifest["arms"] == {"A": {"use_shared_characters": False}, "B": {"use_shared_characters": True}}


def test_generation_refuses_non_empty_directory(tmp_path):
    (tmp_path / "old.txt").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        ab.run_ab_generation(MockImageGenerator(), storyboard=STORYBOARD, base_seeds=SEEDS, out_dir=tmp_path)


def test_generation_error_propagates_without_manifest(tmp_path):
    out = tmp_path / "failed"
    with pytest.raises(RuntimeError, match="hết VRAM"):
        ab.run_ab_generation(FailingBackend(), storyboard=STORYBOARD, base_seeds=SEEDS, out_dir=out)
    assert not (out / "manifest.json").exists()


# ---------- Gói chấm ẩn nhãn ----------

def test_pack_structure_and_key(pack, results):
    pack_dir, key = pack
    _, records = results
    assert len(key) == 8
    assert sorted(r["comic_id"] for r in key) == [f"C{i:02d}" for i in range(1, 9)]
    for name in ("rating_pack.pdf", "rating_sheet.csv", "HUONG_DAN_CHAM.md"):
        assert (pack_dir / "for_raters" / name).stat().st_size > 0
    assert (pack_dir / "for_raters" / "rating_pack.pdf").read_bytes().startswith(b"%PDF")
    assert (pack_dir / "private" / "KEY.csv").is_file()
    assert sorted((r["arm"], r["base_seed"]) for r in key) == sorted((r.arm, r.base_seed) for r in records)
    reread = ab.read_key(pack_dir)
    assert [(r["comic_id"], r["arm"], r["base_seed"]) for r in reread] == [(r["comic_id"], r["arm"], r["base_seed"]) for r in key]


def test_anonymized_images_equal_the_sources(pack, results):
    pack_dir, key = pack
    out, records = results
    source = {(r.arm, r.base_seed): out / r.comic_path for r in records}
    for row in key:
        with Image.open(pack_dir / "for_raters" / "comics" / f"{row['comic_id']}.png") as shown, \
                Image.open(source[(row["arm"], row["base_seed"])]) as original:
            assert shown.convert("RGB").tobytes() == original.convert("RGB").tobytes()


def test_nothing_sent_to_raters_reveals_the_arm(pack):
    pack_dir, _ = pack
    sent = pack_dir / "for_raters"
    for path in sent.rglob("*"):
        assert not re.search(r"seed|arm|shared|_A|_B|A_|B_", path.name, re.IGNORECASE), path.name
    for name in ("rating_sheet.csv", "HUONG_DAN_CHAM.md"):
        text = (sent / name).read_text(encoding="utf-8-sig").lower()
        assert not re.search(r"seed|shared|nhóm a|nhóm b|phương án", text)
    for png in (sent / "comics").glob("*.png"):
        with Image.open(png) as image:
            assert not set(image.info) & {"Software", "Comment", "comment", "parameters", "Description"}


def test_shuffle_is_deterministic_and_depends_on_the_seed(tmp_path, results):
    out, _ = results
    records = ab.load_records(out)
    first = ab.build_blind_pack(records, tmp_path / "p1", shuffle_seed=1)
    again = ab.build_blind_pack(records, tmp_path / "p2", shuffle_seed=1)
    other = ab.build_blind_pack(records, tmp_path / "p3", shuffle_seed=2)
    assert [(r["comic_id"], r["arm"], r["base_seed"]) for r in first] == [(r["comic_id"], r["arm"], r["base_seed"]) for r in again]
    assert [(r["arm"], r["base_seed"]) for r in first] != [(r["arm"], r["base_seed"]) for r in other]


def test_arm_sequence_is_never_obviously_patterned(tmp_path, results):
    out, _ = results
    records = ab.load_records(out)
    for shuffle_seed in range(10):
        key = ab.build_blind_pack(records, tmp_path / f"p{shuffle_seed}", shuffle_seed=shuffle_seed)
        assert not ab._is_obvious_arm_pattern([r["arm"] for r in key]), shuffle_seed


def test_pack_rejects_bad_records(tmp_path, results):
    out, _ = results
    records = ab.load_records(out)
    with pytest.raises(ValueError):
        ab.build_blind_pack([], tmp_path / "a", shuffle_seed=1)
    with pytest.raises(ValueError):  # thiếu một nhóm
        ab.build_blind_pack([r for r in records if not (r.arm == "B" and r.base_seed == 100)], tmp_path / "b", shuffle_seed=1)
    with pytest.raises(ValueError):  # trùng
        ab.build_blind_pack(records + [records[0]], tmp_path / "c", shuffle_seed=1)
    with pytest.raises(FileNotFoundError):
        bad = [ab.RunRecord(r.arm, r.base_seed, tmp_path / "khong_co.png") if i == 0 else r for i, r in enumerate(records)]
        ab.build_blind_pack(bad, tmp_path / "d", shuffle_seed=1)
    (tmp_path / "e").mkdir()
    (tmp_path / "e" / "x").write_text("x", encoding="utf-8")
    with pytest.raises(FileExistsError):
        ab.build_blind_pack(records, tmp_path / "e", shuffle_seed=1)


def test_rubric_lists_every_rating_field():
    text = ab.rubric_text(16)
    assert all(f"`{name}`" in text for name in ab.FIELD_NAMES)
    assert "16" in text


# ---------- Đọc file điểm ----------

def ids_of(pack):
    return [r["comic_id"] for r in pack[1]]


def test_rating_sheet_template_has_all_columns_and_ids(pack):
    pack_dir, key = pack
    with open(pack_dir / "for_raters" / "rating_sheet.csv", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.reader(handle))
    assert tuple(rows[0]) == ab.SHEET_COLUMNS
    assert [r[0] for r in rows[1:]] == sorted(r["comic_id"] for r in key)


@pytest.mark.parametrize(
    "delimiter,encoding",
    [(",", "utf-8-sig"), (";", "utf-8"), ("\t", "utf-8"), (";", "cp1258"), (",", "utf-8")],
)
def test_rating_file_dialects_from_excel_are_accepted(tmp_path, pack, delimiter, encoding):
    path = tmp_path / "r.csv"
    # cp1258 (Excel tiếng Việt) lưu dấu thanh dạng ký tự tổ hợp nên ghi chú phải ở dạng NFD
    notes = to_cp1258_form("ảnh hơi mờ") if encoding == "cp1258" else "ảnh hơi mờ"
    fill_sheet(path, ids_of(pack), mid, delimiter=delimiter, encoding=encoding, notes=notes)
    table = ab.read_rating_table(path, expected_ids=ids_of(pack))
    assert set(table) == set(ids_of(pack))
    assert table["C01"]["rabbit_consistency"] == 3


def test_decimal_comma_and_trailing_blank_rows_are_tolerated(tmp_path, pack):
    ids = ids_of(pack)
    path = tmp_path / "r.csv"
    fill_sheet(path, ids, lambda cid, f: f"{mid(cid, f)},0", delimiter=";")
    with open(path, "a", encoding="utf-8", newline="") as handle:
        handle.write(";;;;;;;\n\n")
    assert ab.read_rating_table(path, expected_ids=ids)["C02"]["panels_hybrid"] == 2


def test_rating_errors_are_listed_for_the_rater(tmp_path, pack):
    ids = ids_of(pack)
    path = tmp_path / "r.csv"
    fill_sheet(path, ids, lambda cid, f: 9 if (cid == "C03" and f.name == "rabbit_consistency") else mid(cid, f))
    with pytest.raises(ab.RatingFileError, match=r"C03.*rabbit_consistency.*ngoài khoảng 1-5"):
        ab.read_rating_table(path, expected_ids=ids)

    fill_sheet(path, ids, lambda cid, f: "" if (cid == "C04" and f.name == "panels_hybrid") else mid(cid, f))
    with pytest.raises(ab.RatingFileError, match=r"C04.*panels_hybrid"):
        ab.read_rating_table(path, expected_ids=ids)

    fill_sheet(path, ids, lambda cid, f: "ba" if cid == "C05" and f.name == "turtle_consistency" else mid(cid, f))
    with pytest.raises(ab.RatingFileError, match=r"C05.*turtle_consistency"):
        ab.read_rating_table(path, expected_ids=ids)

    fill_sheet(path, ids[:-1], mid)
    with pytest.raises(ab.RatingFileError, match=ids[-1]):
        ab.read_rating_table(path, expected_ids=ids)

    fill_sheet(path, ids + ["C99"], mid)
    with pytest.raises(ab.RatingFileError, match="C99"):
        ab.read_rating_table(path, expected_ids=ids)

    fill_sheet(path, ids + [ids[0]], mid)
    with pytest.raises(ab.RatingFileError, match="trùng"):
        ab.read_rating_table(path, expected_ids=ids)


def test_missing_column_and_empty_file(tmp_path, pack):
    path = tmp_path / "r.csv"
    path.write_text("comic_id,rabbit_consistency\nC01,3\n", encoding="utf-8")
    with pytest.raises(ab.RatingFileError, match="Thiếu cột"):
        ab.read_rating_table(path, expected_ids=ids_of(pack))
    path.write_text("", encoding="utf-8")
    with pytest.raises(ab.RatingFileError):
        ab.read_rating_table(path, expected_ids=ids_of(pack))


# ---------- Phân tích ----------

def test_exact_sign_test_values():
    assert ab.exact_sign_test(0, 0) == 1.0
    assert ab.exact_sign_test(8, 0) == pytest.approx(2 / 256)
    assert ab.exact_sign_test(0, 8) == pytest.approx(2 / 256)
    assert ab.exact_sign_test(5, 3) == pytest.approx(2 * 93 / 256)
    assert ab.exact_sign_test(4, 4) == 1.0


def synthetic(key, rater_offsets):
    """Điểm giả: B hơn A ở chỉ số nhất quán, ít lai hơn A; mỗi người chấm lệch nhẹ khác nhau."""
    tables = {}
    for rater, noise in rater_offsets.items():
        table = {}
        for row in key:
            is_b = row["arm"] == "B"
            table[row["comic_id"]] = {
                "rabbit_consistency": 4 if is_b else 2,
                "turtle_consistency": 4 if is_b else 3,
                "panels_hybrid": 1 if is_b else 3,
                "panels_extra_animals": 2,
                "panels_rabbit_red_scarf": 4 if is_b else 0,
                "panels_turtle_green_brown_shell": 3,
            }
            table[row["comic_id"]]["rabbit_consistency"] += noise
        tables[rater] = table
    return tables


def test_analysis_unblinds_pairs_and_respects_direction(pack):
    _, key = pack
    result = ab.analyze_ratings(key, synthetic(key, {"r1": 0, "r2": 0}))
    f = result["fields"]
    assert result["n_runs"] == 4 and result["raters"] == ["r1", "r2"]
    assert f["rabbit_consistency"]["mean_a"] == 2 and f["rabbit_consistency"]["mean_b"] == 4
    assert f["rabbit_consistency"]["b_better"] == 4 and f["rabbit_consistency"]["a_better"] == 0
    assert f["rabbit_consistency"]["sign_test_p"] == pytest.approx(2 / 16)
    assert f["panels_hybrid"]["mean_diff_b_minus_a"] == -2 and f["panels_hybrid"]["b_better"] == 4  # ít lai hơn là tốt
    assert f["panels_extra_animals"]["ties"] == 4 and f["panels_extra_animals"]["sign_test_p"] == 1.0
    assert f["panels_turtle_green_brown_shell"]["ties"] == 4
    assert f["rabbit_consistency"]["primary"] and not f["panels_hybrid"]["primary"]


def test_inter_rater_agreement(pack):
    _, key = pack
    same = ab.analyze_ratings(key, synthetic(key, {"r1": 0, "r2": 0}))
    assert same["inter_rater"]["rabbit_consistency"] == {"mean_abs_diff": 0.0, "exact_agreement": 1.0}
    apart = ab.analyze_ratings(key, synthetic(key, {"r1": 0, "r2": 1}))
    assert apart["inter_rater"]["rabbit_consistency"]["mean_abs_diff"] == 1.0
    assert apart["inter_rater"]["rabbit_consistency"]["exact_agreement"] == 0.0
    single = ab.analyze_ratings(key, synthetic(key, {"r1": 0}))
    assert single["inter_rater"] == {}


def test_opposite_raters_show_up_in_the_per_rater_table(pack):
    _, key = pack
    tables = synthetic(key, {"r1": 0, "r2": 0})
    for row in key:  # r2 đánh giá ngược hẳn
        for field in ("rabbit_consistency", "turtle_consistency"):
            tables["r2"][row["comic_id"]][field] = 6 - tables["r2"][row["comic_id"]][field]
    result = ab.analyze_ratings(key, tables)
    diffs = result["per_rater_mean_diff_b_minus_a"]
    assert diffs["r1"]["rabbit_consistency"] > 0 > diffs["r2"]["rabbit_consistency"]


def test_analysis_rejects_incomplete_input(pack):
    _, key = pack
    tables = synthetic(key, {"r1": 0})
    del tables["r1"]["C01"]
    with pytest.raises(ValueError):
        ab.analyze_ratings(key, tables)
    with pytest.raises(ValueError):
        ab.analyze_ratings(key, {})


def test_report_has_caveats_and_every_field(pack, tmp_path):
    _, key = pack
    result = ab.analyze_ratings(key, synthetic(key, {"r1": 0, "r2": 0}))
    text = ab.format_report(result)
    assert all(name in text for name in ab.FIELD_NAMES)
    assert "mẫu rất nhỏ" in text and "không đủ để kết luận" in text
    assert "khớp với thiết kế" in text
    ab.write_analysis(result, key, tmp_path / "out")
    assert (tmp_path / "out" / "summary.md").read_text(encoding="utf-8") == text
    assert json.loads((tmp_path / "out" / "analysis.json").read_text(encoding="utf-8"))["n_runs"] == 4
    with open(tmp_path / "out" / "per_comic.csv", encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    assert len(rows) == 8 and {r["arm"] for r in rows} == {"A", "B"}


# ---------- Dòng lệnh từ đầu đến cuối ----------

def test_cli_blind_then_analyze(tmp_path, results):
    results_dir, _ = results
    pack_dir = tmp_path / "pack"
    cli.main(["blind", "--results-dir", str(results_dir), "--out-dir", str(pack_dir), "--shuffle-seed", "7"])
    key = ab.read_key(pack_dir)
    ids = [r["comic_id"] for r in key]
    tables = synthetic(key, {"r1": 0, "r2": 0})
    paths = []
    for rater, table in tables.items():
        path = tmp_path / f"{rater}.csv"
        fill_sheet(path, ids, lambda cid, f, t=table: t[cid][f.name], delimiter=";", encoding="utf-8")
        paths.append(str(path))
    cli.main(["analyze", "--pack-dir", str(pack_dir), "--ratings", *paths, "--out-dir", str(tmp_path / "result")])
    assert "rabbit_consistency" in (tmp_path / "result" / "summary.md").read_text(encoding="utf-8")


def test_cli_reports_bad_rating_file_with_its_name(tmp_path, results):
    results_dir, _ = results
    pack_dir = tmp_path / "pack"
    cli.main(["blind", "--results-dir", str(results_dir), "--out-dir", str(pack_dir), "--shuffle-seed", "7"])
    bad = tmp_path / "nguoi_cham.csv"
    bad.write_text("comic_id,rabbit_consistency\nC01,3\n", encoding="utf-8")
    with pytest.raises(SystemExit, match="nguoi_cham.csv"):
        cli.main(["analyze", "--pack-dir", str(pack_dir), "--ratings", str(bad), "--out-dir", str(tmp_path / "r")])

CAT_OWL = {
    "summary": "Mèo xám nhờ cú thắp đèn hải đăng trước cơn bão, sáng hôm sau cả hai ngắm bình minh.",
    "characters": [
        {"id": "cat", "visual": "Gray cat with white paws and a blue collar"},
        {"id": "owl", "visual": "Brown owl with big yellow eyes and a tiny hat"},
    ],
    "scenes": [
        {"index": 1, "caption_vi": "Mèo gặp cú bên ngọn hải đăng.",
         "image_prompt_en": "A cat meets an owl beside a tall lighthouse.", "characters": ["cat", "owl"]},
        {"index": 2, "caption_vi": "Cả hai thắp chiếc đèn lồng.",
         "image_prompt_en": "A cat and an owl light a lantern together.", "characters": ["cat", "owl"]},
        {"index": 3, "caption_vi": "Cơn bão kéo đến trên biển.",
         "image_prompt_en": "A cat and an owl watch a storm over the sea.", "characters": ["cat", "owl"]},
        {"index": 4, "caption_vi": "Bình minh lên, hai bạn mỉm cười.",
         "image_prompt_en": "A cat and an owl smile at the sunrise.", "characters": ["cat", "owl"]},
    ],
}
SCENE_KEYWORDS = ["lighthouse", "lantern", "storm", "sunrise"]


class SpyGenerator(MockImageGenerator):
    """Mock chỉ để ghi lại prompt thật sự được đưa tới image backend."""

    def __init__(self) -> None:
        super().__init__()
        self.prompts = []

    def generate(self, prompt, *args, **kwargs):
        self.prompts.append(prompt)
        return super().generate(prompt, *args, **kwargs)


def test_ab_generation_uses_given_storyboard_not_mock_story(tmp_path):
    spy = SpyGenerator()
    ab.run_ab_generation(spy, storyboard=CAT_OWL, base_seeds=[100], out_dir=tmp_path / "out")

    assert len(spy.prompts) == 8  # nhánh A rồi nhánh B, mỗi nhánh 4 cảnh
    for position, prompt in enumerate(spy.prompts):
        scene = position % 4
        assert prompt.scene_index == scene + 1
        text = prompt.prompt.lower()
        assert SCENE_KEYWORDS[scene] in text
        assert "rabbit" not in text and "turtle" not in text
    assert all("blue collar" not in p.prompt.lower() for p in spy.prompts[:4])  # A: không chèn mô tả chung
    assert all("blue collar" in p.prompt.lower() for p in spy.prompts[4:])      # B: có chèn mô tả chung

    manifest = json.loads((tmp_path / "out" / "manifest.json").read_text(encoding="utf-8"))
    manifest_prompts = [s["prompt"] for run in manifest["runs"] for s in run["scenes"]]
    assert manifest_prompts == [p.prompt for p in spy.prompts]


def test_ab_generation_rejects_invalid_storyboard_before_creating_files(tmp_path):
    broken = dict(CAT_OWL, scenes=CAT_OWL["scenes"][:3])
    out = tmp_path / "out"
    with pytest.raises(Exception):
        ab.run_ab_generation(SpyGenerator(), storyboard=broken, base_seeds=[100], out_dir=out)
    assert not out.exists()