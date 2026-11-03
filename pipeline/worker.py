"""The worker: read the stored file with the model, check it with the rules, update the cab's records and reply to the
driver. The dashboard reads the records live, so nothing is rebuilt. Every model call and rule decision is logged
without personal data."""
import time
from dataclasses import asdict

from . import logs
from .errors import PipelineError, ResidencyError
from .intake import reply
from .model import IMAGE_TYPES, to_pages
from .records import invoice_key
from .rules import Context, evaluate, parse_date, pretty_vehicle
from .training import ACCEPTED, choose_module, module_link, module_title

# Kept on the record. billed_to is left out on purpose: it is a person's or company's name and only its flag matters.
KEPT_FIELDS = ("doc_type", "is_estimate", "vehicle_no_on_doc", "doc_date", "odometer_km", "workshop_name", "gstin",
               "invoice_no", "total_amount", "work_done", "advisories", "validity_till", "summary", "confidence")


def _iso(s):
    d = parse_date(s)
    return d.isoformat() if d else None


def process_job(job: dict, deps) -> dict:
    driver = deps.registry.by_id(job["sender_id"])
    if driver is None:
        logs.event("JOB_SENDER_UNKNOWN", "error", file=job["hash"][:12])
        raise PipelineError("The job's sender is no longer registered")
    vehicle, ref = driver.vehicle_no, job["hash"][:12]
    if not deps.records.has_consent(job["sender_id"]):   # withdrawn (STOP) after the file was queued
        logs.event("JOB_SKIPPED_NO_CONSENT", file=ref, cab=driver.cab_id)
        return {"outcome": "skipped_no_consent", "hash": job["hash"]}
    base = {"received_at": job["received_at"], "hash": job["hash"], "key": job["key"], "mime": job["mime"],
            "cab_id": driver.cab_id}

    if job.get("medical"):   # restricted prefix; never sent to the model
        rec = dict(base, doc={"doc_type": "medical_certificate"}, outcome="pending_review", flags=[], opened=[], closed=[],
                   decided_at=deps.now().isoformat(timespec="seconds"))
        deps.records.save(vehicle, rec, [], [])
        logs.event("MEDICAL_STORED", file=ref, cab=driver.cab_id)
        rec["replied"] = reply(deps, driver.phone, "medical_received", driver.language)
        _changed(deps, vehicle)
        return rec

    earlier = deps.records.documents(vehicle)   # one read serves the duplicate check and the modules already sent
    if any(d["hash"] == job["hash"] for d in earlier):
        logs.event("ALREADY_RECEIVED", file=ref, cab=driver.cab_id)
        reply(deps, driver.phone, "already_received", driver.language, vehicle=pretty_vehicle(vehicle))
        return {"outcome": "already_received", "hash": job["hash"]}

    offshore = not deps.model.in_india or (deps.photo is not None and not deps.photo.in_india)
    if offshore and not driver.synthetic:
        logs.event("RESIDENCY_BLOCK", "error", file=ref, cab=driver.cab_id)
        raise ResidencyError("A real document may not be sent to a model hosted outside India")

    t0 = time.monotonic()
    pages, photo = to_pages(deps.store.get(job["key"]), job["mime"]), None
    if deps.photo is not None and job["mime"] in IMAGE_TYPES:   # a photo, not a PDF: find and straighten the paper
        pages, photo = deps.photo.prepare(pages, job["hash"])
    doc = deps.model.extract(pages, job["hash"])
    read_ms = round((time.monotonic() - t0) * 1000)
    prior = deps.records.seen_hash(job["hash"])
    inv_key = invoice_key(doc)
    inv_prior = deps.records.seen_invoice(inv_key) if inv_key else None
    state = deps.records.cab_state(vehicle)
    decision = evaluate(doc, Context(
        registered_vehicle=vehicle, today=deps.now().date(), last_odometer=state["last_odometer"],
        hash_filed_under=prior if prior and prior != vehicle else None,
        invoice_filed_under=inv_prior if inv_prior and inv_prior != vehicle else None,
        owner_names=driver.owner_names, open_actions=tuple(state["open_actions"])))

    deps.records.claim_hash(job["hash"], vehicle, ref)
    if inv_key and decision.outcome != "rejected":
        deps.records.claim_invoice(inv_key, vehicle, ref)
    decided_at = deps.now().isoformat(timespec="seconds")
    rec = dict(base, doc={k: doc[k] for k in KEPT_FIELDS}, outcome=decision.outcome,
               flags=[asdict(f) for f in decision.flags], opened=decision.open_actions, closed=decision.close_actions,
               doc_date=_iso(doc.get("doc_date")), valid_till=_iso(doc.get("validity_till")),
               decided_at=decided_at, read_ms=read_ms)
    if photo:
        rec["photo"] = photo
    params = dict(decision.reply_params)
    if decision.outcome in ACCEPTED and driver.training_token:   # the Train half rides on an accepting reply
        sent = {d["training"]["module"] for d in earlier if d.get("training")}
        choice = choose_module(decision.open_actions, sent)
        if choice:
            slug, reason = choice
            rec["training"] = {"module": slug, "title": module_title(slug), "reason": reason, "sent_at": decided_at,
                               "url": module_link(slug, driver.training_token)}
            params.update(training_title=module_title(slug, driver.language), training_url=rec["training"]["url"])
    deps.records.save(vehicle, rec, decision.open_actions, decision.close_actions)
    logs.event("RULE_DECISION", file=ref, cab=driver.cab_id, doc_type=doc["doc_type"], outcome=decision.outcome,
               flags=decision.codes, opened=decision.open_actions, closed=decision.close_actions, read_ms=read_ms,
               module=(rec.get("training") or {}).get("module"))
    rec["replied"] = reply(deps, driver.phone, decision.reply_key, driver.language, **params)
    _changed(deps, vehicle)
    return rec


def _changed(deps, vehicle: str) -> None:
    if deps.on_change:
        deps.on_change(vehicle)
