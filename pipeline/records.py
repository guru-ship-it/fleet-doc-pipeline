"""The records store: consent and its withdrawal, duplicate guards (file hash and invoice number, across all cabs), each cab's profile
(last odometer, validity dates, last bill, open safety actions), its document log, and one send slot per recipient
that paces replies. DynamoRecords uses one DynamoDB table in ap-south-1 (pk/sk); LocalRecords keeps the same shapes
in a JSON file for development."""
import copy
import json
import os
import re
from decimal import Decimal

from . import logs
from .config import REGION
from .errors import StorageError
from .schema import SERVICE_TYPES, VALIDITY_TYPES


def invoice_key(doc: dict) -> str | None:
    """Issuer + invoice number, so two workshops that both print "Invoice 892" never collide."""
    inv = re.sub(r"[^A-Z0-9]", "", str(doc.get("invoice_no") or "").upper())
    if not inv:
        return None
    issuer = re.sub(r"[^A-Z0-9]", "", str(doc.get("gstin") or doc.get("workshop_name") or "").upper())
    return issuer + "#" + inv


def empty_profile() -> dict:
    return {"last_odometer": None, "open_actions": {}, "validity": {}, "last_bill": None}


def apply_profile(profile: dict, rec: dict, opened: list, closed: list) -> dict:
    """The cab profile after one document. Rejected documents never move the odometer, validity or last bill."""
    p = copy.deepcopy(profile) if profile else empty_profile()
    doc = rec.get("doc") or {}
    if rec["outcome"] != "rejected":
        km = doc.get("odometer_km")
        if km is not None and (p["last_odometer"] is None or km > p["last_odometer"]):
            p["last_odometer"] = km
        if doc.get("doc_type") in VALIDITY_TYPES and rec.get("valid_till"):
            p["validity"][doc["doc_type"]] = {"till": rec["valid_till"], "ref": rec["hash"][:12]}
        if doc.get("doc_type") in SERVICE_TYPES:
            prev = p.get("last_bill") or {}
            if (rec.get("doc_date") or "") >= (prev.get("date") or ""):
                p["last_bill"] = {"date": rec.get("doc_date"), "km": km, "workshop": doc.get("workshop_name"),
                                  "doc_type": doc["doc_type"], "ref": rec["hash"][:12]}
    for cat in opened:
        p["open_actions"][cat] = {"opened": rec["received_at"], "ref": rec["hash"][:12]}
    for cat in closed:
        p["open_actions"].pop(cat, None)
    return p


class LocalRecords:
    def __init__(self, path: str | None = None):
        self.path = path
        self.data = {"consent": {}, "hashes": {}, "invoices": {}, "cabs": {}, "docs": {}}
        if path and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                self.data = json.load(f)

    def _flush(self):
        if self.path:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=1)
            os.replace(tmp, self.path)

    def has_consent(self, sender_id: str) -> bool:
        return sender_id in self.data["consent"]

    def set_consent(self, sender_id: str, at: str) -> None:
        self.data["consent"][sender_id] = at
        self._flush()

    def withdraw_consent(self, sender_id: str, at: str) -> None:
        self.data["consent"].pop(sender_id, None)
        self.data.setdefault("withdrawn", {})[sender_id] = at
        self._flush()

    def consent_status(self, sender_id: str):
        """{"status": "given" | "withdrawn", "at": iso} or None when the driver has never answered."""
        if sender_id in self.data["consent"]:
            return {"status": "given", "at": self.data["consent"][sender_id]}
        at = self.data.get("withdrawn", {}).get(sender_id)
        return {"status": "withdrawn", "at": at} if at else None

    def reserve_send_slot(self, to_id: str, gap_s: float, now_s: float, max_wait_s: float):
        """Book the next send time for one recipient and return how long to wait for it. Slots are gap_s apart, so a
        burst of documents never trips WhatsApp's per-recipient rate limit. None when the wait would exceed
        max_wait_s: nothing is booked and the caller decides."""
        slots = self.data.setdefault("send_slots", {})
        start = max(float(slots.get(to_id) or 0), now_s)
        if start - now_s > max_wait_s:
            return None
        slots[to_id] = start + gap_s
        self._flush()
        return start - now_s

    def seen_hash(self, file_hash: str):
        return (self.data["hashes"].get(file_hash) or {}).get("vehicle")

    def claim_hash(self, file_hash: str, vehicle: str, ref: str) -> None:
        self.data["hashes"].setdefault(file_hash, {"vehicle": vehicle, "ref": ref})
        self._flush()

    def seen_invoice(self, key: str):
        return (self.data["invoices"].get(key) or {}).get("vehicle")

    def claim_invoice(self, key: str, vehicle: str, ref: str) -> None:
        self.data["invoices"].setdefault(key, {"vehicle": vehicle, "ref": ref})
        self._flush()

    def has_document(self, vehicle: str, file_hash: str) -> bool:
        return any(d["hash"] == file_hash for d in self.data["docs"].get(vehicle, []))

    def profile(self, vehicle: str) -> dict:
        return copy.deepcopy(self.data["cabs"].get(vehicle) or empty_profile())

    def cab_state(self, vehicle: str) -> dict:
        p = self.profile(vehicle)
        return {"last_odometer": p["last_odometer"], "open_actions": sorted(p["open_actions"])}

    def save(self, vehicle: str, rec: dict, opened: list, closed: list) -> None:
        self.data["docs"].setdefault(vehicle, []).append(rec)
        self.data["cabs"][vehicle] = apply_profile(self.data["cabs"].get(vehicle), rec, opened, closed)
        self._flush()

    def documents(self, vehicle: str) -> list:
        return copy.deepcopy(self.data["docs"].get(vehicle, []))

    def cab_record(self, vehicle: str) -> tuple:
        """(profile, documents) for the dashboard."""
        return self.profile(vehicle), self.documents(vehicle)


def _to_ddb(obj):
    return json.loads(json.dumps(obj), parse_float=Decimal)


def _from_ddb(obj):
    return json.loads(json.dumps(obj, default=lambda d: int(d) if d == d.to_integral_value() else float(d)))


class DynamoRecords:
    def __init__(self, table_name: str, resource=None):
        if not table_name:
            raise StorageError("DynamoDB table is not configured")
        import boto3
        self.t = (resource or boto3.resource("dynamodb", region_name=REGION)).Table(table_name)

    def _call(self, fn, **kw):
        from botocore.exceptions import BotoCoreError, ClientError
        try:
            return fn(**kw)
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None
            logs.event("DDB_FAILED", "error", op=fn.__name__, error=e.response.get("Error", {}).get("Code"))
            raise StorageError("DynamoDB rejected %s" % fn.__name__) from e
        except BotoCoreError as e:
            logs.event("DDB_FAILED", "error", op=fn.__name__, error=type(e).__name__)
            raise StorageError("DynamoDB call failed") from e

    def _get(self, pk: str, sk: str):
        item = (self._call(self.t.get_item, Key={"pk": pk, "sk": sk}) or {}).get("Item")
        return _from_ddb(item) if item else None

    def _put_once(self, item: dict) -> None:
        self._call(self.t.put_item, Item=_to_ddb(item), ConditionExpression="attribute_not_exists(pk)")

    def has_consent(self, sender_id: str) -> bool:
        return self._get("CONSENT#" + sender_id, "CONSENT") is not None

    def set_consent(self, sender_id: str, at: str) -> None:
        self._call(self.t.put_item, Item={"pk": "CONSENT#" + sender_id, "sk": "CONSENT", "at": at})

    def withdraw_consent(self, sender_id: str, at: str) -> None:
        # Consent goes first, so a failure part-way leaves the driver withdrawn rather than still consented.
        self._call(self.t.delete_item, Key={"pk": "CONSENT#" + sender_id, "sk": "CONSENT"})
        self._call(self.t.put_item, Item={"pk": "CONSENT#" + sender_id, "sk": "WITHDRAWN", "at": at})

    def consent_status(self, sender_id: str):
        """{"status": "given" | "withdrawn", "at": iso} or None. A live CONSENT item outranks an older WITHDRAWN one."""
        from boto3.dynamodb.conditions import Key
        by_sk = {i["sk"]: _from_ddb(i) for i in self._query_all(Key("pk").eq("CONSENT#" + sender_id))}
        if "CONSENT" in by_sk:
            return {"status": "given", "at": by_sk["CONSENT"].get("at")}
        if "WITHDRAWN" in by_sk:
            return {"status": "withdrawn", "at": by_sk["WITHDRAWN"].get("at")}
        return None

    def reserve_send_slot(self, to_id: str, gap_s: float, now_s: float, max_wait_s: float):
        """Same contract as LocalRecords.reserve_send_slot. The slot is one item per recipient; a conditional write
        makes the booking atomic when several workers answer the same driver at once."""
        pk, sk = "SEND#" + to_id, "SLOT"
        for _ in range(5):
            current = self._get(pk, sk)
            booked_ms = int(current["next_ms"]) if current else None
            start = max((booked_ms or 0) / 1000.0, now_s)
            if start - now_s > max_wait_s:
                return None
            item = {"pk": pk, "sk": sk, "next_ms": int(round((start + gap_s) * 1000))}
            if booked_ms is None:
                done = self._call(self.t.put_item, Item=item, ConditionExpression="attribute_not_exists(pk)")
            else:
                done = self._call(self.t.put_item, Item=item, ConditionExpression="next_ms = :b",
                                  ExpressionAttributeValues={":b": booked_ms})
            if done is not None:   # None means another worker booked first: read again
                return start - now_s
        logs.event("SEND_SLOT_CONTENDED", "warning", to_id=to_id)
        return 0.0

    def seen_hash(self, file_hash: str):
        return (self._get("HASH#" + file_hash, "FILE") or {}).get("vehicle")

    def claim_hash(self, file_hash: str, vehicle: str, ref: str) -> None:
        self._put_once({"pk": "HASH#" + file_hash, "sk": "FILE", "vehicle": vehicle, "ref": ref})

    def seen_invoice(self, key: str):
        return (self._get("INV#" + key, "INVOICE") or {}).get("vehicle")

    def claim_invoice(self, key: str, vehicle: str, ref: str) -> None:
        self._put_once({"pk": "INV#" + key, "sk": "INVOICE", "vehicle": vehicle, "ref": ref})

    def _query_all(self, condition) -> list:
        items, kw = [], {"KeyConditionExpression": condition}
        while True:
            page = self._call(self.t.query, **kw) or {}
            items += page.get("Items", [])
            if "LastEvaluatedKey" not in page:
                return items
            kw["ExclusiveStartKey"] = page["LastEvaluatedKey"]

    def documents(self, vehicle: str) -> list:
        from boto3.dynamodb.conditions import Key
        return [_from_ddb(i)["rec"] for i in self._query_all(Key("pk").eq("CAB#" + vehicle) & Key("sk").begins_with("DOC#"))]

    def has_document(self, vehicle: str, file_hash: str) -> bool:
        return any(d["hash"] == file_hash for d in self.documents(vehicle))

    def profile(self, vehicle: str) -> dict:
        item = self._get("CAB#" + vehicle, "PROFILE")
        return item["profile"] if item else empty_profile()

    def cab_record(self, vehicle: str) -> tuple:
        """(profile, documents) in one query: the dashboard reads every cab on every poll."""
        from boto3.dynamodb.conditions import Key
        profile, docs = empty_profile(), []
        for raw in self._query_all(Key("pk").eq("CAB#" + vehicle)):
            item = _from_ddb(raw)
            if item["sk"] == "PROFILE":
                profile = item["profile"]
            elif item["sk"].startswith("DOC#"):
                docs.append(item["rec"])
        return profile, docs

    def cab_state(self, vehicle: str) -> dict:
        p = self.profile(vehicle)
        return {"last_odometer": p["last_odometer"], "open_actions": sorted(p["open_actions"])}

    def save(self, vehicle: str, rec: dict, opened: list, closed: list) -> None:
        self._call(self.t.put_item, Item=_to_ddb({"pk": "CAB#" + vehicle,
                                                  "sk": "DOC#%s#%s" % (rec["received_at"], rec["hash"][:12]), "rec": rec}))
        profile = apply_profile(self.profile(vehicle), rec, opened, closed)
        self._call(self.t.put_item, Item=_to_ddb({"pk": "CAB#" + vehicle, "sk": "PROFILE", "profile": profile}))
