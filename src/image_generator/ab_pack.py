"""Gói chấm ẩn nhãn hai tầng cho thí nghiệm Task 6 (nhiều truyện).

Tầng lõi (`core`) là seed đầu tiên trong `base_seeds`, bắt buộc chấm. Tầng bổ sung (`extra`) là các seed còn lại,
chỉ chấm nếu còn thời gian. Mỗi tầng có thư mục riêng, mã truyện riêng (C.. cho core, E.. cho extra), phiếu riêng.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path
from typing import Any, Mapping, Sequence

from PIL import Image, ImageDraw, ImageFont

from src.image_generator.ab_experiment import (
    RunRecord,
    _is_obvious_arm_pattern,
    _sha256,
    _validate_records,
)
from src.image_generator.ab_rubric import (
    COMIC_ROW_NO,
    RATING_FIELDS,
    RatedCharacter,
    SheetRow,
    rated_characters,
    sheet_rows_for_comic,
    write_rating_sheet,
)

TIER_PREFIX = {"core": "C", "extra": "E"}


def split_tiers(records: Sequence[RunRecord], base_seeds: Sequence[int]) -> dict[str, list[RunRecord]]:
    """Seed đầu tiên của `base_seeds` là tầng lõi; các seed còn lại là tầng bổ sung (bỏ tầng rỗng)."""
    seeds = list(base_seeds)
    if not seeds:
        raise ValueError("Cần ít nhất một base_seed")
    tiers: dict[str, list[RunRecord]] = {"core": [], "extra": []}
    for record in records:
        if record.base_seed not in seeds:
            raise ValueError(f"base_seed {record.base_seed} của truyện {record.story_id!r} không nằm trong base_seeds")
        tiers["core" if record.base_seed == seeds[0] else "extra"].append(record)
    return {tier: items for tier, items in tiers.items() if items}


def rubric_text(tier: str, entries: Sequence[tuple[str, Sequence[RatedCharacter]]]) -> str:
    """Hướng dẫn chấm cho một tầng; liệt kê nhân vật cần chấm của từng truyện (mô tả giống nhau ở A và B)."""
    lines = [
        "# Hướng dẫn chấm truyện tranh",
        "",
        f"Bạn sẽ xem {len(entries)} truyện tranh (mã {entries[0][0]}, ...) trong `rating_pack.pdf` "
        "(hoặc các ảnh trong thư mục `comics/`). Mỗi truyện có 4 khung. Điền điểm vào `rating_sheet.csv`.",
        "",
        "## Nguyên tắc",
        "- Chấm MỘT MÌNH, không bàn với ai trước khi nộp. Không đoán hay hỏi truyện nào được tạo bằng cách nào.",
        "- Chỉ chấm các khung có GIỐNG NHAU hay không. Mô tả nhân vật bên dưới chỉ để bạn biết nhân vật là ai, "
        "không phải để chấm ảnh có khớp mô tả hay không. Không chấm theo việc truyện đẹp hay xấu.",
        "- Nếu không chắc, chọn giá trị gần đúng nhất và ghi chú vào cột `notes`.",
        "",
        "## Cách điền (mỗi truyện có nhiều dòng trong phiếu)",
        "- Dòng `char_no = 0` (toàn truyện): điền các cột `panels_*`; để trống cột `identity_consistency`.",
        "- Dòng `char_no = 1, 2, ...` (từng nhân vật): chỉ điền `identity_consistency`; để trống các cột `panels_*`.",
        "",
        "## Ý nghĩa các cột (chỉ điền số nguyên)",
    ]
    for field in RATING_FIELDS:
        na = " hoặc NA" if field.allow_na else ""
        where = "dòng nhân vật" if field.scope == "character" else "dòng toàn truyện"
        lines.append(f"- `{field.name}` ({where}; từ {field.low} đến {field.high}{na}): {field.question}")
    lines += ["", "## Danh sách nhân vật cần chấm theo từng truyện", ""]
    for comic_id, characters in entries:
        lines.append(f"### {comic_id}")
        if characters:
            for c in characters:
                lines.append(f"- `char_no {c.char_no}` — {c.character_id}: {c.visual}")
        else:
            lines.append("- Không có nhân vật nào cần chấm nhất quán; chỉ điền dòng toàn truyện.")
        lines.append("")
    lines += [
        "## Cách nộp",
        "1. Mở `rating_sheet.csv` bằng Excel hoặc Google Sheets và điền vào các ô theo hướng dẫn trên.",
        "2. Đừng đổi tên cột, thứ tự dòng, đừng xóa dòng nào.",
        "3. Lưu thành CSV (Excel: Save As, chọn CSV; Google Sheets: Download, chọn CSV).",
        "4. Đổi tên file thành `ten-cua-ban.csv` và gửi lại cho người phụ trách.",
    ]
    return "\n".join(lines) + "\n"


def _build_tier_pack(
    records: Sequence[RunRecord],
    storyboards: Mapping[str, Mapping[str, Any]],
    tier_dir: Path,
    prefix: str,
    shuffle_seed: int,
) -> list[dict[str, Any]]:
    _validate_records(records)
    for_raters = tier_dir / "for_raters"
    private = tier_dir / "private"
    (for_raters / "comics").mkdir(parents=True)
    private.mkdir(parents=True)

    rng = random.Random(shuffle_seed)
    order = list(records)
    for _ in range(100):
        rng.shuffle(order)
        if not _is_obvious_arm_pattern([r.arm for r in order]):
            break

    width = max(2, len(str(len(order))))
    font = ImageFont.load_default(size=40)
    key_rows: list[dict[str, Any]] = []
    sheet_rows: list[SheetRow] = []
    entries: list[tuple[str, list[RatedCharacter]]] = []
    pages: list[Image.Image] = []
    for number, record in enumerate(order, start=1):
        comic_id = f"{prefix}{number:0{width}d}"
        storyboard = storyboards[record.story_id]
        with Image.open(record.comic_path) as source:
            comic = source.convert("RGB")
        comic.save(for_raters / "comics" / f"{comic_id}.png")  # lưu lại từ điểm ảnh: không mang metadata cũ

        header = 70
        page = Image.new("RGB", (comic.width, comic.height + header), "white")
        ImageDraw.Draw(page).text((20, 12), f"Truyen tranh {comic_id}", fill=(0, 0, 0), font=font)  # chỉ ASCII
        page.paste(comic, (0, header))
        pages.append(page)

        sheet_rows += sheet_rows_for_comic(comic_id, storyboard)
        entries.append((comic_id, rated_characters(storyboard)))
        key_rows.append({
            "comic_id": comic_id,
            "story_id": record.story_id,
            "arm": record.arm,
            "base_seed": record.base_seed,
            "source_run": f"{record.story_id}/{record.arm}_seed{record.base_seed}",
            "source_sha256": _sha256(Path(record.comic_path)),
        })

    pages[0].save(for_raters / "rating_pack.pdf", "PDF", save_all=True, append_images=pages[1:], resolution=100.0)
    write_rating_sheet(for_raters / "rating_sheet.csv", sheet_rows)
    (for_raters / "HUONG_DAN_CHAM.md").write_text(rubric_text(prefix, entries), encoding="utf-8")

    with open(private / "KEY.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(key_rows[0]))
        writer.writeheader()
        writer.writerows(key_rows)
    with open(private / "EXPECTED_ROWS.csv", "w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["comic_id", "char_no", "label"])
        for row in sheet_rows:
            writer.writerow([row.comic_id, row.char_no, row.label])
    (private / "pack_info.json").write_text(
        json.dumps({"shuffle_seed": shuffle_seed, "n_comics": len(order)}, indent=2), encoding="utf-8"
    )
    (private / "DOC_TRUOC_KHI_GUI.txt").write_text(
        "Thư mục private/ chứa khóa A/B. KHÔNG gửi cho người chấm; chỉ mở sau khi nhận đủ điểm.\n"
        "Chỉ gửi thư mục for_raters/.\n",
        encoding="utf-8",
    )
    return key_rows


def build_blind_packs(
    records: Sequence[RunRecord],
    storyboards: Mapping[str, Mapping[str, Any]],
    base_seeds: Sequence[int],
    out_dir: str | Path,
    *,
    shuffle_seed: int,
) -> dict[str, list[dict[str, Any]]]:
    """Tạo `out_dir/core/` và (nếu có nhiều seed) `out_dir/extra/`, mỗi thư mục gồm `for_raters/` và `private/`.

    Trả về {tầng: các dòng khóa}. Chỉ gửi `for_raters/` cho người chấm.
    """
    _validate_records(records)
    for record in records:
        if record.story_id not in storyboards:
            raise ValueError(f"Thiếu storyboard cho story_id {record.story_id!r}")
    out = Path(out_dir)
    if out.exists() and any(out.iterdir()):
        raise FileExistsError("Thư mục gói chấm đã có nội dung: dùng thư mục mới")
    tiers = split_tiers(records, base_seeds)
    return {
        tier: _build_tier_pack(items, storyboards, out / tier, TIER_PREFIX[tier], shuffle_seed + offset)
        for offset, (tier, items) in enumerate(tiers.items())
    }


def read_pack_key(tier_dir: str | Path) -> list[dict[str, Any]]:
    with open(Path(tier_dir) / "private" / "KEY.csv", encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        row["base_seed"] = int(row["base_seed"])
    return rows


def read_expected_rows(tier_dir: str | Path) -> list[SheetRow]:
    with open(Path(tier_dir) / "private" / "EXPECTED_ROWS.csv", encoding="utf-8", newline="") as handle:
        return [SheetRow(r["comic_id"], int(r["char_no"]), r["label"]) for r in csv.DictReader(handle)]