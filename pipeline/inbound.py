"""Inbound WhatsApp in Meta's webhook format. One parser serves both Meta's Cloud API test number (the hackathon
demo) and the live helpline on AWS End User Messaging, which forwards the same entry inside whatsAppWebhookEntry."""
import hashlib
import hmac
import json
from dataclasses import dataclass

from .errors import WebhookAuthError
from .registry import norm_phone


@dataclass(frozen=True)
class Inbound:
    sender: str             # E.164, e.g. +919000000001
    message_id: str
    kind: str               # image | document | text | other
    media_id: str | None
    mime: str | None
    caption: str
    filename: str | None
    text: str
    ts: int


def verify_signature(raw: bytes, header: str, app_secret: str) -> None:
    """Meta signs every webhook POST: X-Hub-Signature-256 = "sha256=" + HMAC-SHA256(app secret, raw body)."""
    if not app_secret:
        raise WebhookAuthError("App secret is not configured")
    if not header or not header.startswith("sha256="):
        raise WebhookAuthError("Missing or malformed signature header")
    expected = hmac.new(app_secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, header.split("=", 1)[1]):
        raise WebhookAuthError("Signature does not match")


def verify_challenge(params: dict, verify_token: str) -> str:
    """The one-time GET handshake when the webhook URL is registered in the Meta app."""
    sent = params.get("hub.verify_token", "")
    if params.get("hub.mode") == "subscribe" and verify_token and hmac.compare_digest(sent, verify_token):
        return params.get("hub.challenge", "")
    raise WebhookAuthError("Verify token does not match")


def _entries(payload: dict) -> list:
    if payload.get("entry") is not None:                       # Cloud API webhook
        return payload["entry"]
    raw = payload.get("whatsAppWebhookEntry")                  # AWS End User Messaging event
    if raw:
        return [json.loads(raw) if isinstance(raw, str) else raw]
    return []


@dataclass(frozen=True)
class Status:
    """A delivery receipt for a message we sent. 'sent' means accepted by WhatsApp; only 'delivered' or 'read'
    means it reached the phone; 'failed' carries Meta's error code and title."""
    message_id: str
    status: str             # sent | delivered | read | failed
    recipient: str          # E.164
    ts: int
    error_code: int | None
    error_title: str


def statuses(payload: dict) -> list:
    """Every delivery receipt in the payload as a Status."""
    out = []
    for entry in _entries(payload):
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for s in value.get("statuses") or []:
                err = (s.get("errors") or [{}])[0] or {}
                detail = (err.get("error_data") or {}).get("details") or err.get("message") or ""
                out.append(Status(message_id=s.get("id", ""), status=s.get("status", ""),
                                  recipient=norm_phone(s.get("recipient_id")), ts=int(s.get("timestamp") or 0),
                                  error_code=err.get("code"),
                                  error_title=" ".join(x for x in (err.get("title"), detail) if x).strip()))
    return out


def parse(payload: dict) -> list:
    """Every inbound message in the payload as an Inbound; delivery statuses are read by statuses()."""
    out = []
    for entry in _entries(payload):
        for change in entry.get("changes") or []:
            value = change.get("value") or {}
            for m in value.get("messages") or []:
                kind = m.get("type", "")
                media = (m.get(kind) or {}) if kind in ("image", "document") else {}
                out.append(Inbound(
                    sender=norm_phone(m.get("from")), message_id=m.get("id", ""),
                    kind=kind if kind in ("image", "document", "text") else "other",
                    media_id=media.get("id"), mime=(media.get("mime_type") or "").split(";")[0].strip() or None,
                    caption=(media.get("caption") or "").strip(), filename=media.get("filename"),
                    text=((m.get("text") or {}).get("body") or "").strip(), ts=int(m.get("timestamp") or 0)))
    return out
