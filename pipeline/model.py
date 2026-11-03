"""Reading a document: page images in, a schema-checked dict out. MuseModel calls Meta's Model API (hosted outside
India), so it may only ever see synthetic demo documents; the worker enforces that through `in_india`.
StandInModel returns prepared readings, for tests and rehearsals without network access."""
import base64
import json

import fitz  # PyMuPDF
import jsonschema

from . import bridge, logs
from .errors import ModelCallError
from .schema import DOCUMENT_SCHEMA, validate

SYSTEM_PROMPT = (
    "You read documents for a cab fleet's compliance records in India: vehicle service invoices, job cards, "
    "spares bills, cash memos, payment receipts, insurance, PUC, RC, permit, fitness, road tax, police "
    "verification certificates and driver medical certificates. Report only what is printed on the document and "
    "never guess: use null when a field is absent or unreadable. Dates as YYYY-MM-DD. vehicle_no_on_doc is the "
    "registration number exactly as printed. billed_to is the name in the Bill to, Customer or Buyer field. "
    "is_estimate is true when the document says estimate, quotation or proforma. work_done lists the jobs done "
    "and parts supplied. advisories lists work the workshop recommended but did not do. summary is one plain "
    "sentence on what the document shows. confidence is how sure you are, from 0 to 1, that the fields are read "
    "correctly."
)
IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp"}


def to_pages(data: bytes, mime: str, max_pages: int = 3) -> list:
    """Return [(image bytes, mime)] for the model: images as they are, PDFs rendered page by page."""
    if mime in IMAGE_TYPES:
        return [(data, mime)]
    if mime == "application/pdf":
        with fitz.open(stream=data, filetype="pdf") as pdf:
            return [(page.get_pixmap(dpi=150).tobytes("jpg"), "image/jpeg") for page in list(pdf)[:max_pages]]
    raise ModelCallError("Unsupported file type: %s" % mime)


class MuseModel:
    """Meta Model API (OpenAI-compatible) with vision and JSON-schema structured output."""
    in_india = False

    def __init__(self, base_url: str, api_key: str, model_id: str):
        if not (base_url and api_key and model_id):
            raise ModelCallError("Model API settings are missing (base URL, key or model id)")
        self.base_url, self.api_key, self.model_id = base_url, api_key, model_id

    def extract(self, pages: list, file_hash: str) -> dict:
        content = [{"type": "text", "text": "Read this document and return the fields."}]
        for data, mime in pages:
            content.append({"type": "image_url",
                            "image_url": {"url": "data:%s;base64,%s" % (mime, base64.b64encode(data).decode())}})
        body = {"model": self.model_id, "temperature": 0,
                "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": content}],
                "response_format": {"type": "json_schema",
                                    "json_schema": {"name": "fleet_document", "strict": True, "schema": DOCUMENT_SCHEMA}}}
        out, ms = bridge.model_chat(self.base_url, self.api_key, body)
        try:
            doc = validate(json.loads(out["choices"][0]["message"]["content"]))
        except (KeyError, IndexError, TypeError, ValueError, jsonschema.ValidationError) as e:
            logs.event("MODEL_OUTPUT_INVALID", "error", file=file_hash[:12], model=self.model_id, ms=ms,
                       error=type(e).__name__)
            raise ModelCallError("Model output did not fit the schema") from e
        usage = out.get("usage") or {}
        logs.event("MODEL_CALL", file=file_hash[:12], model=self.model_id, ms=ms, pages=len(pages),
                   doc_type=doc["doc_type"], confidence=doc["confidence"],
                   prompt_tokens=usage.get("prompt_tokens"), completion_tokens=usage.get("completion_tokens"))
        return doc


class StandInModel:
    """Returns a prepared reading per file hash. No network, so it is safe for any data."""
    in_india = True

    def __init__(self, readings: dict):
        self.readings = readings

    def extract(self, pages: list, file_hash: str) -> dict:
        if file_hash not in self.readings:
            raise ModelCallError("The stand-in model has no reading for this file")
        doc = validate(dict(self.readings[file_hash]))
        logs.event("MODEL_CALL", file=file_hash[:12], model="stand-in", ms=0, pages=len(pages),
                   doc_type=doc["doc_type"], confidence=doc["confidence"])
        return doc
