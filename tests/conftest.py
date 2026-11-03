"""Shared test rig: three synthetic drivers, prepared readings, a stand-in model and local stand-ins for storage,
queue and records. No network, no AWS. The clock is a list, so a test can move time on (env.clock[0] += ...)."""
import datetime as dt
import hashlib
import itertools

import pytest

from pipeline.config import Settings
from pipeline.intake import Deps, handle_payload
from pipeline.jobs import LocalQueue
from pipeline.model import StandInModel
from pipeline.records import LocalRecords
from pipeline.registry import Registry
from pipeline.store import LocalStore
from pipeline.worker import process_job

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
NOW = dt.datetime(2026, 10, 22, 10, 0, tzinfo=IST)
A, B, C, STRANGER = "+919000000001", "+919000000002", "+919000000003", "+919999999999"
GSTIN = "36ABCDE1234F1Z5"

FILES = {  # media id -> file bytes (images, so no PDF rendering is needed in tests)
    "INVOICE_A": b"jpeg-invoice-cab-A", "ADVISORY_A": b"jpeg-invoice-tyres-worn", "FIX_A": b"jpeg-invoice-tyres-new",
    "MEDICAL_A": b"jpeg-medical-certificate", "DOC_C": b"jpeg-real-document", "INSURANCE_A": b"jpeg-insurance-cab-A",
    "INVOICE_B": b"jpeg-invoice-cab-B",
}
H = {k: hashlib.sha256(v).hexdigest() for k, v in FILES.items()}


def reading(**over):
    base = {"doc_type": "service_invoice", "is_estimate": False, "vehicle_no_on_doc": "TS09XY4521",
            "doc_date": "2026-09-12", "odometer_km": 59985, "workshop_name": "Sample Toyota, Kondapur", "gstin": GSTIN,
            "invoice_no": "TXP26-28297", "billed_to": "R. Kumar", "total_amount": 15835.0,
            "work_done": ["60,000 km periodic service"], "advisories": [], "validity_till": None,
            "summary": "Periodic service at 60,000 km.", "confidence": 0.95}
    base.update(over)
    return base


READINGS = {
    H["INVOICE_A"]: reading(),
    H["ADVISORY_A"]: reading(doc_date="2026-10-01", odometer_km=64000, invoice_no="TXP26-30001",
                             advisories=["Both rear tyres worn, depth uneven"]),
    H["FIX_A"]: reading(doc_date="2026-10-15", odometer_km=66000, invoice_no="TXP26-31002",
                        work_done=["Rear tyres replaced (2 nos)", "Wheel alignment"]),
    H["INSURANCE_A"]: reading(doc_type="insurance", doc_date="2026-05-19", odometer_km=None, gstin=None,
                              invoice_no="POL-2026-004521", work_done=[], validity_till="2027-05-18",
                              summary="Motor insurance valid till 18 May 2027."),
    H["INVOICE_B"]: reading(vehicle_no_on_doc="TS09XY7730", doc_date="2026-10-03", odometer_km=71200,
                            invoice_no="TXP26-30410", billed_to="Driver Two"),
}
_ids = itertools.count(1)


def wa(sender, kind="image", media=None, caption="", text=""):
    m = {"from": sender.lstrip("+"), "id": "wamid.%d" % next(_ids), "timestamp": "1761120000", "type": kind}
    if kind in ("image", "document"):
        m[kind] = {"id": media, "mime_type": "image/jpeg", "caption": caption}
    elif kind == "text":
        m["text"] = {"body": text}
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {"messages": [m]}}]}]}


@pytest.fixture
def env(tmp_path):
    registry = Registry([
        {"phone": A, "driver_name": "Driver One", "vehicle_no": "TS09XY4521", "cab_id": "CAB-01", "language": "en",
         "synthetic": True, "training_token": "tokA-test"},
        {"phone": B, "driver_name": "Driver Two", "vehicle_no": "TS09XY7730", "cab_id": "CAB-02", "language": "te",
         "synthetic": True, "training_token": "tokB-test"},
        {"phone": C, "driver_name": "Real Driver", "vehicle_no": "TG07AB1188", "cab_id": "CAB-03", "language": "hi"},
    ], client="Example Tech Park")
    outbox, sleeps, clock = [], [], [NOW]
    d = Deps(settings=Settings(local_dir=str(tmp_path)), registry=registry, records=LocalRecords(),
             store=LocalStore(str(tmp_path / "files")), queue=LocalQueue(), model=StandInModel(READINGS),
             fetch_media=lambda mid: (FILES[mid], "image/jpeg"), send=lambda to, body: outbox.append((to, body)) or "id",
             now=lambda: clock[0], sleep=lambda s: sleeps.append(s))
    d.outbox, d.sleeps, d.clock = outbox, sleeps, clock
    return d


def run(d):
    return [process_job(job, d) for job in d.queue.drain()]


def last(d, phone):
    return [body for to, body in d.outbox if to == phone][-1]


def consent(d, phone, word="YES"):
    handle_payload(wa(phone, "text", text=word), d)
