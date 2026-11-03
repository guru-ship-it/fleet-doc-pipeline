"""Intake: what happens when a WhatsApp message arrives, before any model sees anything. An unknown number gets a
reply and nothing is stored. A driver who has not consented gets the consent request and nothing is stored; STOP
withdraws consent. Otherwise the file is downloaded, hashed, stored encrypted and queued for the worker."""
import hashlib
import time
from dataclasses import dataclass
from typing import Callable

from . import logs, replies
from .errors import SendError
from .inbound import parse
from .logs import hid
from .store import object_key

CONSENT_WORDS = {"YES", "Y", "AGREE", "I AGREE", "हाँ", "हां", "అవును"}
STOP_WORDS = {"STOP", "UNSUBSCRIBE"}
MEDICAL_WORDS = ("medical", "मेडिकल", "మెడికల్")


@dataclass
class Deps:
    settings: object
    registry: object
    records: object
    store: object
    queue: object
    model: object = None
    fetch_media: Callable = None    # media_id -> (bytes, mime)
    send: Callable = None           # (to_e164, body) -> message id
    now: Callable = None            # -> timezone-aware datetime
    sleep: Callable = time.sleep    # seconds -> None; replaced in tests
    on_change: Callable = None      # vehicle -> None; asks for a dashboard rebuild


def reply(deps: Deps, to: str, key: str, lang: str = "en", pace: str = "wait", **params) -> bool:
    """Send one templated reply. A failed send is logged as an error and reported to the caller, never hidden.

    Replies to one driver are spaced reply_gap_s apart, because WhatsApp rejects a burst of messages to the same
    person (a driver who sends ten bills at once would otherwise lose most of the answers). pace="wait" holds the
    send for its slot (the worker, which has time). pace="skip" drops the reply when the slot is not free (the
    webhook's "checking it now" note, which the result makes redundant). pace="none" sends at once (one-off replies
    such as consent)."""
    params.setdefault("client", deps.registry.client or "the fleet")
    gap = deps.settings.reply_gap_s
    if gap > 0 and pace != "none":
        limit = deps.settings.reply_max_wait_s if pace == "wait" else 0
        wait = deps.records.reserve_send_slot(hid(to), gap, deps.now().timestamp(), limit)
        if wait is None and pace == "skip":
            logs.event("REPLY_SKIPPED_PACING", template=key, to_id=hid(to))
            return False
        if wait is None:   # the queue for this driver is longer than we will hold a worker: send anyway
            logs.event("REPLY_PACING_OVERFLOW", "warning", template=key, to_id=hid(to))
        elif wait > 0:
            logs.event("REPLY_PACED", template=key, to_id=hid(to), wait_s=round(wait, 1))
            deps.sleep(wait)
    try:
        deps.send(to, replies.render(key, lang, **params))
        return True
    except SendError:
        logs.event("REPLY_NOT_SENT", "error", template=key, to_id=hid(to))
        return False


def handle_payload(payload: dict, deps: Deps) -> list:
    return [_handle(msg, deps) for msg in parse(payload)]


def _handle(msg, deps: Deps) -> dict:
    sender_id = hid(msg.sender)
    driver = deps.registry.lookup(msg.sender)
    if driver is None:
        logs.event("UNREGISTERED_SENDER", sender_id=sender_id, kind=msg.kind)
        reply(deps, msg.sender, "not_registered", pace="none")
        return {"status": "not_registered"}
    lang, consented = driver.language, deps.records.has_consent(sender_id)

    # The webhook never waits for a send slot: Meta expects its answer within seconds.
    if msg.kind == "text":
        word = msg.text.strip().upper().rstrip(".!")
        if word in STOP_WORDS:   # DPDP: withdrawing must be as easy as agreeing
            if consented:
                deps.records.withdraw_consent(sender_id, deps.now().isoformat(timespec="seconds"))
                logs.event("CONSENT_WITHDRAWN", sender_id=sender_id, cab=driver.cab_id)
            reply(deps, driver.phone, "consent_withdrawn", lang, pace="none")
            return {"status": "consent_withdrawn"}
        if word in CONSENT_WORDS:
            if not consented:
                deps.records.set_consent(sender_id, deps.now().isoformat(timespec="seconds"))
                logs.event("CONSENT_RECORDED", sender_id=sender_id, cab=driver.cab_id)
            reply(deps, driver.phone, "consent_thanks", lang, pace="none")
            return {"status": "consent"}
        reply(deps, driver.phone, "how_to" if consented else "consent_request", lang, pace="none")
        return {"status": "text"}
    if msg.kind not in ("image", "document"):
        reply(deps, driver.phone, "unsupported", lang, pace="skip")
        return {"status": "unsupported"}
    if not consented:
        logs.event("CONSENT_REQUIRED", sender_id=sender_id, cab=driver.cab_id)
        reply(deps, driver.phone, "consent_request", lang, pace="skip")
        return {"status": "consent_requested"}

    data, mime = deps.fetch_media(msg.media_id)
    mime = mime or msg.mime or ""
    file_hash = hashlib.sha256(data).hexdigest()
    received = deps.now()
    medical = any(w in msg.caption.lower() for w in MEDICAL_WORDS)
    key = object_key(driver.vehicle_no, received, file_hash, mime, medical)
    deps.store.put(key, data, mime)
    job = {"sender_id": sender_id, "key": key, "hash": file_hash, "mime": mime, "medical": medical,
           "received_at": received.isoformat(timespec="seconds")}
    deps.queue.send(job)
    logs.event("DOC_RECEIVED", file=file_hash[:12], cab=driver.cab_id, mime=mime, bytes=len(data), medical=medical)
    if deps.settings.ack_on_receipt:   # one note per burst is enough; the result reply follows each file anyway
        reply(deps, driver.phone, "received_checking", lang, pace="skip")
    return {"status": "queued", "job": job}
