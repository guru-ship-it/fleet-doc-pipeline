"""Settings. The AWS region is fixed to ap-south-1 (Mumbai). Secrets come from AWS Secrets Manager in the cloud
(loaded into the environment at start-up) and from the environment locally; nothing secret lives in code or files."""
import json
import os
from dataclasses import dataclass

REGION = "ap-south-1"


def load_secret_into_env(secret_id: str) -> None:
    """Copy a Secrets Manager JSON secret's keys into os.environ (keys already set are left alone)."""
    import boto3
    value = boto3.client("secretsmanager", region_name=REGION).get_secret_value(SecretId=secret_id)["SecretString"]
    for k, v in json.loads(value).items():
        os.environ.setdefault(k, str(v))


@dataclass(frozen=True)
class Settings:
    model_mode: str = "standin"           # "muse" calls the Meta Model API; "standin" uses prepared readings
    model_base_url: str = ""
    model_api_key: str = ""
    model_id: str = ""
    wa_app_secret: str = ""               # verifies X-Hub-Signature-256 on every webhook POST
    wa_verify_token: str = ""             # the GET handshake when the webhook URL is registered
    wa_access_token: str = ""             # Graph API token: media downloads and replies
    wa_phone_number_id: str = ""
    graph_version: str = "v21.0"
    s3_bucket: str = ""
    kms_key_id: str = ""
    sqs_queue_url: str = ""
    ddb_table: str = ""
    local_dir: str = ""                   # set for development: files, queue and records stay on disk
    ack_on_receipt: bool = True           # send "Received, checking it now" before the result
    reply_gap_s: float = 3.0              # minimum spacing between two replies to the same driver (0 = off)
    reply_max_wait_s: float = 60.0        # a worker holds a reply at most this long for its slot

    @classmethod
    def from_env(cls) -> "Settings":
        e = os.environ.get
        return cls(model_mode=e("MODEL_MODE", "standin"), model_base_url=e("META_API_BASE_URL", ""),
                   model_api_key=e("META_API_KEY", ""), model_id=e("MUSE_MODEL_ID", ""),
                   wa_app_secret=e("WA_APP_SECRET", ""), wa_verify_token=e("WA_VERIFY_TOKEN", ""),
                   wa_access_token=e("WA_ACCESS_TOKEN", ""), wa_phone_number_id=e("WA_PHONE_NUMBER_ID", ""),
                   graph_version=e("GRAPH_API_VERSION", "v21.0"), s3_bucket=e("S3_BUCKET", ""),
                   kms_key_id=e("KMS_KEY_ID", ""), sqs_queue_url=e("SQS_QUEUE_URL", ""), ddb_table=e("DDB_TABLE", ""),
                   local_dir=e("LOCAL_DATA_DIR", ""), ack_on_receipt=e("ACK_ON_RECEIPT", "true").lower() == "true",
                   reply_gap_s=float(e("REPLY_GAP_S", "3")), reply_max_wait_s=float(e("REPLY_MAX_WAIT_S", "60")))
