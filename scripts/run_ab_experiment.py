"""Công cụ cho thí nghiệm Task 6 (A/B), chạy trên máy cá nhân (CPU).

Tạo gói chấm ẩn nhãn từ kết quả đã tải về từ Kaggle:
    python -m scripts.run_ab_experiment blind --results-dir <thư mục có manifest.json> --out-dir <thư mục mới> --shuffle-seed 2026

Phân tích sau khi nhận đủ file điểm (mở nhãn A/B):
    python -m scripts.run_ab_experiment analyze --pack-dir <thư mục gói> --ratings <file1.csv> <file2.csv> --out-dir <thư mục kết quả>
"""

from __future__ import annotations

import argparse
from pathlib import Path

from src.image_generator import ab_experiment as ab


def cmd_blind(args: argparse.Namespace) -> None:
    records = ab.load_records(args.results_dir)
    key_rows = ab.build_blind_pack(records, args.out_dir, shuffle_seed=args.shuffle_seed)
    print(f"Đã tạo gói chấm cho {len(key_rows)} truyện tại {args.out_dir}")
    print(f"- Gửi cho người chấm: {Path(args.out_dir) / 'for_raters'}")
    print(f"- GIỮ RIÊNG (khóa A/B): {Path(args.out_dir) / 'private'}")


def cmd_analyze(args: argparse.Namespace) -> None:
    key_rows = ab.read_key(args.pack_dir)
    ids = [row["comic_id"] for row in key_rows]
    ratings: dict[str, dict] = {}
    for path in args.ratings:
        name = Path(path).stem
        if name in ratings:
            raise SystemExit(f"Hai file điểm trùng tên người chấm: {name}")
        try:
            ratings[name] = ab.read_rating_table(path, expected_ids=ids)
        except ab.RatingFileError as exc:
            raise SystemExit(f"{path}: {exc}") from exc
    analysis = ab.analyze_ratings(key_rows, ratings)
    ab.write_analysis(analysis, key_rows, args.out_dir)
    print(f"Đã ghi kết quả vào {args.out_dir} (summary.md, analysis.json, per_comic.csv)")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Công cụ thí nghiệm A/B (Task 6)")
    sub = parser.add_subparsers(dest="command", required=True)

    blind = sub.add_parser("blind", help="tạo gói chấm ẩn nhãn")
    blind.add_argument("--results-dir", required=True)
    blind.add_argument("--out-dir", required=True)
    blind.add_argument("--shuffle-seed", type=int, required=True)
    blind.set_defaults(func=cmd_blind)

    analyze = sub.add_parser("analyze", help="mở nhãn và phân tích điểm")
    analyze.add_argument("--pack-dir", required=True)
    analyze.add_argument("--ratings", nargs="+", required=True)
    analyze.add_argument("--out-dir", required=True)
    analyze.set_defaults(func=cmd_analyze)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
