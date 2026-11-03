"""Webhook security and parsing: Meta's signature, the verify-token handshake, and one parser for both the Cloud API
shape and the AWS End User Messaging envelope."""
import hashlib
import hmac
import json

import pytest

from pipeline.errors import WebhookAuthError
from pipeline.inbound import parse, verify_challenge, verify_signature

SECRET = "test-app-secret"


def sign(raw: bytes) -> str:
    return "sha256=" + hmac.new(SECRET.encode(), raw, hashlib.sha256).hexdigest()


def entry(messages=None, statuses=None):
    value = {"messaging_product": "whatsapp", "metadata": {"phone_number_id": "PNID"}}
    if messages is not None:
        value["messages"] = messages
    if statuses is not None:
        value["statuses"] = statuses
    return {"id": "WABA", "changes": [{"field": "messages", "value": value}]}


IMAGE = {"from": "919000000001", "id": "wamid.A1", "timestamp": "1761120000", "type": "image",
         "image": {"id": "MEDIA1", "mime_type": "image/jpeg", "caption": "Cab 4521 service bill"}}
TEXT = {"from": "919000000001", "id": "wamid.A2", "timestamp": "1761120001", "type": "text", "text": {"body": " YES "}}


def test_good_signature_passes_and_tampering_fails():
    raw = json.dumps({"entry": []}).encode()
    verify_signature(raw, sign(raw), SECRET)
    with pytest.raises(WebhookAuthError):
        verify_signature(raw + b" ", sign(raw), SECRET)
    with pytest.raises(WebhookAuthError):
        verify_signature(raw, "", SECRET)
    with pytest.raises(WebhookAuthError):
        verify_signature(raw, sign(raw), "")          # no secret configured: refuse, never allow


def test_handshake_returns_challenge_only_for_the_right_token():
    ok = {"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "12345"}
    assert verify_challenge(ok, "tok") == "12345"
    with pytest.raises(WebhookAuthError):
        verify_challenge(dict(ok, **{"hub.verify_token": "wrong"}), "tok")


def test_cloud_api_payload_is_parsed_and_statuses_skipped():
    payload = {"object": "whatsapp_business_account",
               "entry": [entry([IMAGE, TEXT]), entry(statuses=[{"id": "wamid.X", "status": "delivered"}])]}
    msgs = parse(payload)
    assert [m.kind for m in msgs] == ["image", "text"]
    img, txt = msgs
    assert img.sender == "+919000000001" and img.media_id == "MEDIA1" and img.mime == "image/jpeg"
    assert img.caption == "Cab 4521 service bill" and txt.text == "YES"


def test_aws_end_user_messaging_envelope_uses_the_same_parser():
    event = {"context": {"MetaPhoneNumberIds": ["PNID"]}, "whatsAppWebhookEntry": json.dumps(entry([IMAGE]))}
    msgs = parse(event)
    assert len(msgs) == 1 and msgs[0].media_id == "MEDIA1" and msgs[0].sender == "+919000000001"
