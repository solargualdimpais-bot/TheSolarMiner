import os
import secrets

os.environ.setdefault("SOLARMINER_RELAY_API_KEY", "test-relay-api-key-value-32-characters-min")

from fastapi.testclient import TestClient

from tools.tesla_oauth_relay.relay import SESSION_TTL_SECONDS, create_app


API_KEY = "test-relay-api-key-value-32-characters-min"
ORIGIN = "https://solarminer.example"


def new_session(client: TestClient, *, state: str | None = None, poll_token: str | None = None):
    state = state or secrets.token_urlsafe(32)
    poll_token = poll_token or secrets.token_urlsafe(32)
    response = client.post(
        "/v1/sessions",
        headers={"Authorization": f"Bearer {API_KEY}"},
        json={"state": state, "poll_token": poll_token, "origin": ORIGIN},
    )
    assert response.status_code == 201, response.text
    return state, poll_token


def test_gateway_can_register_and_retrieve_short_lived_code_without_returning_it_to_browser():
    client = TestClient(create_app(api_key=API_KEY))
    state, poll_token = new_session(client)

    pending = client.get(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"})
    assert pending.status_code == 200
    assert pending.json() == {"ready": False, "code": None, "error": None}

    callback = client.get("/oauth/callback", params={"state": state, "code": "one-time-code"})
    assert callback.status_code == 200
    assert "one-time-code" not in callback.text
    assert f'state:"{state}"' in callback.text
    assert callback.headers["cache-control"].startswith("no-store")
    assert callback.headers["referrer-policy"] == "no-referrer"

    result = client.get(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"})
    assert result.json() == {"ready": True, "code": "one-time-code", "error": None}
    assert client.delete(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"}).status_code == 204
    assert client.get(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"}).status_code == 404


def test_relay_rejects_unauthorized_registration_and_result_reads():
    client = TestClient(create_app(api_key=API_KEY))
    state = secrets.token_urlsafe(32)
    poll_token = secrets.token_urlsafe(32)
    payload = {"state": state, "poll_token": poll_token, "origin": ORIGIN}

    assert client.post("/v1/sessions", json=payload).status_code == 401
    assert client.post("/v1/sessions", headers={"Authorization": "Bearer wrong"}, json=payload).status_code == 401
    assert client.get(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"}).status_code == 404


def test_authenticated_health_endpoint_verifies_relay_key_for_owner_setup():
    client = TestClient(create_app(api_key=API_KEY))
    assert client.get("/v1/health").status_code == 401
    assert client.get("/v1/health", headers={"Authorization": "Bearer wrong"}).status_code == 401
    assert client.get("/v1/health", headers={"Authorization": f"Bearer {API_KEY}"}).json() == {"status": "ok"}


def test_callback_requires_registered_state_and_cannot_be_replayed():
    client = TestClient(create_app(api_key=API_KEY))
    assert client.get("/oauth/callback", params={"state": secrets.token_urlsafe(32), "code": "x"}).status_code == 400

    state, _ = new_session(client)
    assert client.get("/oauth/callback", params={"state": state, "code": "first"}).status_code == 200
    assert client.get("/oauth/callback", params={"state": state, "code": "replay"}).status_code == 400


def test_origin_must_be_exact_https_origin():
    client = TestClient(create_app(api_key=API_KEY))
    for origin in (
        "http://solarminer.example",
        "https://solarminer.example/path",
        "https://user@solarminer.example",
        "https://solarminer.example?next=bad",
        "https://solarminer.example/\n",
    ):
        response = client.post(
            "/v1/sessions",
            headers={"Authorization": f"Bearer {API_KEY}"},
            json={"state": secrets.token_urlsafe(32), "poll_token": secrets.token_urlsafe(32), "origin": origin},
        )
        assert response.status_code == 422, (origin, response.text)


def test_expired_session_is_not_available_to_callback_or_gateway(monkeypatch):
    import tools.tesla_oauth_relay.relay as relay_module

    now = [1000.0]
    monkeypatch.setattr(relay_module.time, "time", lambda: now[0])
    client = TestClient(create_app(api_key=API_KEY))
    state, poll_token = new_session(client)

    now[0] += SESSION_TTL_SECONDS + 1
    assert client.get("/oauth/callback", params={"state": state, "code": "expired"}).status_code == 400
    assert client.get(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"}).status_code == 404


def test_oauth_error_is_normalized_and_not_reflected_to_browser():
    client = TestClient(create_app(api_key=API_KEY))
    state, poll_token = new_session(client)

    callback = client.get("/oauth/callback", params={"state": state, "error": "unexpected-sensitive-provider-text"})
    assert callback.status_code == 200
    assert "unexpected-sensitive-provider-text" not in callback.text
    result = client.get(f"/v1/sessions/{state}", headers={"Authorization": f"Bearer {poll_token}"})
    assert result.json() == {"ready": True, "code": None, "error": "authorization_failed"}
