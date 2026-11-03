"""The Train half: an accepting reply carries the driver's own module link, in their language; a rejection never
does; a driver without a learner token gets no link; the dashboard sees the module but never the link."""
from dataclasses import replace

from conftest import A, B, consent, last, run, wa

from pipeline.intake import handle_payload
from pipeline.logs import hid
from pipeline.state import fleet_state
from pipeline.training import MODULES, choose_module

LINK = "https://training.advayafm.com/lessons/"


def test_accepted_bill_carries_the_next_module_link(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    rec, = run(env)
    assert rec["training"] == {"module": "tpt-vehicle", "title": "Vehicle care", "reason": "next in sequence",
                               "sent_at": rec["decided_at"], "url": LINK + "tpt-vehicle?k=tokA-test"}
    assert last(env, A).endswith("Your short module on Vehicle care, in your language: " + LINK + "tpt-vehicle?k=tokA-test")
    handle_payload(wa(A, media="INSURANCE_A"), env)
    rec, = run(env)
    assert rec["training"]["module"] == "defensive-v2"                 # one module per accepted document, in order


def test_workshop_advisory_points_at_vehicle_care_once(env):
    consent(env, A)
    handle_payload(wa(A, media="ADVISORY_A"), env)
    rec, = run(env)
    assert rec["outcome"] == "accepted_with_notes" and rec["training"]["reason"] == "workshop advisory"
    assert choose_module(["tyres"], {"tpt-vehicle"}) == ("defensive-v2", "next in sequence")
    assert choose_module([], {slug for slug, _ in MODULES}) is None


def test_rejected_document_and_tokenless_driver_get_no_link(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    run(env)
    consent(env, B, "అవును")
    handle_payload(wa(B, media="INVOICE_A"), env)                      # another cab's bill: rejected
    rec, = run(env)
    assert rec["outcome"] == "rejected" and "training" not in rec and LINK not in last(env, B)
    driver = env.registry.lookup(A)
    assert driver.training_token == "tokA-test"                        # sanity: the rig gives A a token
    tokenless = replace(driver, training_token="")                     # the same driver, not enrolled
    env.registry._by_phone[driver.phone] = env.registry._by_id[hid(driver.phone)] = tokenless
    handle_payload(wa(A, media="FIX_A"), env)
    rec, = run(env)
    assert rec["outcome"] == "accepted" and "training" not in rec and LINK not in last(env, A)


def test_telugu_driver_gets_the_telugu_title(env):
    consent(env, B, "అవును")
    handle_payload(wa(B, media="INVOICE_B"), env)
    rec, = run(env)
    assert rec["outcome"] == "accepted"
    assert "వాహన సంరక్షణ" in last(env, B) and LINK + "tpt-vehicle?k=tokB-test" in last(env, B)


def test_dashboard_shows_the_module_but_never_the_link(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    run(env)
    cab = fleet_state(env.registry, env.records, env.clock[0].date())["cabs"][0]
    assert cab["training"] == {"module": "tpt-vehicle", "title": "Vehicle care", "reason": "next in sequence",
                               "sent_at": cab["documents"][0]["decided_at"]}
    assert "url" not in cab["documents"][0]["training"]
    assert "tokA-test" not in str(fleet_state(env.registry, env.records, env.clock[0].date()))
