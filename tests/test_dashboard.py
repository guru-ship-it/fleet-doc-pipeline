"""The dashboard function: the page and assets are served with hardening headers from one flat folder, the state
needs the access code and fails closed without one, and an unchanged state costs a 304."""
import json
import pathlib

import pytest

from pipeline import dashboard

ROOT = pathlib.Path(__file__).resolve().parents[1]
CODE = "fleet-test-code"


@pytest.fixture
def site(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCAL_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("REGISTRY_FILE", str(ROOT / "demo" / "registry.example.json"))
    monkeypatch.setenv("DASHBOARD_KEY", CODE)
    monkeypatch.delenv("SECRET_ID", raising=False)
    dashboard._ctx.cache_clear()
    yield
    dashboard._ctx.cache_clear()


def get(path, **headers):
    return dashboard.handle("GET", path, headers)


def test_page_and_assets_come_from_one_flat_folder_with_hardening_headers(site):
    r = get("/")
    assert r["statusCode"] == 200 and r["headers"]["Content-Type"].startswith("text/html")
    assert "Fleet Compliance Dashboard" in r["body"] and r["headers"]["Cache-Control"] == "no-cache"
    assert r["headers"]["Content-Security-Policy"].startswith("default-src 'self'")
    assert r["headers"]["X-Robots-Tag"] == "noindex, nofollow" and r["headers"]["X-Frame-Options"] == "DENY"
    assert get("/app.js")["headers"]["Content-Type"].startswith("text/javascript")
    logo = get("/cdai-logo.png")
    assert logo["statusCode"] == 200 and logo["isBase64Encoded"] is True
    for path in ("/nope.html", "/../pipeline/app.py", "/.env", "/site/index.html", "/serve_local.py"):
        assert get(path)["statusCode"] == 404, path
    assert dashboard.handle("POST", "/", {})["statusCode"] == 405


def test_state_needs_the_access_code(site):
    assert get("/api/state")["statusCode"] == 401
    assert get("/api/state", Authorization="Bearer wrong-code")["statusCode"] == 401
    r = get("/api/state", authorization="Bearer " + CODE)
    assert r["statusCode"] == 200 and r["headers"]["Cache-Control"] == "no-store"
    body = json.loads(r["body"])
    assert body["client"] == "Example Tech Park, Hyderabad" and [c["cab_id"] for c in body["cabs"]] == ["CAB-01", "CAB-02", "CAB-03"]
    assert "9000000001" not in r["body"]


def test_unchanged_state_answers_304_without_a_body(site):
    r = get("/api/state", Authorization="Bearer " + CODE)
    again = get("/api/state", **{"Authorization": "Bearer " + CODE, "If-None-Match": r["headers"]["ETag"]})
    assert again["statusCode"] == 304 and again["body"] == "" and again["headers"]["ETag"] == r["headers"]["ETag"]


def test_no_configured_code_fails_closed(site, monkeypatch):
    monkeypatch.setenv("DASHBOARD_KEY", "")
    dashboard._ctx.cache_clear()
    assert get("/api/state", Authorization="Bearer anything")["statusCode"] == 503
    assert get("/")["statusCode"] == 200                      # the page itself still loads


def test_lambda_event_shape_is_routed(site):
    event = {"rawPath": "/api/state", "requestContext": {"http": {"method": "GET"}},
             "headers": {"authorization": "Bearer " + CODE}}
    assert dashboard.lambda_dashboard(event, None)["statusCode"] == 200
    assert dashboard.lambda_dashboard({"rawPath": "/styles.css", "requestContext": {"http": {"method": "GET"}}}, None)["statusCode"] == 200
