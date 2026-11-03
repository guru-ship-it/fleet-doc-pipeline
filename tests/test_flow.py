"""End to end through intake and worker with local stand-ins: no network, no AWS. Synthetic drivers and cabs only.
The rig (drivers, readings, env fixture, helpers) lives in conftest.py."""
import pytest
from conftest import A, B, C, H, STRANGER, consent, last, run, wa

from pipeline.errors import ResidencyError
from pipeline.intake import handle_payload


def test_unknown_number_is_told_and_nothing_is_stored(env, tmp_path):
    handle_payload(wa(STRANGER, media="INVOICE_A"), env)
    assert "not registered" in last(env, STRANGER)
    assert env.queue.jobs == [] and not (tmp_path / "files").exists()


def test_no_upload_is_kept_before_consent(env, tmp_path):
    handle_payload(wa(A, media="INVOICE_A"), env)
    assert "Reply YES to agree" in last(env, A) and "Example Tech Park" in last(env, A)
    assert env.queue.jobs == [] and not (tmp_path / "files").exists()
    consent(env, A)
    assert last(env, A).startswith("Thank you")


def test_consent_request_says_how_to_withdraw(env):
    handle_payload(wa(A, media="INVOICE_A"), env)
    assert "withdraw at any time by replying STOP" in last(env, A)


def test_stop_withdraws_consent_and_nothing_more_is_stored(env, tmp_path):
    consent(env, A)
    handle_payload(wa(A, "text", text="stop"), env)
    assert last(env, A).startswith("Your consent is withdrawn")
    handle_payload(wa(A, media="INVOICE_A"), env)
    assert "Reply YES to agree" in last(env, A)
    assert env.queue.jobs == [] and not (tmp_path / "files").exists()
    consent(env, A)
    assert last(env, A).startswith("Thank you")


def test_file_queued_before_stop_is_never_read(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    handle_payload(wa(A, "text", text="STOP"), env)
    rec, = run(env)
    assert rec["outcome"] == "skipped_no_consent"
    assert env.records.documents("TS09XY4521") == []
    assert last(env, A).startswith("Your consent is withdrawn")


def test_bill_is_stored_encrypted_path_read_checked_and_answered(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    job = env.queue.jobs[0]
    assert job["key"] == "fleet/TS09XY4521/2026-10/%s.jpg" % H["INVOICE_A"] and "phone" not in job
    assert last(env, A) == "Received. Checking it now."
    rec, = run(env)
    assert rec["outcome"] == "accepted" and "billed_to" not in rec["doc"]
    assert last(env, A).startswith("Received the service bill for TS-09-XY-4521. Thank you.")
    assert env.records.profile("TS09XY4521")["last_odometer"] == 59985


def test_same_bill_sent_for_another_cab_is_caught_and_answered_in_telugu(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    run(env)
    consent(env, B, "అవును")
    handle_payload(wa(B, media="INVOICE_A"), env)
    rec, = run(env)
    codes = {f["code"] for f in rec["flags"]}
    assert rec["outcome"] == "rejected" and {"DUPLICATE_FILE", "VEHICLE_MISMATCH"} <= codes
    assert "TS-09-XY-4521" in last(env, B) and "అందింది" in last(env, B)
    assert env.records.profile("TS09XY7730")["last_odometer"] is None     # a rejected bill moves nothing


def test_safety_advisory_stays_open_until_a_bill_proves_the_fix(env):
    consent(env, A)
    handle_payload(wa(A, media="ADVISORY_A"), env)
    run(env)
    assert list(env.records.profile("TS09XY4521")["open_actions"]) == ["tyres"]
    assert "tyres" in last(env, A)
    handle_payload(wa(A, media="FIX_A"), env)
    rec, = run(env)
    assert rec["closed"] == ["tyres"] and env.records.profile("TS09XY4521")["open_actions"] == {}


def test_medical_certificate_goes_to_the_restricted_prefix_and_never_to_the_model(env):
    consent(env, A)
    handle_payload(wa(A, media="MEDICAL_A", caption="Medical certificate"), env)
    assert env.queue.jobs[0]["key"].startswith("restricted/medical/TS09XY4521/")
    rec, = run(env)                     # the stand-in has no reading for this file, so a model call would fail
    assert rec["outcome"] == "pending_review"
    assert "medical certificate" in last(env, A)


def test_resent_file_is_acknowledged_not_reprocessed(env):
    consent(env, A)
    handle_payload(wa(A, media="INVOICE_A"), env)
    run(env)
    handle_payload(wa(A, media="INVOICE_A"), env)
    out, = run(env)
    assert out["outcome"] == "already_received" and "already received" in last(env, A)


def test_real_document_never_reaches_a_model_outside_india(env):
    class OffshoreModel:
        in_india = False
        calls = 0

        def extract(self, pages, file_hash):
            OffshoreModel.calls += 1
            raise AssertionError("must not be called")

    env.model = OffshoreModel()
    consent(env, C, "हाँ")
    handle_payload(wa(C, media="DOC_C"), env)
    with pytest.raises(ResidencyError):
        run(env)
    assert OffshoreModel.calls == 0
