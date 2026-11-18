import json
from pathlib import Path

from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import Storyboard

path = Path("data/storyboard_sample.json")
sb = Storyboard.from_dict(json.loads(path.read_text(encoding="utf-8")))

for p in PromptBuilder().build(sb):
    print(f"[Scene {p.scene_index}] {p.prompt}\n")