"""The job queue between intake and the worker: SQS in the cloud, a list in memory for development. A job carries
hashed ids and the stored file's key, never a phone number or document content."""
import json

from . import logs
from .config import REGION
from .errors import StorageError


class LocalQueue:
    def __init__(self):
        self.jobs = []

    def send(self, job: dict) -> str:
        self.jobs.append(dict(job))
        return str(len(self.jobs))

    def drain(self) -> list:
        jobs, self.jobs = self.jobs, []
        return jobs


class SqsQueue:
    def __init__(self, queue_url: str, client=None):
        if not queue_url:
            raise StorageError("SQS queue URL is not configured")
        import boto3
        self.url = queue_url
        self.sqs = client or boto3.client("sqs", region_name=REGION)

    def send(self, job: dict) -> str:
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            return self.sqs.send_message(QueueUrl=self.url, MessageBody=json.dumps(job))["MessageId"]
        except (BotoCoreError, ClientError) as e:
            logs.event("SQS_SEND_FAILED", "error", error=type(e).__name__)
            raise StorageError("SQS rejected the job") from e
