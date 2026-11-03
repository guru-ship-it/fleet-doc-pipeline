"""The only module that talks to the outside world over HTTP: the WhatsApp Cloud API (Graph) for media and
replies, and the document model (OpenAI-compatible, e.g. Meta Muse). Every call logs its status and timing, never
its content, and raises a typed error on anything but success."""
import time

import httpx

from . import logs
from .errors import MediaDownloadError, ModelCallError, SendError

GRAPH = "https://graph.facebook.com"
MAX_MEDIA_BYTES = 16 * 1024 * 1024


def _auth(token: str) -> dict:
    return {"Authorization": "Bearer " + token}


def _ms(t0: float) -> int:
    return round((time.monotonic() - t0) * 1000)


def graph_download_media(media_id: str, token: str, version: str) -> tuple:
    """Fetch an inbound WhatsApp media file: look up its URL, then download it. Returns (bytes, mime)."""
    t0 = time.monotonic()
    try:
        meta = httpx.get(f"{GRAPH}/{version}/{media_id}", headers=_auth(token), timeout=20)
        if meta.status_code != 200:
            logs.event("MEDIA_LOOKUP_FAILED", "error", status=meta.status_code, ms=_ms(t0))
            raise MediaDownloadError("Media lookup returned HTTP %s" % meta.status_code)
        info = meta.json()
        blob = httpx.get(info["url"], headers=_auth(token), timeout=60)
    except httpx.HTTPError as e:
        logs.event("MEDIA_DOWNLOAD_FAILED", "error", error=type(e).__name__, ms=_ms(t0))
        raise MediaDownloadError("Media download failed: %s" % type(e).__name__) from e
    if blob.status_code != 200:
        logs.event("MEDIA_DOWNLOAD_FAILED", "error", status=blob.status_code, ms=_ms(t0))
        raise MediaDownloadError("Media download returned HTTP %s" % blob.status_code)
    if len(blob.content) > MAX_MEDIA_BYTES:
        logs.event("MEDIA_TOO_LARGE", "error", bytes=len(blob.content))
        raise MediaDownloadError("File larger than 16 MB")
    mime = (info.get("mime_type") or blob.headers.get("content-type", "")).split(";")[0].strip()
    logs.event("MEDIA_DOWNLOADED", bytes=len(blob.content), mime=mime, ms=_ms(t0))
    return blob.content, mime


def graph_send_text(to_e164: str, body: str, token: str, phone_number_id: str, version: str) -> str:
    """Send a WhatsApp text reply. Returns Meta's message id. Accepted by the API is NOT delivered: delivery is
    only proven by a later status webhook."""
    t0 = time.monotonic()
    try:
        r = httpx.post(f"{GRAPH}/{version}/{phone_number_id}/messages", headers=_auth(token), timeout=20,
                       json={"messaging_product": "whatsapp", "to": to_e164.lstrip("+"), "type": "text",
                             "text": {"body": body}})
    except httpx.HTTPError as e:
        logs.event("REPLY_FAILED", "error", error=type(e).__name__, ms=_ms(t0))
        raise SendError("Reply failed: %s" % type(e).__name__) from e
    if r.status_code != 200:
        try:   # Meta's error code and title say why (rate limit, window closed, bad token); never the message text
            err = r.json().get("error") or {}
        except ValueError:
            err = {}
        logs.event("REPLY_FAILED", "error", status=r.status_code, ms=_ms(t0), code=err.get("code"),
                   title=(err.get("title") or err.get("message") or "")[:120] or None)
        raise SendError("WhatsApp returned HTTP %s (code %s)" % (r.status_code, err.get("code")))
    msg_id = ((r.json().get("messages") or [{}])[0]).get("id", "")
    logs.event("REPLY_ACCEPTED", wamid=msg_id[-12:], ms=_ms(t0))
    return msg_id


def model_chat(base_url: str, api_key: str, body: dict, timeout: float = 90) -> tuple:
    """POST an OpenAI-compatible chat completion. Returns (response json, latency ms)."""
    t0 = time.monotonic()
    try:
        r = httpx.post(base_url.rstrip("/") + "/chat/completions", headers=_auth(api_key), json=body, timeout=timeout)
    except httpx.HTTPError as e:
        logs.event("MODEL_CALL_FAILED", "error", error=type(e).__name__, ms=_ms(t0))
        raise ModelCallError("Model request failed: %s" % type(e).__name__) from e
    if r.status_code != 200:
        try:
            reason = str((r.json().get("error") or {}).get("type") or "")[:60]
        except ValueError:
            reason = ""
        logs.event("MODEL_CALL_FAILED", "error", status=r.status_code, reason=reason, ms=_ms(t0))
        raise ModelCallError("Model returned HTTP %s" % r.status_code)
    return r.json(), _ms(t0)
