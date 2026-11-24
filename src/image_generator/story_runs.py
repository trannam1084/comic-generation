"""Chạy pipeline thật cho các Storyboard đã duyệt; mỗi truyện một thư mục artifacts.

Không sinh lại truyện, không retry, không thay ảnh lỗi bằng mock. Lỗi của từng truyện
được ghi vào metadata.json rồi chạy tiếp truyện sau.
"""

from __future__ import annotations

import hashlib
import json
import re
import time
import traceback
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.configuration import PipelineConfig
from src.factory import build_pipeline
from src.pipeline import PromptStage
from src.storyboard.schema import Storyboard

_STORY_ID = re.compile(r"[A-Za-z0-9_-]+")


class FixedStoryStage:
    """StoryStage trả về đúng Storyboard đã duyệt (không gọi LLM)."""

    def __init__(self, storyboard: Storyboard) -> None:
        self._data = Storyboard.model_validate(storyboard).model_dump()

    def generate(self, summary: str) -> Storyboard:
        """Trả bản mới của storyboard; summary phải khớp storyboard gốc."""
        story = Storyboard.model_validate(self._data)
        if summary != story.summary:
            raise ValueError("Summary không khớp storyboard cố định.")
        return story


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _write_json(path: Path, data: Any) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def _write_sums(story_dir: Path) -> None:
    files = sorted(p for p in story_dir.rglob("*") if p.is_file() and p.name != "SHA256SUMS")
    lines = [f"{_sha256(p)}  {p.relative_to(story_dir).as_posix()}" for p in files]
    (story_dir / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_story(
    story_id: str,
    storyboard_data: Mapping[str, Any],
    *,
    image_backend: Any,
    out_root: str | Path,
    base_seed: int,
    prompt_stage: PromptStage | None = None,
    run_info: Mapping[str, Any] | None = None,
    reset_peak: Callable[[], None] | None = None,
    read_peak_gib: Callable[[], float] | None = None,
) -> dict[str, Any]:
    """Chạy một truyện, ghi artifacts vào out_root/story_id, trả về metadata.

    Lỗi trong quá trình chạy được ghi (status="error" + traceback), không ném ra ngoài
    và không có ảnh thay thế. Thư mục đã tồn tại thì FileExistsError để không ghi đè.
    """
    if not isinstance(story_id, str) or not _STORY_ID.fullmatch(story_id):
        raise ValueError("story_id chỉ gồm chữ, số, '_' và '-'.")
    story_dir = Path(out_root) / story_id
    if story_dir.exists():
        raise FileExistsError(f"Thư mục đã tồn tại, không ghi đè: {story_dir}")
    (story_dir / "raw").mkdir(parents=True)

    record: dict[str, Any] = {
        "story_id": story_id,
        "status": "error",
        "stage": "storyboard",
        "started_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_seed": base_seed,
        "run": dict(run_info or {}),
        "quality_notes": None,  # người chạy tự điền sau khi xem ảnh
    }
    try:
        storyboard = Storyboard.model_validate(storyboard_data)
        _write_json(story_dir / "storyboard.json", storyboard.model_dump(mode="json"))

        record["stage"] = "pipeline"
        config = PipelineConfig(output_dir=story_dir / "comic", base_seed=base_seed)
        pipeline = build_pipeline(
            config,
            story_stage=FixedStoryStage(storyboard),
            prompt_stage=prompt_stage,
            image_backend=image_backend,
        )
        if reset_peak is not None:
            reset_peak()
        start = time.perf_counter()
        try:
            result = pipeline.generate(storyboard.summary)
        finally:
            record["pipeline_sec"] = round(time.perf_counter() - start, 2)
            if read_peak_gib is not None:
                record["peak_vram_gib"] = round(read_peak_gib(), 2)

        captions = {scene.index: scene.caption_vi for scene in storyboard.scenes}
        scenes = []
        for generated, prompt in zip(result.images, result.prompts):
            generated.image.save(story_dir / "raw" / f"scene_{generated.scene_index}.png")
            scenes.append(
                {
                    "scene_index": generated.scene_index,
                    "caption_vi": captions[generated.scene_index],
                    "seed": generated.seed,
                    "backend": generated.backend,
                    "elapsed_sec": round(generated.elapsed_sec, 2),
                    "prompt": prompt.prompt,
                    "negative_prompt": prompt.negative_prompt,
                    "params": generated.params,
                }
            )
        try:
            comic = result.comic_path.relative_to(story_dir).as_posix()
        except ValueError:
            comic = str(result.comic_path)
        record.update({"status": "success", "stage": "done", "comic_path": comic, "scenes": scenes})
    except Exception as exc:  # noqa: BLE001 - ghi nguyên nhân rồi chạy tiếp truyện sau
        record.update(
            {
                "error_type": type(exc).__name__,
                "error_message": str(exc),
                "traceback": traceback.format_exc(),
            }
        )

    _write_json(story_dir / "metadata.json", record)
    _write_sums(story_dir)
    return record


def run_stories(
    stories: Mapping[str, Mapping[str, Any]],
    *,
    out_root: str | Path,
    cleanup: Callable[[], None] | None = None,
    **kwargs: Any,
) -> list[dict[str, Any]]:
    """Chạy lần lượt các truyện theo thứ tự đưa vào; truyện lỗi không chặn truyện sau."""
    if not stories:
        raise ValueError("Cần ít nhất một storyboard.")
    results = []
    for story_id, data in stories.items():
        try:
            results.append(run_story(story_id, data, out_root=out_root, **kwargs))
        finally:
            if cleanup is not None:
                cleanup()
    summary = [
        {key: item.get(key) for key in ("story_id", "status", "stage", "pipeline_sec", "peak_vram_gib", "error_type")}
        for item in results
    ]
    _write_json(Path(out_root) / "summary.json", summary)
    return results