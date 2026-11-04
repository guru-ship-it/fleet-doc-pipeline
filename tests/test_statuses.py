"""Delivery receipts: Meta's statuses payloads are parsed into Status records, and never mistaken for messages."""
from pipeline.inbound import parse, statuses


def receipt(status, errors=None):
    s = {"id": "wamid.ABC123", "status": status, "timestamp": "1761120000", "recipient_id": "919999000001"}
    if errors:
        s["errors"] = errors
    return {"object": "whatsapp_business_account",
            "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {"statuses": [s]}}]}]}


def test_delivered_receipt_is_parsed_and_is_not_a_message():
    payload = receipt("delivered")
    st, = statuses(payload)
    assert (st.status, st.recipient, st.message_id, st.error_code) == ("delivered", "+919999000001", "wamid.ABC123", None)
    assert parse(payload) == []


def test_failed_receipt_carries_metas_error():
    payload = receipt("failed", [{"code": 131047, "title": "Re-engagement message",
                                  "error_data": {"details": "Message failed to send because more than 24 hours have passed"}}])
    st, = statuses(payload)
    assert st.status == "failed" and st.error_code == 131047
    assert "Re-engagement message" in st.error_title and "24 hours" in st.error_title


def test_message_payload_has_no_statuses():
    payload = {"object": "whatsapp_business_account", "entry": [{"id": "WABA", "changes": [{"field": "messages", "value": {
        "messages": [{"from": "919999000001", "id": "wamid.1", "timestamp": "1761120000", "type": "text", "text": {"body": "hi"}}]}}]}]}
    assert statuses(payload) == [] and len(parse(payload)) == 1
