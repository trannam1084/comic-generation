import json
import logging
from pathlib import Path

from src.image_generator.image_generator import MockImageGenerator
from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import Storyboard


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    sb = Storyboard.from_dict(
        json.loads(Path("data/storyboard_sample.json").read_text(encoding="utf-8"))
    )
    prompts = PromptBuilder().build(sb)
    results = MockImageGenerator().generate_all(prompts)

    out = Path("outputs/mock")
    out.mkdir(parents=True, exist_ok=True)
    for r in results:
        path = out / f"scene_{r.scene_index}.png"
        r.image.save(path)
        print(f"{path}  backend={r.backend}  seed={r.seed}  {r.elapsed_sec * 1000:.1f} ms")


if __name__ == "__main__":
    main()