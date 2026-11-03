"""The fleet view: every registered cab appears, status follows the records in a fixed order, phone numbers never
leave the records, and the ETag only moves when something changed."""
import datetime as dt
import json

from conftest import A, B, C, NOW, consent, run, wa

from pipeline.intake import handle_payload
from pipeline.state import etag, fleet_state


def view(env):
    return fleet_state(env.registry, env.records, env.clock[0].date())


def test_every_registered_cab_is_listed_and_no_phone_number_appears(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    env.clock[0] = NOW + dt.timedelta(seconds=9)
    run(env)
    consent(env, B, "అవును")
    env.clock[0] = NOW + dt.timedelta(seconds=40)
    handle_payload(wa(B, media="INVOICE_A"), env)
    env.clock[0] = NOW + dt.timedelta(seconds=47)
    run(env)

    s = view(env)
    assert [c["cab_id"] for c in s["cabs"]] == ["CAB-01", "CAB-02", "CAB-03"]
    a, b, c = s["cabs"]
    assert a["status"]["code"] == "GOOD" and a["counts"]["documents"] == 1 and a["last_odometer"] == 59985
    assert a["documents"][0]["seconds"] == 9 and a["documents"][0]["outcome"] == "accepted"
    assert b["status"]["code"] == "WATCH" and b["status"]["label"] == "Resend requested"
    assert "TS-09-XY-4521" in b["status"]["headline"] and b["last_odometer"] is None
    assert c["status"]["label"] == "Consent pending" and c["consent"] is None
    assert s["kpis"] == {"cabs": 3, "consented": 2, "documents": 2, "accepted": 1, "rejected": 1, "needs_more": 0,
                         "open_actions": 0, "papers_due": 0, "median_seconds": 8}
    assert [x["cab_id"] for x in s["activity"]] == ["CAB-02", "CAB-01"]      # newest first
    assert s["as_of"] == (NOW + dt.timedelta(seconds=47)).isoformat(timespec="seconds")
    body = json.dumps(s)
    for phone in (A, B, C):
        assert phone not in body and phone.lstrip("+") not in body and phone[3:] not in body


def test_open_safety_action_outranks_everything_until_the_fix_arrives(env):
    consent(env, A)
    handle_payload(wa(A, media="ADVISORY_A"), env)
    run(env)
    a = view(env)["cabs"][0]
    assert a["status"]["code"] == "ACTION" and "tyres" in a["status"]["headline"]
    assert a["open_actions"][0]["label"] == "tyres" and a["documents"][0]["opened"] == ["tyres"]
    env.clock[0] = NOW + dt.timedelta(days=14)
    handle_payload(wa(A, media="FIX_A"), env)
    run(env)
    a = view(env)["cabs"][0]
    assert a["status"]["code"] == "GOOD" and a["open_actions"] == [] and a["documents"][0]["closed"] == ["tyres"]
    assert [x["ref"] for x in a["documents"]] == [x["ref"] for x in sorted(a["documents"], key=lambda x: x["received_at"], reverse=True)]


def test_validity_dates_show_with_their_state(env):
    consent(env, A)
    handle_payload(wa(A, media="INSURANCE_A"), env)
    run(env)
    a = view(env)["cabs"][0]
    assert a["validity"] == [{"doc_type": "insurance", "label": "insurance", "till": "2027-05-18", "days": 208, "state": "OK"}]
    env.clock[0] = dt.datetime(2027, 5, 1, tzinfo=NOW.tzinfo)
    a = view(env)["cabs"][0]
    assert a["validity"][0]["state"] == "DUE" and a["status"]["label"] == "Renewal due"
    env.clock[0] = dt.datetime(2027, 6, 1, tzinfo=NOW.tzinfo)
    a = view(env)["cabs"][0]
    assert a["validity"][0]["state"] == "EXPIRED" and a["status"]["code"] == "ACTION"


def test_withdrawn_consent_reads_as_such(env):
    consent(env, A)
    handle_payload(wa(A, "text", text="STOP"), env)
    a = view(env)["cabs"][0]
    assert a["consent"]["status"] == "withdrawn" and a["status"]["label"] == "Consent withdrawn"


def test_etag_moves_only_when_the_records_change(env):
    consent(env, A)
    first = etag(view(env))
    assert first == etag(view(env))
    handle_payload(wa(A, media="INVOICE_A"), env)
    run(env)
    assert etag(view(env)) != first
