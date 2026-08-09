import json
from unittest.mock import MagicMock

import pytest

from plugins.common.clients.s3_client import S3Service


@pytest.fixture
def bucket_name():
    """Fixture providing a test S3 bucket name."""
    return "test-bucket"


@pytest.fixture
def mock_boto_client():
    """Fixture providing a mocked boto3 S3 client."""
    return MagicMock()


@pytest.fixture
def s3_service(bucket_name, mock_boto_client):
    """Fixture providing an S3Service instance with mocked dependencies."""
    return S3Service(bucket_name, mock_boto_client)


# ---- JSON tests ----


def test_save_dict_as_json_encodes_correctly(bucket_name, mock_boto_client, s3_service):
    """
    Test that save_dict_as_json correctly encodes a dictionary as JSON bytes
    and calls put_object with the expected parameters.
    """
    data = {"key": "value", "second_key": "second_value"}
    file_key = "folder/data.json"

    s3_service.save_dict_as_json(data, file_key)

    mock_boto_client.put_object.assert_called_once()

    call_kwargs = mock_boto_client.put_object.call_args.kwargs

    assert call_kwargs["Bucket"] == bucket_name
    assert call_kwargs["Key"] == file_key
    assert call_kwargs["ContentType"] == "application/json"

    assert isinstance(call_kwargs["Body"], bytes)

    sent_json = json.loads(call_kwargs["Body"].decode("UTF-8"))
    assert sent_json == data


def test_load_json_decodes_correctly(bucket_name, mock_boto_client, s3_service):
    """
    Test that load_json decodes JSON bytes from S3 and returns the correct dictionary.
    """
    expected_data = {"key": "value", "second_key": "second_value"}
    json_bytes = json.dumps(expected_data).encode("UTF-8")

    mock_body = MagicMock()
    mock_body.read.return_value = json_bytes

    mock_boto_client.get_object.return_value = {"Body": mock_body}

    result = s3_service.load_json("data.json")

    assert result == expected_data
    mock_boto_client.get_object.assert_called_with(Bucket=bucket_name, Key="data.json")


def test_s3_exception_is_reraised(s3_service, mock_boto_client):
    """
    Test that exceptions raised by the boto3 client are propagated by the S3Service.
    """
    mock_boto_client.get_object.side_effect = Exception("AWS is down")

    with pytest.raises(Exception, match="AWS is down"):
        s3_service.load_json("fail.json")


# ---- Listing tests ----


def _paginate_returns(mock_boto_client, pages):
    """
    Make the mocked client's list_objects_v2 paginator yield the given pages.

    Returns the mocked paginator so tests can assert how it was called.
    """
    mock_paginator = MagicMock()
    mock_paginator.paginate.return_value = pages
    mock_boto_client.get_paginator.return_value = mock_paginator

    return mock_paginator


def test_list_keys_returns_empty_list_when_prefix_matches_nothing(mock_boto_client, s3_service):
    """
    Test that list_keys returns an empty list for a prefix with no objects.

    S3 omits the "Contents" key entirely instead of returning an empty list, so this is
    the shape the paginator really yields for an empty prefix.
    """
    _paginate_returns(mock_boto_client, [{"KeyCount": 0, "IsTruncated": False}])

    assert s3_service.list_keys("bronze/weather_data/city=Berlin/") == []


def test_list_keys_collects_keys_from_every_page(bucket_name, mock_boto_client, s3_service):
    """
    Test that list_keys walks the whole paginated listing instead of the first page only.

    A single list_objects_v2 call returns at most 1000 keys, so a listing spanning several
    pages must come back whole — a caller that deletes a truncated listing reports success
    while leaving objects behind.
    """
    pages = [
        {"IsTruncated": True, "Contents": [{"Key": "bronze/a.json"}, {"Key": "bronze/b.json"}]},
        {"IsTruncated": False, "Contents": [{"Key": "bronze/c.json"}]},
    ]
    mock_paginator = _paginate_returns(mock_boto_client, pages)

    result = s3_service.list_keys("bronze/")

    assert result == ["bronze/a.json", "bronze/b.json", "bronze/c.json"]

    mock_boto_client.get_paginator.assert_called_once_with("list_objects_v2")
    mock_paginator.paginate.assert_called_once_with(Bucket=bucket_name, Prefix="bronze/")
