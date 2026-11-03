"""Smoke test of the web entry point: the handshake and the signature gate, through FastAPI's test client."""
from fastapi.testclient import TestClient

from pipeline import app as app_module
from pipeline.config import Settings
from pipeline.intake import Deps
from pipeline.registry import Registry


def fake_deps():
    return Deps(settings=Settings(wa_app_secret="secret", wa_verify_token="tok"), registry=Registry([]),
                records=None, store=None, queue=None)


def test_handshake_and_signature_gate(monkeypatch):
    monkeypatch.setattr(app_module, "deps", fake_deps)
    client = TestClient(app_module.app)
    r = client.get("/wa/inbound", params={"hub.mode": "subscribe", "hub.verify_token": "tok", "hub.challenge": "42"})
    assert r.status_code == 200 and r.text == "42"
    assert client.get("/wa/inbound", params={"hub.mode": "subscribe", "hub.verify_token": "x"}).status_code == 403
    r = client.post("/wa/inbound", content=b'{"entry": []}', headers={"x-hub-signature-256": "sha256=bad"})
    assert r.status_code == 403
