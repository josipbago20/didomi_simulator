from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from app.config import ApiKey, Settings
from app.main import create_app

NOW = datetime(2026, 10, 27, 12, tzinfo=timezone.utc)
ORG = "demo-org"
SETTINGS = Settings(
    keys=(ApiKey("demo-key", "demo-secret", ORG), ApiKey("other-key", "other-secret", "other-org")),
    jwt_secret="test-secret-that-is-at-least-32-bytes-long",
    users=800,
    now=NOW,
)


@pytest.fixture
def app():
    return create_app(SETTINGS)


@pytest.fixture
def client(app):
    return TestClient(app)


def login(client, key="demo-key", secret="demo-secret"):
    r = client.post("/v1/sessions", json={"type": "api-key", "key": key, "secret": secret})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


@pytest.fixture
def auth(client):
    return login(client)


def crawl(client, auth, **params):
    users, cursor, pages = [], None, 0
    while True:
        query = {"organization_id": ORG, **params, **({"$cursor": cursor} if cursor else {})}
        r = client.get("/v1/consents/users", params=query, headers=auth)
        assert r.status_code == 200, r.text
        body = r.json()
        assert set(body) == {"data", "limit", "cursor"} and body["limit"] == 100
        users += body["data"]
        pages += 1
        cursor = body["cursor"]
        if cursor is None:
            return users, pages
