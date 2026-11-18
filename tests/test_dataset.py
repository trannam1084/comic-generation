import json
from pathlib import Path

import pytest


ROOT_DIR = Path(__file__).resolve().parent.parent

DEV_FILE = ROOT_DIR / "data" / "dev_cases.jsonl"
TEST_FILE = ROOT_DIR / "data" / "test_cases.jsonl"

REQUIRED_FIELDS = {
    "id",
    "title",
    "summary",
    "characters",
    "key_events",
}


def load_jsonl(file_path):
    """Đọc file JSONL và trả về danh sách các bản ghi."""
    records = []

    with open(file_path, "r", encoding="utf-8") as file:
        for line_number, line in enumerate(file, start=1):
            if not line.strip():
                continue

            try:
                record = json.loads(line)
            except json.JSONDecodeError as error:
                pytest.fail(
                    f"{file_path.name}, line {line_number}: "
                    f"JSON không hợp lệ - {error}"
                )

            records.append(record)

    return records


@pytest.fixture
def dev_records():
    return load_jsonl(DEV_FILE)


@pytest.fixture
def test_records():
    return load_jsonl(TEST_FILE)


def test_dataset_files_exist():
    """Kiểm tra các file Dev và Test tồn tại."""
    assert DEV_FILE.exists(), "Không tìm thấy file dev_cases.jsonl"
    assert TEST_FILE.exists(), "Không tìm thấy file test_cases.jsonl"


def test_dev_dataset_has_20_records(dev_records):
    """Dev dataset phải có 20 truyện."""
    assert len(dev_records) == 20


def test_test_dataset_has_10_records(test_records):
    """Test dataset phải có 10 truyện."""
    assert len(test_records) == 10


@pytest.mark.parametrize("dataset_name", ["dev", "test"])
def test_required_fields(dataset_name):
    """Kiểm tra các trường bắt buộc của từng bản ghi."""
    file_path = DEV_FILE if dataset_name == "dev" else TEST_FILE
    records = load_jsonl(file_path)

    for index, record in enumerate(records, start=1):
        missing_fields = REQUIRED_FIELDS - record.keys()

        assert not missing_fields, (
            f"{dataset_name} - record {index} thiếu trường: "
            f"{missing_fields}"
        )


@pytest.mark.parametrize("dataset_name", ["dev", "test"])
def test_required_fields_are_not_empty(dataset_name):
    """Kiểm tra các trường nội dung không bị trống."""
    file_path = DEV_FILE if dataset_name == "dev" else TEST_FILE
    records = load_jsonl(file_path)

    for index, record in enumerate(records, start=1):
        for field in ("id", "title", "summary"):
            value = record.get(field)

            assert isinstance(value, str), (
                f"{dataset_name} - record {index}: "
                f"{field} phải là string"
            )

            assert value.strip(), (
                f"{dataset_name} - record {index}: "
                f"{field} không được rỗng"
            )


@pytest.mark.parametrize("dataset_name", ["dev", "test"])
def test_characters_is_list(dataset_name):
    """Characters phải là danh sách."""
    file_path = DEV_FILE if dataset_name == "dev" else TEST_FILE
    records = load_jsonl(file_path)

    for index, record in enumerate(records, start=1):
        assert isinstance(record["characters"], list), (
            f"{dataset_name} - record {index}: "
            "characters phải là list"
        )


@pytest.mark.parametrize("dataset_name", ["dev", "test"])
def test_key_events_is_list(dataset_name):
    """Key events phải là danh sách."""
    file_path = DEV_FILE if dataset_name == "dev" else TEST_FILE
    records = load_jsonl(file_path)

    for index, record in enumerate(records, start=1):
        assert isinstance(record["key_events"], list), (
            f"{dataset_name} - record {index}: "
            "key_events phải là list"
        )

        assert len(record["key_events"]) >= 2, (
            f"{dataset_name} - record {index}: "
            "cần tối thiểu 2 sự kiện chính"
        )


def test_dev_ids_are_unique(dev_records):
    """ID trong Dev không được trùng."""
    ids = [record["id"] for record in dev_records]

    assert len(ids) == len(set(ids)), "ID bị trùng trong Dev dataset"


def test_test_ids_are_unique(test_records):
    """ID trong Test không được trùng."""
    ids = [record["id"] for record in test_records]

    assert len(ids) == len(set(ids)), "ID bị trùng trong Test dataset"


def test_dev_and_test_ids_do_not_overlap(dev_records, test_records):
    """Dev và Test không được chứa cùng ID."""
    dev_ids = {record["id"] for record in dev_records}
    test_ids = {record["id"] for record in test_records}

    overlap = dev_ids & test_ids

    assert not overlap, (
        f"ID bị trùng giữa Dev và Test: {overlap}"
    )


def test_total_dataset_has_30_records(dev_records, test_records):
    """Tổng dataset phải có 30 truyện."""
    assert len(dev_records) + len(test_records) == 30