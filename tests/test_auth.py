import time

import jwt

from tests.conftest import ORG, SETTINGS, login

ERROR_KEYS = {"name", "message", "code", "className", "errors"}


def test_session_returns_jwt_bound_to_org(client):
    r = client.post("/v1/sessions", json={"type": "api-key", "key": "demo-key", "secret": "demo-secret"})
    body = r.json()
    assert r.status_code == 200 and body["type"] == "api-key" and body["key"] == "demo-key"
    claims = jwt.decode(body["access_token"], SETTINGS.jwt_secret, algorithms=["HS256"])
    assert claims["organization_id"] == ORG
    assert 3590 <= claims["exp"] - int(time.time()) <= 3600


def test_bad_credentials_400(client):
    for payload in ({"type": "api-key", "key": "demo-key", "secret": "nope"},
                    {"type": "email", "key": "demo-key", "secret": "demo-secret"}):
        r = client.post("/v1/sessions", json=payload)
        assert r.status_code == 400
        assert set(r.json()) == ERROR_KEYS and r.json()["name"] == "BadRequest"
    r = client.post("/v1/sessions", json={"type": "api-key"})
    assert r.status_code == 400 and set(r.json()) == ERROR_KEYS


def test_missing_invalid_or_expired_token_401(client):
    expired = jwt.encode({"sub": "demo-key", "organization_id": ORG, "exp": int(time.time()) - 5},
                         SETTINGS.jwt_secret, algorithm="HS256")
    for headers in ({}, {"Authorization": "Bearer garbage"}, {"Authorization": f"Bearer {expired}"},
                    {"Authorization": "Basic abc"}):
        for path in ("/v1/consents/users", "/v1/metadata/purposes", "/v1/properties"):
            r = client.get(path, params={"organization_id": ORG}, headers=headers)
            assert r.status_code == 401, (path, headers)
            assert r.json()["name"] == "NotAuthenticated" and set(r.json()) == ERROR_KEYS


def test_other_org_403(client, auth):
    for path in ("/v1/consents/users", "/v1/consents/users/x", "/v1/metadata/purposes", "/v1/properties"):
        r = client.get(path, params={"organization_id": "other-org"}, headers=auth)
        assert r.status_code == 403 and r.json()["name"] == "Forbidden"
    assert client.get("/v1/organizations/other-org", headers=auth).status_code == 403
    other = login(client, "other-key", "other-secret")
    assert client.get("/v1/consents/users", params={"organization_id": ORG}, headers=other).status_code == 403
    assert client.get("/v1/consents/users", params={"organization_id": "other-org"}, headers=other).status_code == 200


def test_missing_organization_id_400(client, auth):
    r = client.get("/v1/consents/users", headers=auth)
    assert r.status_code == 400 and "organization_id" in r.json()["errors"]


def test_keys_env_formats():
    from app.config import ApiKey, parse_keys
    expected = (ApiKey("k1", "s1", "org-a"), ApiKey("k2", "s2", "org-b"))
    assert parse_keys("k1:s1:org-a, k2:s2:org-b") == expected
    assert parse_keys('[{"key":"k1","secret":"s1","organization_id":"org-a"},'
                      '{"key":"k2","secret":"s2","organization_id":"org-b"}]') == expected
