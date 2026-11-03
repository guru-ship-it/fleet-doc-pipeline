"""Entry points: the FastAPI webhook (GET handshake, POST messages) and the SQS worker for AWS Lambda.
build_deps() wires local or AWS backends from Settings."""
import datetime as dt
import functools
import json
import os

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, PlainTextResponse

from . import bridge, logs
from .config import Settings, load_secret_into_env
from .errors import WebhookAuthError
from .inbound import statuses, verify_challenge, verify_signature
from .intake import Deps, handle_payload
from .logs import hid
from .jobs import LocalQueue, SqsQueue
from .model import MuseModel, StandInModel
from .photo import SamPhoto
from .records import DynamoRecords, LocalRecords
from .registry import Registry
from .store import LocalStore, S3Store
from .worker import process_job

IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")


def build_deps(settings: Settings | None = None) -> Deps:
    if os.environ.get("SECRET_ID"):
        load_secret_into_env(os.environ["SECRET_ID"])
    s = settings or Settings.from_env()
    registry = Registry.from_file(os.environ.get("REGISTRY_FILE", "demo/registry.example.json"))
    if s.local_dir:
        store, queue = LocalStore(os.path.join(s.local_dir, "files")), LocalQueue()
        records = LocalRecords(os.path.join(s.local_dir, "records.json"))
    else:
        store, queue, records = S3Store(s.s3_bucket, s.kms_key_id), SqsQueue(s.sqs_queue_url), DynamoRecords(s.ddb_table)
    if s.model_mode == "muse":
        model = MuseModel(s.model_base_url, s.model_api_key, s.model_id)
    else:
        with open(os.environ.get("READINGS_FILE", "demo/readings.example.json"), encoding="utf-8") as f:
            model = StandInModel(json.load(f))
    photo = SamPhoto(s.model_base_url, s.model_api_key, s.photo_model_id) if s.photo_mode == "sam" else None
    return Deps(settings=s, registry=registry, records=records, store=store, queue=queue, model=model, photo=photo,
                fetch_media=functools.partial(bridge.graph_download_media, token=s.wa_access_token,
                                              version=s.graph_version),
                send=functools.partial(bridge.graph_send_text, token=s.wa_access_token,
                                       phone_number_id=s.wa_phone_number_id, version=s.graph_version),
                now=lambda: dt.datetime.now(IST))


@functools.lru_cache(maxsize=1)
def deps() -> Deps:
    return build_deps()


app = FastAPI(title="Fleet document intake", docs_url=None, redoc_url=None, openapi_url=None)


@app.get("/wa/inbound")
async def handshake(request: Request):
    try:
        return PlainTextResponse(verify_challenge(dict(request.query_params), deps().settings.wa_verify_token))
    except WebhookAuthError:
        return PlainTextResponse("forbidden", status_code=403)


@app.post("/wa/inbound")
async def inbound(request: Request):
    raw = await request.body()
    d = deps()
    try:
        verify_signature(raw, request.headers.get("x-hub-signature-256", ""), d.settings.wa_app_secret)
    except WebhookAuthError as e:
        logs.event("WEBHOOK_REJECTED", "error", reason=str(e))
        return JSONResponse({"status": "forbidden"}, status_code=403)
    payload = json.loads(raw)
    for st in statuses(payload):   # delivery receipts: "sent" is not "delivered"; "failed" says why
        logs.event("WA_STATUS", "warning" if st.status == "failed" else "info", status=st.status,
                   wamid=st.message_id[-12:], to_id=hid(st.recipient), error=st.error_code,
                   detail=st.error_title[:160] or None)
    handle_payload(payload, d)   # failures raise -> HTTP 500 -> Meta retries the delivery
    return {"status": "ok"}


def lambda_webhook(event, context):
    from mangum import Mangum
    return Mangum(app, lifespan="off")(event, context)


def lambda_worker(event, context):
    """SQS-triggered. Failed jobs are reported back so SQS retries them, and after the last try they land in the
    dead-letter queue for review."""
    failures, d = [], deps()
    for r in event.get("Records", []):
        try:
            process_job(json.loads(r["body"]), d)
        except Exception as e:   # reported, not hidden: SQS retries, then moves the job to the DLQ
            logs.event("JOB_FAILED", "error", error=type(e).__name__, detail=str(e)[:160], sqs_id=r.get("messageId"))
            failures.append({"itemIdentifier": r["messageId"]})
    return {"batchItemFailures": failures}
