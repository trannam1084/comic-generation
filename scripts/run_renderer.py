import json
from pathlib import Path

from src.comic_renderer.renderer import ComicRenderer
from src.image_generator.image_generator import MockImageGenerator
from src.image_generator.prompt_builder import PromptBuilder
from src.image_generator.schemas import Storyboard

storyboard = Storyboard.from_dict(
    json.loads(Path("data/storyboard_sample.json").read_text(encoding="utf-8"))
)
prompts = PromptBuilder().build(storyboard)
images = MockImageGenerator().generate_all(prompts)
captions = [scene.caption_vi for scene in storyboard.scenes]

renderer = ComicRenderer()
result = renderer.render(images, captions)
for path in renderer.save(result, Path("outputs/render_test")):
    print(path)
print("font sizes:", result.font_sizes)