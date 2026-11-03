"""Reply pacing: a driver who sends many files at once gets one "checking" note and evenly spaced results, so
WhatsApp's per-recipient rate limit never swallows the answers. One-off replies (consent) are never held or dropped."""
import dataclasses

from conftest import A, consent, run, wa

from pipeline.intake import handle_payload
from pipeline.records import LocalRecords

ACK = "Received. Checking it now."


def sent_to(env, phone):
    return [body for to, body in env.outbox if to == phone]


def test_burst_gets_one_ack_and_paced_results(env):
    consent(env, A)
    for media in ("INVOICE_A", "ADVISORY_A", "FIX_A"):
        handle_payload(wa(A, media=media), env)
    assert sent_to(env, A).count(ACK) == 1                      # the other two notes were skipped, not queued
    assert env.sleeps == []                                      # the webhook never waits
    run(env)
    msgs = sent_to(env, A)
    assert len(msgs) == 5 and msgs[0].startswith("Thank you") and msgs[1] == ACK
    assert env.sleeps == [3.0, 6.0, 9.0]                         # fixed clock: each result books the slot after the last


def test_slot_is_free_again_once_the_gap_has_passed():
    r = LocalRecords()
    assert r.reserve_send_slot("x", 3, 100.0, 60) == 0
    assert r.reserve_send_slot("x", 3, 100.5, 60) == 2.5
    assert r.reserve_send_slot("y", 3, 100.5, 60) == 0           # another recipient is independent
    assert r.reserve_send_slot("x", 3, 200.0, 60) == 0


def test_a_queue_longer_than_the_limit_is_not_booked():
    r = LocalRecords()
    for _ in range(21):                                          # books slots out to +63 s
        assert r.reserve_send_slot("x", 3, 100.0, 60) is not None
    assert r.reserve_send_slot("x", 3, 100.0, 60) is None        # 63 s > 60 s: nothing booked
    assert r.reserve_send_slot("x", 3, 100.0, 0) is None         # "skip" callers ask for a free slot only
    assert r.reserve_send_slot("x", 3, 163.0, 0) == 0


def test_overflowing_result_is_still_sent(env):
    env.settings = dataclasses.replace(env.settings, reply_max_wait_s=4)
    consent(env, A)
    for media in ("INVOICE_A", "ADVISORY_A", "FIX_A"):
        handle_payload(wa(A, media=media), env)
    run(env)
    assert len(sent_to(env, A)) == 5                             # the third result overflowed the limit and went anyway
    assert env.sleeps == [3.0]                                   # waits of 3 s booked; 6 s was over the 4 s limit


def test_consent_replies_are_immediate_even_in_a_burst(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    handle_payload(wa(A, "text", text="STOP"), env)
    handle_payload(wa(A, "text", text="YES"), env)
    msgs = sent_to(env, A)
    assert msgs[-2].startswith("Your consent is withdrawn") and msgs[-1].startswith("Thank you")
    assert env.sleeps == []


def test_pacing_can_be_switched_off(env):
    env.settings = dataclasses.replace(env.settings, reply_gap_s=0)
    consent(env, A)
    for media in ("INVOICE_A", "ADVISORY_A", "FIX_A"):
        handle_payload(wa(A, media=media), env)
    assert sent_to(env, A).count(ACK) == 3
    run(env)
    assert env.sleeps == []
