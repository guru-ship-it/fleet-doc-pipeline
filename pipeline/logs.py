"""Structured JSON logs. Phone numbers, names and document text never reach a log line: callers pass hashed ids
(hid), and any field whose name marks personal data is masked as a second line of defence."""
import hashlib
import json
import logging
import sys
import time

_PII_KEYS = {"phone", "sender", "mobile", "driver_name", "owner_name", "billed_to", "caption", "text", "body",
             "address", "message"}

_log = logging.getLogger("fleetdoc")
if not _log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    _h.setFormatter(logging.Formatter("%(message)s"))
    _log.addHandler(_h)
_log.setLevel(logging.INFO)
_log.propagate = False


def hid(value) -> str:
    """Stable, non-reversible id for a phone number or a file: the first 12 hex characters of its SHA-256."""
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()[:12]


def event(name: str, level: str = "info", **fields) -> str:
    """Write one log line: {"event": NAME, "ts": ..., **fields}. Returns the line (useful in tests)."""
    clean = {k: ("***" if k.lower() in _PII_KEYS else v) for k, v in fields.items()}
    line = json.dumps({"event": name, "ts": round(time.time(), 3), **clean}, default=str, ensure_ascii=False)
    getattr(_log, level)(line)
    return line
