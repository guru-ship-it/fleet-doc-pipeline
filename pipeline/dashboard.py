"""The client dashboard: one read-only Lambda behind a function URL serves the page and its assets and answers
GET /api/state from the live records. The page is public; the state needs the access code (Authorization: Bearer),
compared in constant time, and fails closed when no code is configured. The state carries an ETag, so a browser
polling every few seconds gets 304 and no body until a document changes a cab's record."""
import base64
import datetime as dt
import functools
import hmac
import json
import os
import pathlib

from . import logs
from .config import load_secret_into_env
from .records import DynamoRecords, LocalRecords
from .registry import Registry
from .state import etag, fleet_state

SITE = pathlib.Path(__file__).resolve().parent.parent / "dashboard" / "site"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30), "IST")
TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
         ".png": "image/png", ".ico": "image/x-icon", ".svg": "image/svg+xml", ".txt": "text/plain; charset=utf-8"}
BINARY = {".png", ".ico"}
HARDENING = {
    "X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "X-Robots-Tag": "noindex, nofollow",
    "X-Frame-Options": "DENY",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


@functools.lru_cache(maxsize=1)
def _ctx() -> tuple:
    """(registry, records, access code), built once per container."""
    if os.environ.get("SECRET_ID"):
        load_secret_into_env(os.environ["SECRET_ID"])
    registry = Registry.from_file(os.environ.get("REGISTRY_FILE", "demo/registry.example.json"))
    local = os.environ.get("LOCAL_DATA_DIR")
    records = LocalRecords(os.path.join(local, "records.json")) if local else DynamoRecords(os.environ.get("DDB_TABLE", ""))
    return registry, records, os.environ.get("DASHBOARD_KEY", "")


def _response(status: int, body=b"", content_type: str = "text/plain; charset=utf-8", extra: dict | None = None,
              binary: bool = False) -> dict:
    headers = dict(HARDENING, **{"Content-Type": content_type}, **(extra or {}))
    if binary:
        return {"statusCode": status, "headers": headers, "body": base64.b64encode(body).decode("ascii"), "isBase64Encoded": True}
    return {"statusCode": status, "headers": headers, "body": body if isinstance(body, str) else body.decode("utf-8"),
            "isBase64Encoded": False}


def _json(status: int, payload: dict, extra: dict | None = None) -> dict:
    return _response(status, json.dumps(payload, ensure_ascii=False), "application/json; charset=utf-8",
                     dict({"Cache-Control": "no-store"}, **(extra or {})))


def _authorized(headers: dict, key: str) -> bool:
    given = (headers.get("authorization") or "").strip()
    return bool(key) and given.startswith("Bearer ") and hmac.compare_digest(given[7:].strip(), key)


def handle(method: str, path: str, headers: dict | None) -> dict:
    """Route one request. Plain arguments, so tests need no Lambda event."""
    headers = {k.lower(): v for k, v in (headers or {}).items()}
    if method not in ("GET", "HEAD"):
        return _response(405, "method not allowed")
    if path == "/api/state":
        registry, records, key = _ctx()
        if not key:
            logs.event("DASHBOARD_KEY_MISSING", "error")
            return _json(503, {"error": "The dashboard access code is not configured"})
        if not _authorized(headers, key):
            logs.event("DASHBOARD_UNAUTHORIZED", "warning")
            return _json(401, {"error": "Access code required"}, {"WWW-Authenticate": "Bearer"})
        state = fleet_state(registry, records, dt.datetime.now(IST).date())
        tag = etag(state)
        if headers.get("if-none-match") == tag:
            return _response(304, "", extra={"ETag": tag, "Cache-Control": "no-store"})
        return _json(200, state, {"ETag": tag})
    name = "index.html" if path in ("", "/") else path.lstrip("/")
    target = SITE / name
    if "/" in name or name.startswith(".") or not target.is_file() or target.suffix not in TYPES:   # flat folder only
        return _response(404, "not found")
    cache = "no-cache" if target.suffix == ".html" else "public, max-age=300"
    return _response(200, target.read_bytes(), TYPES[target.suffix], {"Cache-Control": cache}, binary=target.suffix in BINARY)


def lambda_dashboard(event, context):
    http = (event.get("requestContext") or {}).get("http") or {}
    return handle(http.get("method", "GET"), event.get("rawPath") or "/", event.get("headers") or {})
