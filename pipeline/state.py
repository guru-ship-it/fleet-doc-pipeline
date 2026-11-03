"""The fleet view the dashboard shows, computed from the records on every request: each registered cab with its
consent, documents (newest first), validity dates, open safety actions and a one-line status, plus fleet totals and
the latest activity. Driver names appear (they are the client's own staff list); phone numbers never do."""
import datetime as dt
import hashlib
import json
import statistics

from .logs import hid
from .replies import LABELS, SAFETY_LABELS
from .rules import MORE, REJECT, parse_date, pretty_vehicle

DUE_DAYS = 30
OUTCOMES = {"accepted": "Accepted", "accepted_with_notes": "Accepted, with notes",
            "more_proof_needed": "More proof needed", "rejected": "Rejected", "pending_review": "Stored for review"}
LANGUAGES = {"en": "English", "hi": "Hindi", "te": "Telugu"}


def _label(doc_type) -> str:
    return LABELS.get(doc_type, LABELS["other"])[0]


def _safety(category: str) -> str:
    return SAFETY_LABELS.get(category, (category.replace("_", " "),))[0]


def _seconds(start, end):
    try:
        return max(0, round((dt.datetime.fromisoformat(end) - dt.datetime.fromisoformat(start)).total_seconds()))
    except (TypeError, ValueError):
        return None


def _headline(rec: dict, doc: dict) -> str:
    """The one line a supervisor reads: the strongest problem, else the model's one-sentence summary."""
    flags = rec.get("flags") or []
    for severity in (REJECT, MORE):
        for f in flags:
            if f.get("severity") == severity and f.get("detail"):
                return f["detail"]
    if rec.get("outcome") == "pending_review":
        return "Stored under the restricted prefix for a person to review; never sent to the model"
    notes = [f["detail"] for f in flags if f.get("detail")]
    return doc.get("summary") or (notes[0] if notes else OUTCOMES.get(rec.get("outcome"), ""))


def document_view(rec: dict) -> dict:
    doc = rec.get("doc") or {}
    return {"received_at": rec.get("received_at"), "decided_at": rec.get("decided_at"),
            "seconds": _seconds(rec.get("received_at"), rec.get("decided_at")), "read_ms": rec.get("read_ms"),
            "ref": (rec.get("hash") or "")[:12], "doc_type": doc.get("doc_type"), "label": _label(doc.get("doc_type")),
            "outcome": rec.get("outcome"), "outcome_label": OUTCOMES.get(rec.get("outcome"), rec.get("outcome")),
            "headline": _headline(rec, doc), "doc_date": rec.get("doc_date"), "valid_till": rec.get("valid_till"),
            "workshop": doc.get("workshop_name"), "invoice_no": doc.get("invoice_no"), "gstin": doc.get("gstin"),
            "amount": doc.get("total_amount"), "odometer_km": doc.get("odometer_km"),
            "work_done": list(doc.get("work_done") or []), "advisories": list(doc.get("advisories") or []),
            "summary": doc.get("summary"), "confidence": doc.get("confidence"), "flags": list(rec.get("flags") or []),
            "opened": list(rec.get("opened") or []), "closed": list(rec.get("closed") or []),
            # the module that went out, without the link: the link carries the driver's personal learner token
            "training": {k: v for k, v in rec["training"].items() if k != "url"} if rec.get("training") else None}


def validity_view(profile: dict, today: dt.date) -> list:
    out = []
    for doc_type, v in sorted((profile.get("validity") or {}).items()):
        till = parse_date(v.get("till"))
        days = (till - today).days if till else None
        state = "UNKNOWN" if days is None else "EXPIRED" if days < 0 else "DUE" if days <= DUE_DAYS else "OK"
        out.append({"doc_type": doc_type, "label": _label(doc_type), "till": v.get("till"), "days": days, "state": state})
    return out


def status_view(consent, profile: dict, docs: list, validity: list) -> dict:
    """One line per cab, decided in a fixed order, so the same records always read the same way."""
    open_actions = profile.get("open_actions") or {}
    if open_actions:
        names = ", ".join(_safety(c) for c in sorted(open_actions))
        return {"code": "ACTION", "label": "Safety action open",
                "headline": "Workshop flagged %s; open until a bill shows the fix" % names}
    expired = [v for v in validity if v["state"] == "EXPIRED"]
    if expired:
        return {"code": "ACTION", "label": "Paper expired",
                "headline": "%s expired on %s" % (expired[0]["label"].capitalize(), expired[0]["till"])}
    latest = next((d for d in docs if d["outcome"] != "pending_review"), None)
    if latest and latest["outcome"] == "rejected":
        return {"code": "WATCH", "label": "Resend requested", "headline": latest["headline"]}
    if latest and latest["outcome"] == "more_proof_needed":
        return {"code": "WATCH", "label": "More proof requested", "headline": latest["headline"]}
    due = [v for v in validity if v["state"] == "DUE"]
    if due:
        return {"code": "WATCH", "label": "Renewal due",
                "headline": "%s valid only till %s" % (due[0]["label"].capitalize(), due[0]["till"])}
    if not docs:
        if consent is None:
            return {"code": "NONE", "label": "Consent pending", "headline": "The driver has not replied YES yet"}
        if consent["status"] == "withdrawn":
            return {"code": "NONE", "label": "Consent withdrawn",
                    "headline": "Nothing this driver sends is stored or read"}
        return {"code": "NONE", "label": "No documents yet", "headline": "Consent given; waiting for the first document"}
    return {"code": "GOOD", "label": "Up to date", "headline": (latest or docs[0])["headline"]}


def fleet_state(registry, records, today: dt.date) -> dict:
    cabs, activity, seconds, stamps = [], [], [], []
    for d in sorted(registry.drivers(), key=lambda x: (x.cab_id, x.vehicle_no)):
        profile, recs = records.cab_record(d.vehicle_no)
        # newest first; on equal timestamps the later-stored record wins (stable ascending sort, then reversed)
        docs = [document_view(r) for r in sorted(recs, key=lambda r: r.get("received_at") or "")[::-1]]
        consent = records.consent_status(hid(d.phone))
        validity = validity_view(profile, today)
        counts = {k: sum(1 for x in docs if x["outcome"] == k) for k in OUTCOMES}
        cab = {"cab_id": d.cab_id, "vn": d.vehicle_no, "vehicle": pretty_vehicle(d.vehicle_no), "driver": d.driver_name,
               "language": LANGUAGES.get(d.language, d.language), "lang": d.language, "consent": consent,
               "status": status_view(consent, profile, docs, validity), "last_odometer": profile.get("last_odometer"),
               "last_bill": profile.get("last_bill"), "validity": validity,
               "open_actions": [{"category": c, "label": _safety(c), "opened": v.get("opened"), "ref": v.get("ref")}
                                for c, v in sorted((profile.get("open_actions") or {}).items())],
               "documents": docs, "counts": dict(counts, documents=len(docs)),
               "training": next((x["training"] for x in docs if x.get("training")), None)}
        cabs.append(cab)
        for x in docs:
            activity.append({"at": x["decided_at"] or x["received_at"], "cab_id": d.cab_id, "vehicle": cab["vehicle"],
                             "label": x["label"], "outcome": x["outcome"], "outcome_label": x["outcome_label"],
                             "headline": x["headline"], "seconds": x["seconds"], "ref": x["ref"]})
            if x["seconds"] is not None:
                seconds.append(x["seconds"])
            stamps += [s for s in (x["received_at"], x["decided_at"]) if s]
        if consent and consent.get("at"):
            stamps.append(consent["at"])
    activity.sort(key=lambda a: a["at"] or "", reverse=True)
    kpis = {"cabs": len(cabs),
            "consented": sum(1 for c in cabs if c["consent"] and c["consent"]["status"] == "given"),
            "documents": sum(c["counts"]["documents"] for c in cabs),
            "accepted": sum(c["counts"]["accepted"] + c["counts"]["accepted_with_notes"] for c in cabs),
            "rejected": sum(c["counts"]["rejected"] for c in cabs),
            "needs_more": sum(c["counts"]["more_proof_needed"] for c in cabs),
            "open_actions": sum(len(c["open_actions"]) for c in cabs),
            "papers_due": sum(1 for c in cabs for v in c["validity"] if v["state"] in ("DUE", "EXPIRED")),
            "median_seconds": round(statistics.median(seconds)) if seconds else None}
    return {"client": registry.client, "as_of": max(stamps) if stamps else None, "kpis": kpis,
            "activity": activity[:30], "cabs": cabs}


def etag(state: dict) -> str:
    """Strong ETag over the whole view, so an unchanged fleet costs the browser a 304 and nothing more."""
    return '"%s"' % hashlib.sha256(json.dumps(state, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:32]
