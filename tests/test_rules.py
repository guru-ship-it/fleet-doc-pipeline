"""Rule checks, including the five problems found in the manual audit of real service bills. All vehicles, names
and amounts here are synthetic; the patterns are the real ones."""
import datetime as dt

from pipeline.rules import Context, evaluate, categorize, fixed_categories

TODAY = dt.date(2026, 10, 22)
CAB_A, CAB_B = "TS09XY4521", "TS09XY7730"
GSTIN = "36ABCDE1234F1Z5"


def doc(**over):
    base = {"doc_type": "service_invoice", "is_estimate": False, "vehicle_no_on_doc": CAB_A, "doc_date": "2026-09-12",
            "odometer_km": 59985, "workshop_name": "Sample Toyota, Kondapur", "gstin": GSTIN, "invoice_no": "TXP26-28297",
            "billed_to": "R. Kumar", "total_amount": 15835.0, "work_done": ["60,000 km periodic service"],
            "advisories": [], "validity_till": None, "summary": "Periodic service.", "confidence": 0.95}
    base.update(over)
    return base


def ctx(**over):
    base = dict(registered_vehicle=CAB_A, today=TODAY)
    base.update(over)
    return Context(**base)


# ---- the five audit problems -------------------------------------------------------------------------------

def test_audit_1_future_dated_memo():
    d = evaluate(doc(doc_type="cash_memo", doc_date="2026-10-31", gstin=None, invoice_no="935"), ctx())
    assert d.outcome == "rejected"
    assert {"FUTURE_DATE", "NO_GSTIN"} <= set(d.codes)
    assert d.reply_key == "future_date"


def test_audit_2_wrong_vehicle_number():
    d = evaluate(doc(doc_type="cash_memo", vehicle_no_on_doc="TS09XV4521", gstin=None, odometer_km=None), ctx())
    assert d.outcome == "rejected"
    mismatch = next(f for f in d.flags if f.code == "VEHICLE_MISMATCH")
    assert "one character differs" in mismatch.detail
    assert d.reply_key == "vehicle_mismatch" and d.reply_params["other_vehicle"] == "TS-09-XV-4521"


def test_audit_3_bill_in_a_banks_name():
    d = evaluate(doc(doc_type="spares_bill", vehicle_no_on_doc=None, odometer_km=None,
                     billed_to="Example First Bank, Secunderabad Branch"), ctx())
    assert d.outcome == "more_proof_needed"
    assert {"BILLED_TO_THIRD_PARTY", "NO_VEHICLE_NO", "PROOF_INCOMPLETE"} <= set(d.codes)
    assert d.reply_key == "billed_to_third_party"


def test_audit_4_spares_only_bill():
    d = evaluate(doc(doc_type="spares_bill", billed_to="TS 09 XY 4521", odometer_km=None), ctx())
    assert d.outcome == "more_proof_needed"
    assert d.codes == ["PROOF_INCOMPLETE"]
    assert d.reply_key == "proof_incomplete"


def test_audit_5_invoice_filed_under_the_wrong_cab():
    # Cab B's driver sends the invoice that was already filed for cab A.
    d = evaluate(doc(), ctx(registered_vehicle=CAB_B, hash_filed_under=CAB_A))
    assert d.outcome == "rejected"
    assert {"DUPLICATE_FILE", "VEHICLE_MISMATCH"} <= set(d.codes)
    assert d.reply_key == "duplicate_file" and d.reply_params["other_vehicle"] == "TS-09-XY-4521"


# ---- accepted documents and safety actions -----------------------------------------------------------------

def test_valid_insurance_is_accepted_with_validity_in_reply():
    d = evaluate(doc(doc_type="insurance", doc_date="2026-05-19", validity_till="2027-05-18", gstin=None,
                     odometer_km=None, work_done=[]), ctx())
    assert d.outcome == "accepted" and d.reply_key == "received_validity"
    assert d.reply_params["valid_till"] == "18-05-2027"


def test_expired_insurance_needs_the_current_one():
    d = evaluate(doc(doc_type="insurance", validity_till="2026-06-06", gstin=None, odometer_km=None), ctx())
    assert d.outcome == "more_proof_needed" and d.reply_key == "expired"


def test_insurance_due_within_30_days_is_noted():
    d = evaluate(doc(doc_type="insurance", validity_till="2026-11-10", gstin=None, odometer_km=None), ctx())
    assert d.outcome == "accepted_with_notes" and "DUE_SOON" in d.codes


def test_safety_advisory_opens_an_action():
    d = evaluate(doc(advisories=["All tyres hard and worn", "Front wiper rubber damaged"]), ctx())
    assert d.outcome == "accepted_with_notes"
    assert d.open_actions == ["tyres"]
    assert d.reply_key == "received_with_advisory"


def test_proof_of_fix_closes_the_action():
    d = evaluate(doc(work_done=["Rear tyres replaced (2 nos)", "Wheel alignment"]), ctx(open_actions=("tyres",)))
    assert d.close_actions == ["tyres"] and d.open_actions == []
    assert d.outcome == "accepted"


def test_rejected_bill_cannot_close_an_action():
    d = evaluate(doc(doc_date="2026-12-01", work_done=["Clutch plate replaced"]), ctx(open_actions=("clutch",)))
    assert d.outcome == "rejected" and d.close_actions == []


def test_odometer_going_backwards_is_flagged_for_review():
    d = evaluate(doc(odometer_km=89000), ctx(last_odometer=98000))
    assert "ODOMETER_BACKWARDS" in d.codes and d.outcome == "accepted_with_notes"


def test_estimate_job_card_needs_the_final_invoice():
    d = evaluate(doc(doc_type="job_card", is_estimate=True), ctx())
    assert "PROOF_INCOMPLETE" in d.codes and d.outcome == "more_proof_needed"


def test_low_confidence_asks_for_a_clearer_photo():
    d = evaluate(doc(confidence=0.4), ctx())
    assert d.reply_key == "unreadable" and d.outcome == "more_proof_needed"


def test_same_invoice_number_under_another_cab_is_a_duplicate():
    d = evaluate(doc(vehicle_no_on_doc=CAB_B), ctx(registered_vehicle=CAB_B, invoice_filed_under=CAB_A))
    assert "DUPLICATE_INVOICE" in d.codes and d.outcome == "rejected"


def test_word_matching_does_not_misfire():
    assert categorize(["Discount 10%", "Padding for seat"]) == set()
    assert fixed_categories(["Discount on front brake pads"]) == set()   # no fix word
    assert fixed_categories(["Front disc brake pads replaced"]) == {"brakes"}
