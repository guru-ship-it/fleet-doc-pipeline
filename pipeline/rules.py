"""Deterministic checks on what the model read. The model only reads; these rules decide, so every decision is
plain code that can be tested and explained. The five problems found in the manual bill audit (future-dated memo,
wrong vehicle number, bill in a bank's name, spares-only bill, invoice filed under the wrong cab) are covered by
tests/test_rules.py."""
import datetime as dt
import re
from dataclasses import dataclass, field

from .schema import SERVICE_TYPES, VALIDITY_TYPES

# Severity, strongest first. REJECT: cannot be used as proof. MORE: kept on file, more proof needed.
# REVIEW: kept, a person should look. INFO: kept, noted on the cab's record.
REJECT, MORE, REVIEW, INFO = "reject", "more_proof", "review", "info"

SAFETY = {  # advisory category -> words that mark it (matched as whole words, plural allowed)
    "tyres": ("tyre", "tire"),
    "brakes": ("brake", "brake pad", "pad", "shim", "brake shoe"),
    "clutch": ("clutch",),
    "steering": ("steering", "ball joint", "tie rod", "rack end"),
    "suspension": ("suspension", "shock absorber", "strut", "bush"),
    "fuel_system": ("fuel tank", "fuel pipe", "fuel line", "fuel leak"),
}
FIX_WORDS = ("replace", "replaced", "replacement", "new", "fitted", "r&r", "changed", "repair", "repaired",
             "overhaul", "overhauled")
THIRD_PARTY = ("bank", "finance", "finserv", "financial", "capital", "leasing", "nbfc", "insurance company")
GSTIN_RE = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$")
PROOF_INCOMPLETE_TYPES = {"spares_bill", "payment_receipt"}
GSTIN_REQUIRED_TYPES = {"service_invoice", "job_card", "spares_bill", "cash_memo"}

# Reply chosen from the strongest flag, in this order; accepted documents get a "received_*" reply instead.
REPLY_PRIORITY = ["DUPLICATE_FILE", "VEHICLE_MISMATCH", "FUTURE_DATE", "NO_GSTIN", "DUPLICATE_INVOICE",
                  "UNREADABLE", "BILLED_TO_THIRD_PARTY", "NO_VEHICLE_NO", "PROOF_INCOMPLETE", "EXPIRED",
                  "NO_VALIDITY"]


@dataclass(frozen=True)
class Flag:
    code: str
    severity: str
    detail: str


@dataclass
class Context:
    registered_vehicle: str
    today: dt.date
    last_odometer: int | None = None
    hash_filed_under: str | None = None       # another cab this exact file was already filed under
    invoice_filed_under: str | None = None    # another cab this invoice number was already filed under
    owner_names: tuple = ()
    open_actions: tuple = ()                   # safety categories already open on this cab


@dataclass
class Decision:
    outcome: str                               # accepted | accepted_with_notes | more_proof_needed | rejected
    flags: list = field(default_factory=list)
    open_actions: list = field(default_factory=list)    # safety categories this document opens
    close_actions: list = field(default_factory=list)   # open categories this document proves fixed
    reply_key: str = "received_service"
    reply_params: dict = field(default_factory=dict)

    @property
    def codes(self) -> list:
        return [f.code for f in self.flags]


def norm_vehicle(v) -> str:
    return re.sub(r"[^A-Z0-9]", "", str(v or "").upper())


def pretty_vehicle(v) -> str:
    m = re.match(r"^([A-Z]{2})(\d{1,2})([A-Z]{0,3})(\d{1,4})$", norm_vehicle(v))
    return "-".join(x for x in m.groups() if x) if m else norm_vehicle(v)


def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%b-%Y", "%d %b %Y", "%d-%b-%y"):
        try:
            return dt.datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _edit_distance(a: str, b: str) -> int:
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _has_word(text: str, word: str) -> bool:
    return re.search(r"\b" + re.escape(word) + r"s?\b", text) is not None


def categorize(lines) -> set:
    """Safety categories mentioned in a list of advisory or work lines."""
    found = set()
    for line in lines or []:
        low = str(line).lower()
        for cat, words in SAFETY.items():
            if any(_has_word(low, w) for w in words):
                found.add(cat)
    return found


def fixed_categories(work_done) -> set:
    """Categories a document proves were fixed: a work line naming the part together with a fix word."""
    fixed = set()
    for line in work_done or []:
        low = str(line).lower()
        if any(_has_word(low, w) for w in FIX_WORDS):
            fixed |= categorize([line])
    return fixed


def _matches_owner(billed_to: str, owner_names) -> bool:
    b = billed_to.lower()
    return any(n and n.lower() in b for n in owner_names)


def evaluate(doc: dict, ctx: Context) -> Decision:
    flags = []
    dtype = doc.get("doc_type", "other")
    is_service = dtype in SERVICE_TYPES
    reg = norm_vehicle(ctx.registered_vehicle)
    on_doc = norm_vehicle(doc.get("vehicle_no_on_doc"))
    params = {"vehicle": pretty_vehicle(reg), "doc_type": dtype}

    if (doc.get("confidence") or 0) < 0.6:
        flags.append(Flag("UNREADABLE", MORE, "The document could not be read clearly"))

    if on_doc and on_doc != reg:
        near = _edit_distance(on_doc, reg) == 1
        params["other_vehicle"] = pretty_vehicle(on_doc)
        flags.append(Flag("VEHICLE_MISMATCH", REJECT, "Document shows %s; this cab is %s%s" % (
            pretty_vehicle(on_doc), pretty_vehicle(reg), " (one character differs: check the RC copy)" if near else "")))
    elif not on_doc and (is_service or dtype in VALIDITY_TYPES):
        flags.append(Flag("NO_VEHICLE_NO", MORE, "The cab number is not on the document"))

    d = parse_date(doc.get("doc_date"))
    if d:
        params["date"] = d.strftime("%d-%m-%Y")
        if d > ctx.today:
            flags.append(Flag("FUTURE_DATE", REJECT, "Dated %s, after the day it was received" % d.strftime("%d %b %Y")))

    if dtype in GSTIN_REQUIRED_TYPES:
        g = norm_vehicle(doc.get("gstin"))
        if not g:
            flags.append(Flag("NO_GSTIN", REJECT, "No GST number on the bill"))
        elif not GSTIN_RE.match(g):
            flags.append(Flag("GSTIN_FORMAT", REVIEW, "The GST number does not look valid"))

    billed = (doc.get("billed_to") or "").strip()
    if billed and any(_has_word(billed.lower(), w) for w in THIRD_PARTY) and not _matches_owner(billed, ctx.owner_names):
        flags.append(Flag("BILLED_TO_THIRD_PARTY", MORE, "The bill is in a bank's or another business's name"))

    km = doc.get("odometer_km")
    if km is not None:
        params["km"] = km
        if ctx.last_odometer is not None and km < ctx.last_odometer:
            flags.append(Flag("ODOMETER_BACKWARDS", REVIEW,
                              "Odometer %s km is below the last known %s km" % (km, ctx.last_odometer)))

    if ctx.hash_filed_under:
        params["other_vehicle"] = pretty_vehicle(ctx.hash_filed_under)
        flags.append(Flag("DUPLICATE_FILE", REJECT,
                          "This exact file was already received for %s" % pretty_vehicle(ctx.hash_filed_under)))
    elif ctx.invoice_filed_under:
        params["other_vehicle"] = pretty_vehicle(ctx.invoice_filed_under)
        flags.append(Flag("DUPLICATE_INVOICE", REJECT, "Invoice %s was already received for %s" % (
            doc.get("invoice_no"), pretty_vehicle(ctx.invoice_filed_under))))

    if dtype in PROOF_INCOMPLETE_TYPES or (dtype == "job_card" and doc.get("is_estimate")):
        flags.append(Flag("PROOF_INCOMPLETE", MORE, "A workshop job card or the final invoice is needed"))

    if dtype in VALIDITY_TYPES:
        v = parse_date(doc.get("validity_till"))
        if not v:
            flags.append(Flag("NO_VALIDITY", MORE, "The validity date could not be read"))
        else:
            params["valid_till"] = v.strftime("%d-%m-%Y")
            if v < ctx.today:
                flags.append(Flag("EXPIRED", MORE, "Expired on %s" % v.strftime("%d %b %Y")))
            elif (v - ctx.today).days <= 30:
                flags.append(Flag("DUE_SOON", INFO, "Valid only till %s" % v.strftime("%d %b %Y")))

    rejected = any(f.severity == REJECT for f in flags)
    opened, closed = [], []
    if is_service and not rejected:
        fixed = fixed_categories(doc.get("work_done"))
        closed = sorted(fixed & set(ctx.open_actions))
        opened = sorted(categorize(doc.get("advisories")) - fixed - set(ctx.open_actions))
        for cat in opened:
            flags.append(Flag("SAFETY_ADVISORY", INFO, "Workshop flagged %s; open until proof of fix" % cat.replace("_", " ")))
        if opened:
            params["advisories"] = opened

    severities = {f.severity for f in flags}
    if REJECT in severities:
        outcome = "rejected"
    elif MORE in severities:
        outcome = "more_proof_needed"
    elif flags:
        outcome = "accepted_with_notes"
    else:
        outcome = "accepted"

    codes = [f.code for f in flags]
    reply_key = next((c.lower() for c in REPLY_PRIORITY if c in codes), None)
    if reply_key is None:
        if dtype in VALIDITY_TYPES:
            reply_key = "received_validity"
        elif opened:
            reply_key = "received_with_advisory"
        else:
            reply_key = "received_service"
    return Decision(outcome=outcome, flags=flags, open_actions=opened, close_actions=closed,
                    reply_key=reply_key, reply_params=params)
