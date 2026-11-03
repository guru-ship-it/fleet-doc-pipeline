"""Where original files live: S3 with SSE-KMS in ap-south-1, or a local folder for development. Driver medical
certificates go under a separate restricted prefix and are never sent to the model."""
import os

from . import logs
from .config import REGION
from .errors import StorageError

EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp", "application/pdf": "pdf"}


def object_key(vehicle: str, received_at, file_hash: str, mime: str, medical: bool = False) -> str:
    prefix = "restricted/medical" if medical else "fleet"
    return "%s/%s/%s/%s.%s" % (prefix, vehicle, received_at.strftime("%Y-%m"), file_hash, EXT.get(mime, "bin"))


class LocalStore:
    def __init__(self, root: str):
        self.root = root

    def _path(self, key: str) -> str:
        return os.path.join(self.root, *key.split("/"))

    def put(self, key: str, data: bytes, mime: str) -> str:
        path = self._path(key)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(data)
        return key

    def get(self, key: str) -> bytes:
        try:
            with open(self._path(key), "rb") as f:
                return f.read()
        except OSError as e:
            raise StorageError("Stored file not found") from e


class S3Store:
    def __init__(self, bucket: str, kms_key_id: str, client=None):
        if not (bucket and kms_key_id):
            raise StorageError("S3 bucket and KMS key must both be configured")
        import boto3
        self.bucket, self.kms_key_id = bucket, kms_key_id
        self.s3 = client or boto3.client("s3", region_name=REGION)

    def put(self, key: str, data: bytes, mime: str) -> str:
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            self.s3.put_object(Bucket=self.bucket, Key=key, Body=data, ContentType=mime,
                               ServerSideEncryption="aws:kms", SSEKMSKeyId=self.kms_key_id)
        except (BotoCoreError, ClientError) as e:
            logs.event("S3_PUT_FAILED", "error", error=type(e).__name__)
            raise StorageError("S3 rejected the upload") from e
        return key

    def get(self, key: str) -> bytes:
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            return self.s3.get_object(Bucket=self.bucket, Key=key)["Body"].read()
        except (BotoCoreError, ClientError) as e:
            logs.event("S3_GET_FAILED", "error", error=type(e).__name__)
            raise StorageError("S3 read failed") from e
