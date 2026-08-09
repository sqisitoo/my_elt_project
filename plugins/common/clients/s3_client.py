import io
import json
import logging
from typing import TYPE_CHECKING, Any, cast

import pandas as pd

if TYPE_CHECKING:
    from botocore.client import BaseClient

logger = logging.getLogger(__name__)


class S3Service:

    def __init__(self, bucket_name: str, s3_client: "BaseClient"):
        self._bucket = bucket_name
        self._client = s3_client

    def load_json(self, key: str) -> dict[str, Any]:
        try:
            response = self._client.get_object(Bucket=self._bucket, Key=key)
            json_string = response["Body"].read().decode("UTF-8")

            return cast(dict[str, Any], json.loads(json_string))
        except Exception as err:
            logger.error(f"Failed to load json from s3://{self._bucket}/{key}. Error: {err}")
            raise

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


    def list_keys(self, prefix: str) -> list[str]:
        """
        List every object key under the given prefix.

        Args:
            prefix: S3 key prefix to list, e.g. "bronze/weather_data/city=Berlin/".

        Returns:
            All matching keys, or an empty list if the prefix matches nothing.
        """
        # a single list_objects_v2 call returns at most 1000 keys plus a continuation token;
        # the paginator replays the call until the last page, so callers never act on a
        # silently truncated listing
        paginator = self._client.get_paginator("list_objects_v2")

        # "Contents" is absent, not empty, on a page that matched nothing
        s3_keys = [
            content["Key"]
            for page in paginator.paginate(Bucket=self._bucket, Prefix=prefix)
            for content in page.get("Contents", [])
        ]

        logger.info(f"Listed {len(s3_keys)} object(s) under s3://{self._bucket}/{prefix}")
        logger.debug("Keys under %s: %s", prefix, s3_keys)

        return s3_keys
