import json
import logging
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from botocore.client import BaseClient

logger = logging.getLogger(__name__)


class S3Service:
    def __init__(self, bucket_name: str, s3_client: "BaseClient"):
        self._bucket = bucket_name
        self._client = s3_client

    def save_dict_as_json(self, data: dict[str, Any], key: str) -> None:
        try:
            json_bytes = json.dumps(data, ensure_ascii=False).encode("UTF-8")

            self._client.put_object(
                Bucket=self._bucket, Key=key, Body=json_bytes, ContentType="application/json"
            )

            logger.info(f"Successfully saved JSON to s3://{self._bucket}/{key}")

        except Exception:
            logger.error(f"Failed to save JSON to s3://{self._bucket}/{key}")
            raise
