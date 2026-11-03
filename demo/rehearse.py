"""Rehearse the pipeline end to end on this machine: no network, no AWS, no model call. The synthetic registry, a
stand-in model with prepared readings, and the real intake, rules, records and replies. Writes local_data/rehearsal,
which dashboard/serve_local.py reads, and prints every WhatsApp reply as the driver would see it.

    python demo/rehearse.py
"""
import datetime as dt
import hashlib
import itertools
import json
import os
import pathlib
import shutil
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.chdir(ROOT)

from pipeline.config import Settings  # noqa: E402
from pipeline.intake import Deps, handle_payload  # noqa: E402
from pipeline.jobs import LocalQueue  # noqa: E402
from pipeline.model import StandInModel  # noqa: E402
from pipeline.records import LocalRecords  # noqa: E402
from pipeline.registry import Registry  # noqa: E402
from pipeline.store import LocalStore  # noqa: E402
from pipeline.worker import process_job  # noqa: E402

DATA = ROOT / "local_data" / "rehearsal"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")
A, B, C = "+919000000001", "+919000000002", "+919000000004"      # demo/registry.example.json
GSTIN = "36ABCDE1234F1Z5"

FILES = {"INVOICE_A": b"synthetic-service-invoice-cab-01", "INSURANCE_A": b"synthetic-insurance-cab-01",
         "ADVISORY_A": b"synthetic-invoice-tyres-worn-cab-01", "FUTURE_B": b"synthetic-cash-memo-future-dated"}
H = {k: hashlib.sha256(v).hexdigest() for k, v in FILES.items()}


def reading(**over):
    base = {"doc_type": "service_invoice", "is_estimate": False, "vehicle_no_on_doc": "TS09XY4521", "doc_date": "2026-09-12",
            "odometer_km": 59985, "workshop_name": "Sample Toyota, Kondapur", "gstin": GSTIN, "invoice_no": "TXP26-28297",
            "billed_to": "Ravi", "total_amount": 15835.0, "work_done": ["60,000 km periodic service", "Engine oil and filter"],
            "advisories": [], "validity_till": None, "summary": "Periodic service at 59,985 km with oil and filter change.",
            "confidence": 0.95}
    base.update(over)
    return base


READINGS = {
    H["INVOICE_A"]: reading(),
    H["INSURANCE_A"]: reading(doc_type="insurance", doc_date="2026-05-19", odometer_km=None, workshop_name="Sample General Insurance",
                              gstin=None, invoice_no="POL-2026-004521", total_amount=18420.0, work_done=[],
                              validity_till="2027-05-18", summary="Comprehensive motor insurance policy valid till 18 May 2027."),
    H["ADVISORY_A"]: reading(doc_date="2026-10-01", odometer_km=64000, invoice_no="TXP26-30001", total_amount=4120.0,
                             work_done=["Wheel balancing", "Brake fluid top-up"], advisories=["Both rear tyres worn, depth uneven"],
                             summary="Wheel balancing and brake fluid top-up; workshop recommends replacing both rear tyres."),
    H["FUTURE_B"]: reading(doc_type="cash_memo", vehicle_no_on_doc="TS09XY7730", doc_date="2026-12-31", odometer_km=71200,
                           workshop_name="Raju Auto Works", gstin=None, invoice_no="412", billed_to="Suresh", total_amount=2400.0,
                           work_done=["Engine oil change"], summary="Hand-written cash memo for an oil change, dated 31 Dec 2026.",
                           confidence=0.82),
}
_ids = itertools.count(1)


def wa(sender, kind="image", media=None, caption="", text=""):
    m = {"from": sender.lstrip("+"), "id": "wamid.%d" % next(_ids), "timestamp": "1761120000", "type": kind}
    if kind in ("image", "document"):
        m[kind] = {"id": media, "mime_type": "image/jpeg", "caption": caption}
    else:
        m["text"] = {"body": text}
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {"messages": [m]}}]}]}


def main() -> None:
    shutil.rmtree(DATA, ignore_errors=True)     # the rehearsal's own scratch output, listed in .gitignore
    DATA.mkdir(parents=True)
    clock = [dt.datetime(2026, 11, 2, 9, 30, tzinfo=IST)]
    with open("demo/registry.example.json", encoding="utf-8") as f:
        example = json.load(f)
    # rehearsal-only learner tokens, so the Train half shows; the example file in the repo carries none
    registry = Registry([dict(d, training_token="rehearsal-" + d["cab_id"].lower()) for d in example["drivers"]],
                        example.get("client", ""))
    names = {d.phone: "%s (%s)" % (d.cab_id, d.language) for d in registry.drivers()}

    def send(to, body):
        print("  -> %s: %s" % (names.get(to, "unknown"), body))
        return "wamid.sent"

    deps = Deps(settings=Settings(local_dir=str(DATA)), registry=registry, records=LocalRecords(str(DATA / "records.json")),
                store=LocalStore(str(DATA / "files")), queue=LocalQueue(), model=StandInModel(READINGS),
                fetch_media=lambda mid: (FILES[mid], "image/jpeg"), send=send, now=lambda: clock[0],
                sleep=lambda s: None)

    def step(title, payload, seconds_to_reply=9, minutes_after=7):
        clock[0] += dt.timedelta(minutes=minutes_after)
        print("%s  %s" % (clock[0].strftime("%H:%M:%S"), title))
        handle_payload(payload, deps)
        clock[0] += dt.timedelta(seconds=seconds_to_reply)
        for job in deps.queue.drain():
            process_job(job, deps)

    step("CAB-01 says hi", wa(A, "text", text="Hi"))
    step("CAB-01 agrees", wa(A, "text", text="YES"), minutes_after=1)
    step("CAB-01 sends the September service invoice", wa(A, media="INVOICE_A"), seconds_to_reply=8)
    step("CAB-01 sends the insurance policy", wa(A, media="INSURANCE_A"), seconds_to_reply=11, minutes_after=3)
    step("CAB-02 agrees (Telugu)", wa(B, "text", text="అవును"), minutes_after=25)
    step("CAB-02 forwards CAB-01's invoice as its own", wa(B, media="INVOICE_A"), seconds_to_reply=7)
    step("CAB-02 sends a future-dated cash memo without GST", wa(B, media="FUTURE_B"), seconds_to_reply=6, minutes_after=4)
    step("CAB-01 sends October bill: workshop flags worn rear tyres", wa(A, media="ADVISORY_A"), seconds_to_reply=9, minutes_after=40)
    print("\nrecords: %s\nnow: python dashboard/serve_local.py 8098   (access code: demo)" % (DATA / "records.json"))


if __name__ == "__main__":
    main()
