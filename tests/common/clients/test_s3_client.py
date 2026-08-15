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
