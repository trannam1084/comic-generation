

"""Evaluation metrics for Vietnamese story-to-comic generation."""
from src.storyboard.validator import StoryboardValidator
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
import re
import unicodedata


@dataclass(frozen=True)
class RateMetric:
    """Stores a metric numerator, denominator and rate."""

    numerator: int
    denominator: int
    rate: float | None

    @property
    def percentage(self) -> float | None:
        """Return the rate as a percentage."""
        if self.rate is None:
            return None
        return self.rate * 100


def _extract_scenes(output: object) -> object:
    """
    Extract scenes from a JSON string, dictionary or Storyboard object.

    Invalid or missing outputs return None.
    """
    if output is None:
        return None

    if isinstance(output, str):
        try:
            output = json.loads(output)
        except json.JSONDecodeError:
            return None

    if isinstance(output, Mapping):
        return output.get("scenes")

    return getattr(output, "scenes", None)


def four_scene_rate(outputs: Sequence[object]) -> RateMetric:
    """
    Calculate Four Scene Rate over all planned cases.

    Each element represents exactly one planned case.
    Use None when generation failed or no output was produced.

    A case passes when its output contains exactly four scenes.
    This metric checks scene count only, not full schema validity.

    Rate = cases with exactly four scenes / all planned cases.
    """
    if isinstance(outputs, (str, bytes, bytearray)) or not isinstance(
        outputs, Sequence
    ):
        raise TypeError("outputs must be a sequence with one entry per planned case.")

    denominator = len(outputs)
    numerator = 0

    for output in outputs:
        scenes = _extract_scenes(output)

        if isinstance(scenes, list) and len(scenes) == 4:
            numerator += 1

    rate = numerator / denominator if denominator > 0 else None

    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
    )

def schema_valid_rate(outputs: Sequence[object]) -> RateMetric:
    """
    Calculate Schema Valid Rate over all planned cases.

    Each element represents one planned case.
    Expected input is the raw JSON string returned by the story generator.

    None, non-string values, invalid JSON and schema-invalid records
    count as failures. They remain in the denominator.

    Warnings do not invalidate the schema.

    Rate = valid JSON + valid Shared Storyboard Schema / all planned cases.
    """
    if isinstance(outputs, (str, bytes, bytearray)) or not isinstance(
        outputs, Sequence
    ):
        raise TypeError("outputs must be a sequence with one entry per planned case.")

    validator = StoryboardValidator()
    denominator = len(outputs)
    numerator = 0

    for output in outputs:
        if not isinstance(output, str):
            continue

        report = validator.validate_raw(output)

        if (
            report.json_syntax == "passed"
            and report.structural_validity == "passed"
        ):
            numerator += 1

    rate = numerator / denominator if denominator > 0 else None

    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
    )

def _extract_captions(output: object) -> list[str]:
    """Extract caption_vi from at most the first four scenes."""
    scenes = _extract_scenes(output)

    if not isinstance(scenes, Sequence) or isinstance(
        scenes, (str, bytes, bytearray)
    ):
        return []

    captions = []

    for scene in scenes[:4]:
        if isinstance(scene, Mapping):
            caption = scene.get("caption_vi")
        else:
            caption = getattr(scene, "caption_vi", None)

        if isinstance(caption, str) and caption.strip():
            captions.append(caption)

    return captions


def _normalize_keyword_text(value: str) -> str:
    """Normalize Unicode, case and whitespace while preserving Vietnamese accents."""
    value = unicodedata.normalize("NFC", value)
    return " ".join(value.casefold().split())


def _contains_keyword_phrase(text: str, phrase: str) -> bool:
    """Check whether a complete keyword phrase appears in the text."""
    words = phrase.split()

    if not words:
        return False

    pattern = (
        r"(?<!\w)"
        + r"\s+".join(re.escape(word) for word in words)
        + r"(?!\w)"
    )

    return re.search(pattern, text) is not None


def keyword_recall(
    outputs: Sequence[object],
    keyword_groups_by_case: Sequence[Sequence[Sequence[str]]],
) -> RateMetric:
    """
    Calculate micro-averaged keyword recall across all cases.

    Each case has a corresponding list of keyword groups.
    A group is covered when at least one alias appears in its captions.
    Only caption_vi from the first four scenes is evaluated.
    """
    if isinstance(outputs, (str, bytes, bytearray)) or not isinstance(
        outputs, Sequence
    ):
        raise TypeError("outputs must be a sequence")

    if isinstance(
        keyword_groups_by_case, (str, bytes, bytearray)
    ) or not isinstance(keyword_groups_by_case, Sequence):
        raise TypeError("keyword_groups_by_case must be a sequence")

    if len(outputs) != len(keyword_groups_by_case):
        raise ValueError(
            "outputs and keyword_groups_by_case must have the same length"
        )

    numerator = 0
    denominator = 0

    for output, case_groups in zip(
        outputs, keyword_groups_by_case, strict=True
    ):
        if isinstance(case_groups, (str, bytes, bytearray)) or not isinstance(
            case_groups, Sequence
        ):
            raise TypeError("Each case must contain a sequence of keyword groups")

        captions = _extract_captions(output)
        caption_text = _normalize_keyword_text(" ".join(captions))

        for group in case_groups:
            if isinstance(group, (str, bytes, bytearray)) or not isinstance(
                group, Sequence
            ):
                raise TypeError("Each keyword group must be a sequence of aliases")

            if not group:
                raise ValueError("A keyword group cannot be empty")

            aliases = []

            for alias in group:
                if not isinstance(alias, str):
                    raise TypeError("Every keyword alias must be a string")

                normalized_alias = _normalize_keyword_text(alias)

                if not normalized_alias:
                    raise ValueError("A keyword alias cannot be empty")

                aliases.append(normalized_alias)

            denominator += 1

            if any(
                _contains_keyword_phrase(caption_text, alias)
                for alias in aliases
            ):
                numerator += 1

    rate = numerator / denominator if denominator > 0 else None

    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
    )

def event_coverage(annotations_by_case: Sequence[object]) -> RateMetric:
    """
    Calculate micro-averaged Event Coverage from adjudicated human labels.

    Each case contains:
        {
            "case_id": "story_001",
            "events": [
                {
                    "event_id": "E1",
                    "annotator_1_label": "covered",
                    "annotator_2_label": "covered",
                    "adjudicated_label": "covered"
                }
            ]
        }

    Allowed labels: covered, not_covered, uncertain.
    Uncertain remains in the denominator but not the numerator.
    """
    if isinstance(
        annotations_by_case, (str, bytes, bytearray)
    ) or not isinstance(annotations_by_case, Sequence):
        raise TypeError("annotations_by_case must be a sequence")

    allowed_labels = {"covered", "not_covered", "uncertain"}
    numerator = 0
    denominator = 0
    seen_case_ids: set[str] = set()

    for case in annotations_by_case:
        if not isinstance(case, Mapping):
            raise TypeError("Each case annotation must be a mapping")

        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Each case must have a non-empty case_id")
        if case_id in seen_case_ids:
            raise ValueError(f"Duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)

        events = case.get("events")
        if isinstance(events, (str, bytes, bytearray)) or not isinstance(
            events, Sequence
        ):
            raise TypeError("Each case must contain a sequence of events")
        if not events:
            raise ValueError("A case must contain at least one reference event")

        seen_event_ids: set[str] = set()

        for event in events:
            if not isinstance(event, Mapping):
                raise TypeError("Each event annotation must be a mapping")

            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("Each event must have a non-empty event_id")
            if event_id in seen_event_ids:
                raise ValueError(
                    f"Duplicate event_id in case {case_id}: {event_id}"
                )
            seen_event_ids.add(event_id)

            for field in (
                "annotator_1_label",
                "annotator_2_label",
                "adjudicated_label",
            ):
                label = event.get(field)
                if not isinstance(label, str) or label not in allowed_labels:
                    raise ValueError(
                        f"{field} must be one of {sorted(allowed_labels)}"
                    )

            denominator += 1
            if event["adjudicated_label"] == "covered":
                numerator += 1

    rate = numerator / denominator if denominator > 0 else None
    return RateMetric(
        numerator=numerator,
        denominator=denominator,
        rate=rate,
    )


@dataclass(frozen=True)
class EventOrderMetric:
    """Pairwise event-order scores and their evaluability coverage."""

    correct_pairs: int
    evaluable_pairs: int
    total_reference_pairs: int
    same_scene_pairs: int
    accuracy: float | None
    pair_coverage: float | None

    @property
    def accuracy_percentage(self) -> float | None:
        if self.accuracy is None:
            return None
        return self.accuracy * 100

    @property
    def pair_coverage_percentage(self) -> float | None:
        if self.pair_coverage is None:
            return None
        return self.pair_coverage * 100


def _validate_event_scene_index(
    label: str,
    scene_index: object,
    *,
    field_name: str,
    event_id: str,
) -> None:
    """Require scene 1-4 for covered events; require None otherwise."""
    if label == "covered":
        if type(scene_index) is not int or scene_index not in (1, 2, 3, 4):
            raise ValueError(
                f"{field_name} must be an integer from 1 to 4 when event "
                f"{event_id} is covered"
            )
    elif scene_index is not None:
        raise ValueError(
            f"{field_name} must be None when event {event_id} is "
            f"{label}"
        )


def event_order(
    annotations_by_case: Sequence[object],
) -> EventOrderMetric:
    """
    Calculate pairwise Event Order Accuracy and Order Pair Coverage.

    Each case contains events with explicit reference_order (1-based),
    the three adjudication labels, and each annotator's observed scene
    index plus the adjudicated scene index.

    A pair is evaluable only when both events are adjudicated as covered,
    both have a scene index, and they occur in different scenes. Events
    placed in the same scene are counted separately and excluded from
    accuracy because their within-scene order is not observable.

    Accuracy = correctly ordered evaluable pairs / evaluable pairs.
    Pair Coverage = evaluable pairs / all reference event pairs.

    Comparisons are within each story only, never across stories.
    """
    if isinstance(
        annotations_by_case, (str, bytes, bytearray)
    ) or not isinstance(annotations_by_case, Sequence):
        raise TypeError("annotations_by_case must be a sequence")

    allowed_labels = {"covered", "not_covered", "uncertain"}
    seen_case_ids: set[str] = set()
    correct_pairs = 0
    evaluable_pairs = 0
    total_reference_pairs = 0
    same_scene_pairs = 0

    for case in annotations_by_case:
        if not isinstance(case, Mapping):
            raise TypeError("Each case annotation must be a mapping")

        case_id = case.get("case_id")
        if not isinstance(case_id, str) or not case_id.strip():
            raise ValueError("Each case must have a non-empty case_id")
        if case_id in seen_case_ids:
            raise ValueError(f"Duplicate case_id: {case_id}")
        seen_case_ids.add(case_id)

        events = case.get("events")
        if isinstance(events, (str, bytes, bytearray)) or not isinstance(
            events, Sequence
        ):
            raise TypeError("Each case must contain a sequence of events")
        if not events:
            raise ValueError("A case must contain at least one reference event")

        prepared_events: list[dict[str, object]] = []
        seen_event_ids: set[str] = set()
        seen_reference_orders: set[int] = set()

        for event in events:
            if not isinstance(event, Mapping):
                raise TypeError("Each event annotation must be a mapping")

            event_id = event.get("event_id")
            if not isinstance(event_id, str) or not event_id.strip():
                raise ValueError("Each event must have a non-empty event_id")
            if event_id in seen_event_ids:
                raise ValueError(
                    f"Duplicate event_id in case {case_id}: {event_id}"
                )
            seen_event_ids.add(event_id)

            reference_order = event.get("reference_order")
            if type(reference_order) is not int or reference_order < 1:
                raise ValueError(
                    f"reference_order for {event_id} must be a positive integer"
                )
            if reference_order in seen_reference_orders:
                raise ValueError(
                    f"Duplicate reference_order in case {case_id}: "
                    f"{reference_order}"
                )
            seen_reference_orders.add(reference_order)

            labels: dict[str, str] = {}
            for field in (
                "annotator_1_label",
                "annotator_2_label",
                "adjudicated_label",
            ):
                label = event.get(field)
                if not isinstance(label, str) or label not in allowed_labels:
                    raise ValueError(
                        f"{field} must be one of {sorted(allowed_labels)}"
                    )
                labels[field] = label

            scene_fields = (
                ("annotator_1_label", "annotator_1_scene_index"),
                ("annotator_2_label", "annotator_2_scene_index"),
                ("adjudicated_label", "adjudicated_scene_index"),
            )
            for label_field, scene_field in scene_fields:
                _validate_event_scene_index(
                    labels[label_field],
                    event.get(scene_field),
                    field_name=scene_field,
                    event_id=event_id,
                )

            prepared_events.append(
                {
                    "event_id": event_id,
                    "reference_order": reference_order,
                    "adjudicated_label": labels["adjudicated_label"],
                    "adjudicated_scene_index": event.get(
                        "adjudicated_scene_index"
                    ),
                }
            )

        prepared_events.sort(key=lambda item: item["reference_order"])
        count = len(prepared_events)
        total_reference_pairs += count * (count - 1) // 2

        for earlier_position in range(count):
            for later_position in range(earlier_position + 1, count):
                earlier = prepared_events[earlier_position]
                later = prepared_events[later_position]

                if (
                    earlier["adjudicated_label"] != "covered"
                    or later["adjudicated_label"] != "covered"
                ):
                    continue

                earlier_scene = earlier["adjudicated_scene_index"]
                later_scene = later["adjudicated_scene_index"]

                if earlier_scene == later_scene:
                    same_scene_pairs += 1
                    continue

                evaluable_pairs += 1
                if earlier_scene < later_scene:
                    correct_pairs += 1

    accuracy = (
        correct_pairs / evaluable_pairs if evaluable_pairs > 0 else None
    )
    pair_coverage = (
        evaluable_pairs / total_reference_pairs
        if total_reference_pairs > 0
        else None
    )

    return EventOrderMetric(
        correct_pairs=correct_pairs,
        evaluable_pairs=evaluable_pairs,
        total_reference_pairs=total_reference_pairs,
        same_scene_pairs=same_scene_pairs,
        accuracy=accuracy,
        pair_coverage=pair_coverage,
    )
