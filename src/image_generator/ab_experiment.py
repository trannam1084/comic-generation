"""Thí nghiệm Task 6: so sánh A (prompt độc lập) và B (shared character descriptions).

Đơn vị phân tích là MỘT TRUYỆN TRANH 4 khung, vì nhất quán nhân vật là việc các khung trông như
cùng một nhân vật. Mỗi `base_seed` sinh một cặp truyện (A và B) dùng cùng seed theo từng cảnh và cùng
thông số suy luận; chỉ khác việc có chèn mô tả nhân vật dùng chung vào prompt hay không.

Quy trình:
  1. `run_ab_generation`  : sinh các cặp truyện (cần GPU khi dùng SDXLImageGenerator).
  2. `build_blind_pack`   : trộn ngẫu nhiên, ẩn nhãn A/B, tạo gói cho người chấm và file khóa riêng.
  3. `read_rating_table`  : đọc file điểm của từng người chấm.
  4. `analyze_ratings`    : mở nhãn và so sánh A với B (thống kê mô tả, không kết luận quá mức).
"""

from __future__ import annotations

import csv
import hashlib
import itertools
import json
import math
import os
import random
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

ARMS = ("A", "B")
ARM_USES_SHARED_CHARACTERS = {"A": False, "B": True}
SCENES_PER_COMIC = 4
# Cách nhau từ 4 trở lên để bộ seed (base+1..base+4) của các truyện không chồng lấn; tránh seed 43-46 đã dùng ở pilot.
DEFAULT_BASE_SEEDS = (100, 200, 300, 400, 500, 600, 700, 800)

# Cấu hình prompt E0 (đã chọn ở pilot bước 3.2).
E0_STYLE = "children's storybook illustration, clean line art, vibrant colors, single scene"
E0_NEGATIVE = (
    "text, letters, watermark, signature, blurry, low quality, deformed, extra limbs, "
    "multiple panels, collage, split screen, comic page, frame, border, grid"
)


class RatingFileError(ValueError):
    """File điểm của người chấm không hợp lệ; thông báo liệt kê từng lỗi để người chấm sửa."""


@dataclass(frozen=True)
class RunRecord:
    arm: str
    base_seed: int
    comic_path: Path


@dataclass(frozen=True)
class RatingField:
    name: str
    low: int
    high: int
    better: str      # "higher" hoặc "lower"
    primary: bool    # chỉ số chính (nhất quán giữa các khung) hay chỉ số phụ
    question: str


RATING_FIELDS = (
    RatingField(
        "rabbit_consistency", 1, 5, "higher", True,
        "Nhìn cả 4 khung: các con thỏ có trông như cùng MỘT nhân vật không (màu lông, tai, khăn, dáng)? "
        "1 = mỗi khung một con khác hẳn, 3 = giống một phần, 5 = rõ ràng là cùng một con.",
    ),
    RatingField(
        "turtle_consistency", 1, 5, "higher", True,
        "Tương tự, nhưng cho các con rùa: 1 = mỗi khung một con khác hẳn, 3 = giống một phần, "
        "5 = rõ ràng là cùng một con.",
    ),
    RatingField(
        "panels_hybrid", 0, 4, "lower", False,
        "Số khung (0 đến 4) có nhân vật bị LAI: thỏ mang mai rùa, hoặc rùa có đầu hay tai thỏ.",
    ),
    RatingField(
        "panels_extra_animals", 0, 4, "lower", False,
        "Số khung (0 đến 4) có DƯ nhân vật: nhiều hơn một thỏ hoặc nhiều hơn một rùa.",
    ),
    RatingField(
        "panels_rabbit_red_scarf", 0, 4, "higher", False,
        "Số khung (0 đến 4) mà con thỏ trắng quàng khăn đỏ.",
    ),
    RatingField(
        "panels_turtle_green_brown_shell", 0, 4, "higher", False,
        "Số khung (0 đến 4) mà con rùa có thân màu xanh và mai màu nâu.",
    ),
)
FIELD_NAMES = tuple(f.name for f in RATING_FIELDS)
SHEET_COLUMNS = ("comic_id",) + FIELD_NAMES + ("notes",)


# ---------------------------------------------------------------------------
# 1. Sinh các cặp truyện A/B
# ---------------------------------------------------------------------------
def validate_base_seeds(base_seeds: Sequence[int]) -> tuple[int, ...]:
    seeds = tuple(base_seeds)
    if not seeds:
        raise ValueError("Cần ít nhất một base_seed")
    for seed in seeds:
        if isinstance(seed, bool) or not isinstance(seed, int) or seed < 0:
            raise ValueError(f"base_seed phải là số nguyên >= 0, nhận {seed!r}")
    if len(set(seeds)) != len(seeds):
        raise ValueError("base_seed bị trùng")
    ordered = sorted(seeds)
    for low, high in zip(ordered, ordered[1:]):
        if high - low < SCENES_PER_COMIC:
            raise ValueError(
                f"base_seed {low} và {high} gần nhau (< {SCENES_PER_COMIC}): bộ seed của các truyện bị chồng lấn"
            )
    return seeds


def run_ab_generation(
    generator: Any,
    *,
    storyboard: Mapping[str, Any],
    base_seeds: Sequence[int],
    out_dir: str | Path,
    style: str = E0_STYLE,
    negative_prompt: str = E0_NEGATIVE,
) -> list[RunRecord]:
    """Sinh một cặp truyện (A và B) cho mỗi base_seed bằng pipeline dùng chung.

    Mọi lỗi được raise nguyên vẹn (không retry, không bỏ qua). Thư mục `out_dir` phải trống hoặc chưa có.
    """
    from src.configuration import PipelineConfig
    from src.factory import build_pipeline
    from src.image_generator.prompt_builder import PromptBuilder
    from src.storyboard.compat import LegacyPromptBuilderAdapter

    seeds = validate_base_seeds(base_seeds)
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Thư mục kết quả đã có nội dung: dùng thư mục mới để không ghi đè")
    out.mkdir(parents=True, exist_ok=True)

    summary = storyboard["summary"]
    records: list[RunRecord] = []
    runs: list[dict[str, Any]] = []
    params: dict[str, Any] | None = None
    for base_seed in seeds:
        scene_seeds: dict[str, list[int]] = {}
        for arm in ARMS:
            run_dir = out / f"{arm}_seed{base_seed}"
            run_dir.mkdir()
            comic_dir = run_dir / "comic"
            comic_dir.mkdir()
            (run_dir / "raw").mkdir()

            builder = PromptBuilder(
                style=style,
                negative_prompt=negative_prompt,
                use_shared_characters=ARM_USES_SHARED_CHARACTERS[arm],
            )
            config = PipelineConfig(output_dir=comic_dir, base_seed=base_seed)
            pipeline = build_pipeline(
                config, image_backend=generator, prompt_stage=LegacyPromptBuilderAdapter(builder)
            )
            result = pipeline.generate(summary)

            for generated in result.images:
                generated.image.save(run_dir / "raw" / f"scene_{generated.scene_index}.png")
            scene_seeds[arm] = [g.seed for g in result.images]
            params = params or dict(result.images[0].params)
            comic_rel = Path(os.path.relpath(Path(result.comic_path), out))
            records.append(RunRecord(arm, base_seed, comic_rel))
            runs.append({
                "arm": arm,
                "base_seed": base_seed,
                "comic": comic_rel.as_posix(),
                "scenes": [
                    {
                        "scene_index": g.scene_index,
                        "seed": g.seed,
                        "elapsed_sec": round(g.elapsed_sec, 2),
                        "prompt": p.prompt,
                        "negative_prompt": p.negative_prompt,
                    }
                    for g, p in zip(result.images, result.prompts)
                ],
            })
        if scene_seeds["A"] != scene_seeds["B"]:
            raise RuntimeError("Seed theo từng cảnh phải giống nhau giữa A và B")

    manifest = {
        "arms": {arm: {"use_shared_characters": flag} for arm, flag in ARM_USES_SHARED_CHARACTERS.items()},
        "base_seeds": list(seeds),
        "style": style,
        "negative_prompt": negative_prompt,
        "inference_params": params,
        "runs": runs,
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    return records


def load_records(results_dir: str | Path) -> list[RunRecord]:
    root = Path(results_dir)
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    return [RunRecord(run["arm"], int(run["base_seed"]), root / run["comic"]) for run in manifest["runs"]]


# ---------------------------------------------------------------------------
# 2. Gói chấm ẩn nhãn
# ---------------------------------------------------------------------------
def rubric_text(n_comics: int) -> str:
    lines = [
        "# Hướng dẫn chấm truyện tranh",
        "",
        f"Bạn sẽ xem {n_comics} truyện tranh (mã C01, C02, ...) trong file `rating_pack.pdf` "
        "(hoặc các ảnh trong thư mục `comics/`). Mỗi truyện có 4 khung. Hãy điền điểm vào file `rating_sheet.csv`.",
        "",
        "## Nguyên tắc",
        "- Chấm MỘT MÌNH, không bàn với ai trước khi nộp. Không đoán hay hỏi truyện nào được tạo bằng cách nào.",
        "- Chấm theo những gì nhìn thấy, không theo việc truyện đẹp hay xấu.",
        "- Khoảng 1 phút cho mỗi truyện. Nếu không chắc, chọn giá trị gần đúng nhất và ghi chú vào cột `notes`.",
        "- Thiết kế nhân vật: thỏ trắng, tai dài, quàng khăn đỏ; rùa nhỏ màu xanh, mai nâu.",
        "",
        "## Các cột cần điền (chỉ điền số nguyên)",
    ]
    for field in RATING_FIELDS:
        lines.append(f"- `{field.name}` (từ {field.low} đến {field.high}): {field.question}")
    lines += [
        "",
        "## Cách nộp",
        "1. Mở `rating_sheet.csv` bằng Excel hoặc Google Sheets, điền các cột số cho từng dòng (mỗi dòng là một truyện).",
        "2. Đừng đổi tên cột hay thứ tự dòng, đừng xóa dòng nào.",
        "3. Lưu lại thành file CSV (Excel: Save As, chọn CSV; Google Sheets: Download, chọn CSV).",
        "4. Đổi tên file thành `ten-cua-ban.csv` và gửi lại cho người phụ trách.",
    ]
    return "\n".join(lines) + "\n"


def _is_obvious_arm_pattern(arms: Sequence[str]) -> bool:
    """Chuỗi nhãn quá dễ đoán: nhóm A rồi nhóm B, hoặc xen kẽ đều đặn."""
    if len(arms) < 4:
        return False
    grouped = list(arms) == sorted(arms) or list(arms) == sorted(arms, reverse=True)
    alternating = all(a != b for a, b in zip(arms, arms[1:]))
    return grouped or alternating


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _validate_records(records: Sequence[RunRecord]) -> None:
    if not records:
        raise ValueError("Không có truyện nào để chấm")
    seen: dict[tuple[str, int], Path] = {}
    for record in records:
        if record.arm not in ARMS:
            raise ValueError(f"Nhãn nhóm không hợp lệ: {record.arm!r}")
        key = (record.arm, record.base_seed)
        if key in seen:
            raise ValueError(f"Trùng truyện cho nhóm {record.arm}, base_seed {record.base_seed}")
        if not Path(record.comic_path).is_file():
            raise FileNotFoundError(f"Thiếu file truyện tranh: {record.comic_path.name}")
        seen[key] = record.comic_path
    seeds_a = {seed for arm, seed in seen if arm == "A"}
    seeds_b = {seed for arm, seed in seen if arm == "B"}
    if seeds_a != seeds_b:
        raise ValueError("Mỗi base_seed phải có đủ một truyện A và một truyện B")


def build_blind_pack(
    records: Sequence[RunRecord], out_dir: str | Path, *, shuffle_seed: int
) -> list[dict[str, Any]]:
    """Tạo `for_raters/` (gửi người chấm) và `private/` (khóa A/B, KHÔNG gửi). Trả về các dòng khóa."""
    _validate_records(records)
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Thư mục gói chấm đã có nội dung: dùng thư mục mới")
    for_raters = out / "for_raters"
    private = out / "private"
    (for_raters / "comics").mkdir(parents=True)
    private.mkdir(parents=True)

    rng = random.Random(shuffle_seed)
    order = list(records)
    for _ in range(100):
        rng.shuffle(order)
        if not _is_obvious_arm_pattern([r.arm for r in order]):
            break

    width = len(str(len(order)))
    key_rows: list[dict[str, Any]] = []
    pages: list[Image.Image] = []
    font = ImageFont.load_default(size=40)
    for number, record in enumerate(order, start=1):
        comic_id = f"C{number:0{max(2, width)}d}"
        with Image.open(record.comic_path) as source:
            comic = source.convert("RGB")
        comic.save(for_raters / "comics" / f"{comic_id}.png")  # lưu lại từ điểm ảnh: không mang metadata cũ

        header = 70
        page = Image.new("RGB", (comic.width, comic.height + header), "white")
        ImageDraw.Draw(page).text((20, 12), f"Truyen tranh {comic_id}", fill=(0, 0, 0), font=font)
        page.paste(comic, (0, header))
        pages.append(page)
        key_rows.append({
            "comic_id": comic_id,
            "arm": record.arm,
            "base_seed": record.base_seed,
            "source_comic": Path(record.comic_path).name,
            "source_sha256": _sha256(Path(record.comic_path)),
        })

    pages[0].save(for_raters / "rating_pack.pdf", "PDF", save_all=True, append_images=pages[1:], resolution=100.0)

    with open(for_raters / "rating_sheet.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(SHEET_COLUMNS)
        for row in key_rows:
            writer.writerow([row["comic_id"]] + [""] * (len(SHEET_COLUMNS) - 1))
    (for_raters / "HUONG_DAN_CHAM.md").write_text(rubric_text(len(order)), encoding="utf-8")

    with open(private / "KEY.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(key_rows)
    (private / "pack_info.json").write_text(
        json.dumps({"shuffle_seed": shuffle_seed, "n_comics": len(order)}, indent=2), encoding="utf-8"
    )
    (private / "DOC_TRUOC_KHI_GUI.txt").write_text(
        "Thư mục private/ chứa khóa A/B. KHÔNG gửi cho người chấm; chỉ mở sau khi nhận đủ điểm.\n"
        "Chỉ gửi thư mục for_raters/.\n",
        encoding="utf-8",
    )
    return key_rows


def read_key(pack_dir: str | Path) -> list[dict[str, Any]]:
    with open(Path(pack_dir) / "private" / "KEY.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["base_seed"] = int(row["base_seed"])
    return rows


# ---------------------------------------------------------------------------
# 3. Đọc file điểm
# ---------------------------------------------------------------------------
def _decode(data: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1258"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    return data.decode("latin-1")


def _detect_delimiter(header_line: str) -> str:
    counts = {delimiter: header_line.count(delimiter) for delimiter in (",", ";", "\t")}
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


def read_rating_table(path: str | Path, *, expected_ids: Sequence[str]) -> dict[str, dict[str, int]]:
    """Đọc một file điểm (chịu được dấu phân cách `,` `;` hoặc tab và các bảng mã thường gặp của Excel)."""
    text = _decode(Path(path).read_bytes())
    lines = [line for line in text.splitlines() if line.strip()]
    if not lines:
        raise RatingFileError("File rỗng")
    delimiter = _detect_delimiter(lines[0])
    reader = csv.reader(lines, delimiter=delimiter)
    header = [cell.strip().lower() for cell in next(reader)]

    problems: list[str] = []
    missing_columns = [name for name in ("comic_id",) + FIELD_NAMES if name not in header]
    if missing_columns:
        raise RatingFileError(f"Thiếu cột: {', '.join(missing_columns)}")
    position = {name: header.index(name) for name in header}

    table: dict[str, dict[str, int]] = {}
    expected = set(expected_ids)
    for line_number, cells in enumerate(reader, start=2):
        comic_id = cells[position["comic_id"]].strip() if position["comic_id"] < len(cells) else ""
        if not comic_id:
            continue
        if comic_id not in expected:
            problems.append(f"dòng {line_number}: mã truyện lạ {comic_id!r}")
            continue
        if comic_id in table:
            problems.append(f"dòng {line_number}: trùng mã {comic_id}")
            continue
        values: dict[str, int] = {}
        for field in RATING_FIELDS:
            index = position[field.name]
            raw = cells[index] if index < len(cells) else ""
            number = _parse_int(raw)
            if number is None:
                problems.append(f"{comic_id}, cột {field.name}: cần số nguyên, nhận {raw.strip()!r}")
            elif not field.low <= number <= field.high:
                problems.append(f"{comic_id}, cột {field.name}: {number} ngoài khoảng {field.low}-{field.high}")
            else:
                values[field.name] = number
        if len(values) == len(RATING_FIELDS):
            table[comic_id] = values
    for comic_id in sorted(expected - set(table)):
        if not any(comic_id in problem for problem in problems):
            problems.append(f"thiếu dòng cho {comic_id}")
    if problems:
        shown = problems[:20]
        extra = f" (và {len(problems) - 20} lỗi khác)" if len(problems) > 20 else ""
        raise RatingFileError("; ".join(shown) + extra)
    return table


# ---------------------------------------------------------------------------
# 4. Phân tích
# ---------------------------------------------------------------------------
def exact_sign_test(wins_b: int, wins_a: int) -> float:
    """Kiểm định dấu chính xác hai phía; bỏ qua các cặp hòa. Chỉ mang tính tham khảo khi n nhỏ."""
    n = wins_a + wins_b
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, i) for i in range(min(wins_a, wins_b) + 1))
    return min(1.0, 2 * tail / 2**n)


def _mean(values: Sequence[float]) -> float:
    return sum(values) / len(values)


def _b_better(field: RatingField, diff: float, eps: float = 1e-9) -> int:
    """+1 nếu B tốt hơn A, -1 nếu A tốt hơn B, 0 nếu hòa (xét theo chiều tốt của chỉ số)."""
    if abs(diff) <= eps:
        return 0
    improves = diff > 0 if field.better == "higher" else diff < 0
    return 1 if improves else -1


def analyze_ratings(
    key_rows: Sequence[Mapping[str, Any]], ratings_by_rater: Mapping[str, Mapping[str, Mapping[str, int]]]
) -> dict[str, Any]:
    if not ratings_by_rater:
        raise ValueError("Cần ít nhất một file điểm")
    ids = sorted(row["comic_id"] for row in key_rows)
    key = {row["comic_id"]: row for row in key_rows}
    for rater, table in ratings_by_rater.items():
        if set(table) != set(ids):
            raise ValueError(f"Người chấm {rater} không chấm đủ các truyện")

    raters = list(ratings_by_rater)
    comic_mean = {
        cid: {f.name: _mean([ratings_by_rater[r][cid][f.name] for r in raters]) for f in RATING_FIELDS}
        for cid in ids
    }
    pair: dict[tuple[int, str], str] = {}
    for cid in ids:
        pair[(int(key[cid]["base_seed"]), key[cid]["arm"])] = cid
    seeds = sorted({seed for seed, _ in pair})
    for seed in seeds:
        if (seed, "A") not in pair or (seed, "B") not in pair:
            raise ValueError(f"base_seed {seed} thiếu A hoặc B")

    fields: dict[str, Any] = {}
    for field in RATING_FIELDS:
        a_values = [comic_mean[pair[(seed, "A")]][field.name] for seed in seeds]
        b_values = [comic_mean[pair[(seed, "B")]][field.name] for seed in seeds]
        diffs = [b - a for a, b in zip(a_values, b_values)]
        verdicts = [_b_better(field, d) for d in diffs]
        wins_b, wins_a = verdicts.count(1), verdicts.count(-1)
        fields[field.name] = {
            "better": field.better,
            "primary": field.primary,
            "mean_a": _mean(a_values),
            "mean_b": _mean(b_values),
            "mean_diff_b_minus_a": _mean(diffs),
            "b_better": wins_b,
            "a_better": wins_a,
            "ties": verdicts.count(0),
            "sign_test_p": exact_sign_test(wins_b, wins_a),
        }

    inter_rater: dict[str, Any] = {}
    if len(raters) >= 2:
        for field in RATING_FIELDS:
            gaps, same = [], []
            for first, second in itertools.combinations(raters, 2):
                for cid in ids:
                    x, y = ratings_by_rater[first][cid][field.name], ratings_by_rater[second][cid][field.name]
                    gaps.append(abs(x - y))
                    same.append(1.0 if x == y else 0.0)
            inter_rater[field.name] = {"mean_abs_diff": _mean(gaps), "exact_agreement": _mean(same)}

    per_rater: dict[str, Any] = {}
    for rater in raters:
        per_rater[rater] = {}
        for field in RATING_FIELDS:
            diffs = [
                ratings_by_rater[rater][pair[(seed, "B")]][field.name]
                - ratings_by_rater[rater][pair[(seed, "A")]][field.name]
                for seed in seeds
            ]
            per_rater[rater][field.name] = _mean(diffs)

    return {
        "n_runs": len(seeds),
        "base_seeds": seeds,
        "raters": raters,
        "fields": fields,
        "inter_rater": inter_rater,
        "per_rater_mean_diff_b_minus_a": per_rater,
        "comic_means": comic_mean,
    }


def format_report(analysis: Mapping[str, Any]) -> str:
    n = analysis["n_runs"]
    lines = [
        "# Kết quả so sánh A và B (Task 6)",
        "",
        f"- Số cặp truyện: {n} (mỗi nhóm {n} truyện, mỗi truyện 4 khung); cùng seed và cùng thông số cho A và B.",
        f"- Người chấm ({len(analysis['raters'])}): {', '.join(analysis['raters'])}. Điểm dùng để phân tích là trung bình các người chấm.",
        "- A: prompt độc lập từng cảnh (không có mô tả nhân vật). B: có mô tả nhân vật dùng chung.",
        "",
        "> Đây là thống kê mô tả trên mẫu rất nhỏ, do người chấm theo cảm nhận. Giá trị p của kiểm định dấu chỉ để tham khảo, "
        "không đủ để kết luận phương án nào tốt hơn.",
        "",
    ]
    for title, primary in (("Chỉ số chính (nhất quán giữa các khung)", True), ("Chỉ số phụ", False)):
        lines += [
            f"## {title}",
            "",
            "| Chỉ số | Trung bình A | Trung bình B | B trừ A | B tốt hơn | A tốt hơn | Hòa | p (kiểm định dấu) |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for field in RATING_FIELDS:
            row = analysis["fields"][field.name]
            if row["primary"] != primary:
                continue
            arrow = "cao hơn là tốt" if field.better == "higher" else "thấp hơn là tốt"
            lines.append(
                f"| `{field.name}` ({arrow}) | {row['mean_a']:.2f} | {row['mean_b']:.2f} | "
                f"{row['mean_diff_b_minus_a']:+.2f} | {row['b_better']} | {row['a_better']} | {row['ties']} | "
                f"{row['sign_test_p']:.3f} |"
            )
        lines.append("")
    lines += [
        "Lưu ý về chỉ số phụ `panels_rabbit_red_scarf` và `panels_turtle_green_brown_shell`: prompt của A "
        "không nhắc đến khăn đỏ hay màu rùa, nên A thua ở hai chỉ số này là điều dễ hiểu; chúng đo mức khớp "
        "với thiết kế, không phải độ nhất quán.",
        "",
    ]
    if analysis["inter_rater"]:
        lines += [
            "## Độ đồng thuận giữa người chấm",
            "",
            "| Chỉ số | Sai khác tuyệt đối trung bình | Tỉ lệ chấm trùng nhau |",
            "|---|---|---|",
        ]
        for name, row in analysis["inter_rater"].items():
            lines.append(f"| `{name}` | {row['mean_abs_diff']:.2f} | {row['exact_agreement']:.0%} |")
        lines.append("")
    lines += ["## B trừ A theo từng người chấm", "", "| Người chấm | " + " | ".join(f"`{n_}`" for n_ in FIELD_NAMES) + " |",
              "|---|" + "---|" * len(FIELD_NAMES)]
    for rater, values in analysis["per_rater_mean_diff_b_minus_a"].items():
        lines.append(f"| {rater} | " + " | ".join(f"{values[n_]:+.2f}" for n_ in FIELD_NAMES) + " |")
    lines += [
        "",
        "Nếu các người chấm cho hướng chênh lệch ngược nhau, kết quả không đáng tin dù trung bình trông rõ ràng.",
        "",
    ]
    return "\n".join(lines)


def write_analysis(
    analysis: Mapping[str, Any], key_rows: Sequence[Mapping[str, Any]], out_dir: str | Path
) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    (out / "summary.md").write_text(format_report(analysis), encoding="utf-8")
    (out / "analysis.json").write_text(json.dumps(analysis, indent=2, ensure_ascii=False), encoding="utf-8")
    with open(out / "per_comic.csv", "w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["comic_id", "arm", "base_seed"] + list(FIELD_NAMES))
        for row in sorted(key_rows, key=lambda r: (int(r["base_seed"]), r["arm"])):
            means = analysis["comic_means"][row["comic_id"]]
            writer.writerow([row["comic_id"], row["arm"], row["base_seed"]] + [f"{means[n_]:.2f}" for n_ in FIELD_NAMES])
