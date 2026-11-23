import pytest

from src.evaluation.metrics import event_order


def make_order_event(
    event_id,
    reference_order,
    *,
    annotator_1_label="covered",
    annotator_2_label="covered",
    adjudicated_label="covered",
    annotator_1_scene_index=1,
    annotator_2_scene_index=1,
    adjudicated_scene_index=1,
):
    return {
        "event_id": event_id,
        "reference_order": reference_order,
        "annotator_1_label": annotator_1_label,
        "annotator_2_label": annotator_2_label,
        "adjudicated_label": adjudicated_label,
        "annotator_1_scene_index": annotator_1_scene_index,
        "annotator_2_scene_index": annotator_2_scene_index,
        "adjudicated_scene_index": adjudicated_scene_index,
    }


def make_order_case(events, case_id="story_001"):
    return {"case_id": case_id, "events": events}


def test_event_order_all_pairs_correct():
    case = make_order_case([
        make_order_event("E1", 1, annotator_1_scene_index=1,
                         annotator_2_scene_index=1, adjudicated_scene_index=1),
        make_order_event("E2", 2, annotator_1_scene_index=2,
                         annotator_2_scene_index=2, adjudicated_scene_index=2),
        make_order_event("E3", 3, annotator_1_scene_index=4,
                         annotator_2_scene_index=4, adjudicated_scene_index=4),
    ])

    result = event_order([case])

    assert result.correct_pairs == 3
    assert result.evaluable_pairs == 3
    assert result.total_reference_pairs == 3
    assert result.same_scene_pairs == 0
    assert result.accuracy == 1.0
    assert result.accuracy_percentage == 100.0
    assert result.pair_coverage == 1.0
    assert result.pair_coverage_percentage == 100.0


def test_event_order_all_pairs_reversed():
    case = make_order_case([
        make_order_event("E1", 1, annotator_1_scene_index=4,
                         annotator_2_scene_index=4, adjudicated_scene_index=4),
        make_order_event("E2", 2, annotator_1_scene_index=2,
                         annotator_2_scene_index=2, adjudicated_scene_index=2),
        make_order_event("E3", 3, annotator_1_scene_index=1,
                         annotator_2_scene_index=1, adjudicated_scene_index=1),
    ])

    result = event_order([case])

    assert result.correct_pairs == 0
    assert result.evaluable_pairs == 3
    assert result.accuracy == 0.0
    assert result.pair_coverage == 1.0


def test_event_order_excludes_pairs_with_not_covered_event():
    case = make_order_case([
        make_order_event("E1", 1, adjudicated_scene_index=1,
                         annotator_1_scene_index=1, annotator_2_scene_index=1),
        make_order_event(
            "E2", 2,
            annotator_1_label="not_covered",
            annotator_2_label="not_covered",
            adjudicated_label="not_covered",
            annotator_1_scene_index=None,
            annotator_2_scene_index=None,
            adjudicated_scene_index=None,
        ),
        make_order_event("E3", 3, adjudicated_scene_index=3,
                         annotator_1_scene_index=3, annotator_2_scene_index=3),
    ])

    result = event_order([case])

    assert result.correct_pairs == 1
    assert result.evaluable_pairs == 1
    assert result.total_reference_pairs == 3
    assert result.accuracy == 1.0
    assert result.pair_coverage == pytest.approx(1 / 3)


def test_event_order_excludes_pairs_with_uncertain_event():
    case = make_order_case([
        make_order_event("E1", 1, adjudicated_scene_index=1,
                         annotator_1_scene_index=1, annotator_2_scene_index=1),
        make_order_event(
            "E2", 2,
            annotator_1_label="uncertain",
            annotator_2_label="uncertain",
            adjudicated_label="uncertain",
            annotator_1_scene_index=None,
            annotator_2_scene_index=None,
            adjudicated_scene_index=None,
        ),
    ])

    result = event_order([case])

    assert result.correct_pairs == 0
    assert result.evaluable_pairs == 0
    assert result.total_reference_pairs == 1
    assert result.accuracy is None
    assert result.pair_coverage == 0.0


def test_event_order_same_scene_pair_is_not_order_evaluable():
    case = make_order_case([
        make_order_event("E1", 1, annotator_1_scene_index=2,
                         annotator_2_scene_index=2, adjudicated_scene_index=2),
        make_order_event("E2", 2, annotator_1_scene_index=2,
                         annotator_2_scene_index=2, adjudicated_scene_index=2),
    ])

    result = event_order([case])

    assert result.correct_pairs == 0
    assert result.evaluable_pairs == 0
    assert result.total_reference_pairs == 1
    assert result.same_scene_pairs == 1
    assert result.accuracy is None
    assert result.pair_coverage == 0.0


def test_event_order_single_event_has_no_reference_pairs():
    case = make_order_case([
        make_order_event("E1", 1),
    ])

    result = event_order([case])

    assert result.total_reference_pairs == 0
    assert result.evaluable_pairs == 0
    assert result.accuracy is None
    assert result.pair_coverage is None


def test_event_order_micro_average_is_within_cases_only():
    case_1 = make_order_case([
        make_order_event("E1", 1, adjudicated_scene_index=1,
                         annotator_1_scene_index=1, annotator_2_scene_index=1),
        make_order_event("E2", 2, adjudicated_scene_index=2,
                         annotator_1_scene_index=2, annotator_2_scene_index=2),
    ], "story_001")
    case_2 = make_order_case([
        make_order_event("E1", 1, adjudicated_scene_index=4,
                         annotator_1_scene_index=4, annotator_2_scene_index=4),
        make_order_event("E2", 2, adjudicated_scene_index=1,
                         annotator_1_scene_index=1, annotator_2_scene_index=1),
        make_order_event("E3", 3, adjudicated_scene_index=2,
                         annotator_1_scene_index=2, annotator_2_scene_index=2),
    ], "story_002")

    result = event_order([case_1, case_2])

    # story_001: 1 correct / 1 evaluable
    # story_002: 1 correct / 3 evaluable
    assert result.correct_pairs == 2
    assert result.evaluable_pairs == 4
    assert result.total_reference_pairs == 4
    assert result.accuracy == 0.5
    assert result.pair_coverage == 1.0


def test_event_order_uses_explicit_reference_order_not_event_id_sort():
    case = make_order_case([
        make_order_event("Z_LAST", 2, adjudicated_scene_index=2,
                         annotator_1_scene_index=2, annotator_2_scene_index=2),
        make_order_event("A_FIRST", 1, adjudicated_scene_index=1,
                         annotator_1_scene_index=1, annotator_2_scene_index=1),
    ])

    result = event_order([case])

    assert result.correct_pairs == 1
    assert result.accuracy == 1.0


def test_event_order_rejects_scene_index_outside_one_to_four():
    case = make_order_case([
        make_order_event("E1", 1, adjudicated_scene_index=5,
                         annotator_1_scene_index=5, annotator_2_scene_index=5),
    ])

    with pytest.raises(ValueError, match="integer from 1 to 4"):
        event_order([case])


def test_event_order_requires_scene_index_for_covered_event():
    case = make_order_case([
        make_order_event("E1", 1, adjudicated_scene_index=None),
    ])

    with pytest.raises(ValueError, match="adjudicated_scene_index"):
        event_order([case])


def test_event_order_rejects_scene_index_for_not_covered_event():
    case = make_order_case([
        make_order_event(
            "E1", 1,
            annotator_1_label="not_covered",
            annotator_2_label="not_covered",
            adjudicated_label="not_covered",
            annotator_1_scene_index=None,
            annotator_2_scene_index=None,
            adjudicated_scene_index=2,
        ),
    ])

    with pytest.raises(ValueError, match="adjudicated_scene_index must be None"):
        event_order([case])


def test_event_order_rejects_duplicate_reference_order():
    case = make_order_case([
        make_order_event("E1", 1),
        make_order_event("E2", 1, adjudicated_scene_index=2,
                         annotator_1_scene_index=2, annotator_2_scene_index=2),
    ])

    with pytest.raises(ValueError, match="Duplicate reference_order"):
        event_order([case])


def test_event_order_rejects_duplicate_event_id():
    case = make_order_case([
        make_order_event("E1", 1),
        make_order_event("E1", 2, adjudicated_scene_index=2,
                         annotator_1_scene_index=2, annotator_2_scene_index=2),
    ])

    with pytest.raises(ValueError, match="Duplicate event_id"):
        event_order([case])


def test_event_order_empty_inventory_returns_none_rates():
    result = event_order([])

    assert result.correct_pairs == 0
    assert result.evaluable_pairs == 0
    assert result.total_reference_pairs == 0
    assert result.accuracy is None
    assert result.pair_coverage is None
