"""What the model must return for every document: a strict JSON schema used as structured output, and the
validator that holds the model to it."""
import jsonschema

DOC_TYPES = ["service_invoice", "job_card", "spares_bill", "cash_memo", "payment_receipt", "insurance", "puc",
             "rc", "permit", "fitness", "road_tax", "medical_certificate", "police_verification", "other"]
SERVICE_TYPES = {"service_invoice", "job_card", "spares_bill", "cash_memo", "payment_receipt"}
VALIDITY_TYPES = {"insurance", "puc", "rc", "permit", "fitness", "road_tax"}


def _nullable(kind: str, description: str) -> dict:
    return {"type": [kind, "null"], "description": description}


DOCUMENT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "doc_type": {"type": "string", "enum": DOC_TYPES, "description": "What kind of document this is"},
        "is_estimate": {"type": "boolean",
                        "description": "True when the document says estimate, quotation or proforma"},
        "vehicle_no_on_doc": _nullable("string", "Vehicle registration number exactly as printed"),
        "doc_date": _nullable("string", "Date of the document, YYYY-MM-DD"),
        "odometer_km": _nullable("integer", "Odometer or mileage reading in km"),
        "workshop_name": _nullable("string", "Workshop, dealer, shop or issuer name"),
        "gstin": _nullable("string", "GSTIN of the issuer, as printed"),
        "invoice_no": _nullable("string", "Invoice, bill, memo, job card or policy number"),
        "billed_to": _nullable("string", "Name in the Bill to / Customer / Buyer field"),
        "total_amount": _nullable("number", "Grand total in rupees"),
        "work_done": {"type": "array", "items": {"type": "string"},
                      "description": "Jobs done and parts supplied, one per item"},
        "advisories": {"type": "array", "items": {"type": "string"},
                       "description": "Work the workshop recommended but did not do"},
        "validity_till": _nullable("string", "Valid-till or expiry date, YYYY-MM-DD"),
        "summary": {"type": "string", "description": "One plain sentence on what the document shows"},
        "confidence": {"type": "number", "minimum": 0, "maximum": 1,
                       "description": "Confidence (0 to 1) that the fields above are read correctly"},
    },
}
DOCUMENT_SCHEMA["required"] = list(DOCUMENT_SCHEMA["properties"])


def validate(doc: dict) -> dict:
    """Raise jsonschema.ValidationError unless doc fits DOCUMENT_SCHEMA exactly; return it otherwise."""
    jsonschema.validate(doc, DOCUMENT_SCHEMA)
    return doc
