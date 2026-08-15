from datetime import datetime

from plugins.common.utils.bronze_paths import object_key, partition_prefix

LOGICAL_DATE = datetime(2026, 6, 27, 0, 0, 0)
ACTUAL_DATETIME = datetime(2026, 7, 1, 7, 42, 0)


def test_partition_prefix_format():
    assert partition_prefix("bronze/weather", LOGICAL_DATE) == "bronze/weather/date=2026-06-27"


def test_object_key_without_part():
    key = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=ACTUAL_DATETIME,
        city="Warsaw",
    )

    assert key == "bronze/weather/date=2026-06-27/city=Warsaw/20260627000000_20260701074200.json"


def test_object_key_with_part():
    key = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=ACTUAL_DATETIME,
        city="Warsaw",
        part=2,
    )

    assert key == "bronze/weather/date=2026-06-27/city=Warsaw/20260627000000_20260701074200_part_2.json"


def test_object_key_nests_under_its_partition_prefix():
    prefix = partition_prefix("bronze/weather", LOGICAL_DATE)
    key = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=ACTUAL_DATETIME,
        city="Warsaw",
    )

    assert key.startswith(prefix + "/city=Warsaw/")


def test_object_key_differs_across_reruns():
    # Same logical date and chunk, different wall-clock write attempts (ADR-0003).
    first = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=datetime(2026, 6, 27, 0, 5, 0),
        city="Warsaw",
    )
    second = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=datetime(2026, 6, 28, 22, 11, 0),
        city="Warsaw",
    )

    assert first != second


def test_object_key_file_name_sorts_by_actual_datetime_regardless_of_part():
    # actual timestamp sits left of the part index, so a later attempt with a
    # smaller chunk count still sorts after an earlier attempt (ADR-0003).
    earlier_attempt_part_2 = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=datetime(2026, 6, 28, 22, 11, 0),
        city="Warsaw",
        part=2,
    )
    later_attempt_part_1 = object_key(
        s3_prefix="bronze/weather",
        logical_date=LOGICAL_DATE,
        actual_datetime=datetime(2026, 7, 1, 7, 42, 0),
        city="Warsaw",
        part=1,
    )

    assert earlier_attempt_part_2 < later_attempt_part_1
