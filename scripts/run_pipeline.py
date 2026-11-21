"""CPU mock integration demo; không phải LLM/diffusion inference."""

import argparse
from pathlib import Path
import sys

# Hỗ trợ chạy file từ bất kỳ cwd; không phụ thuộc PYTHONPATH của shell.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.factory import PipelineConfig, build_pipeline

# Independent sample input, exact matching fixture contract; không thay fixture summary.
SAMPLE_SUMMARY = "Thỏ thách rùa thi chạy. Thỏ chủ quan ngủ quên giữa đường, còn rùa kiên trì về đích và chiến thắng."


def main() -> None:
    """Gọi shared factory/pipeline một lần và in actual comic PNG path."""
    parser = argparse.ArgumentParser(description="CPU mock four-panel comic smoke test")
    parser.add_argument("--output-dir", default="outputs")
    parser.add_argument("--base-seed", type=int, default=42)
    args = parser.parse_args()
    pipeline = build_pipeline(PipelineConfig(output_dir=args.output_dir, base_seed=args.base_seed))
    result = pipeline.generate(SAMPLE_SUMMARY)
    print(result.comic_path)


if __name__ == "__main__":
    main()
