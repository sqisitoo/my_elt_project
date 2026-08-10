# Bronze key layout: date above city, write-attempt timestamp left of the chunk
# index so re-runs never collide and dedup can sort on the file name (ADR-0003, ADR-0004).
from datetime import datetime


def partition_prefix(s3_prefix: str, logical_date: datetime) -> str:
    """Partition prefix for a logical date: '<s3_prefix>/date=YYYY-MM-DD'."""
    return f"{s3_prefix}/date={logical_date:%Y-%m-%d}"


def object_key(
    s3_prefix: str,
    logical_date: datetime,
    actual_datetime: datetime,
    city: str,
    part: int | None = None,
) -> str:
    """Full bronze object key: '<partition_prefix>/city=<city>/<logical_ts>_<actual_ts>[_part_n].json'."""
    prefix = partition_prefix(s3_prefix, logical_date)
    part_suffix = f"_part_{part}" if part is not None else ""
    file_name = (
        f"{logical_date:%Y%m%d%H%M%S}_{actual_datetime:%Y%m%d%H%M%S}{part_suffix}.json"
    )
    return f"{prefix}/city={city}/{file_name}"