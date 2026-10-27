from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from app.main import create_app
from tests.conftest import NOW, ORG, SETTINGS, crawl, login


def test_cursor_paging_covers_population_exactly_once(client, auth):
    users, pages = crawl(client, auth)
    ids = [u["id"] for u in users]
    assert len(ids) == len(set(ids)) and ids == sorted(ids)
    assert 0 < len(ids) < SETTINGS.users
    assert pages == -(-len(ids) // 100)
    assert all(u["created_at"] <= "2026-10-27T12:00:00.000Z" for u in users)

    # Once the whole timeline has passed, the crawl returns every generated user.
    client.app.state.clock = lambda: SETTINGS.anchor + timedelta(days=SETTINGS.future_days + 1)
    all_users, _ = crawl(client, auth)
    assert len({u["id"] for u in all_users}) == SETTINGS.users


def test_invalid_cursor_400(client, auth):
    r = client.get("/v1/consents/users", params={"organization_id": ORG, "$cursor": "%%%"}, headers=auth)
    assert r.status_code == 400 and r.json()["name"] == "BadRequest"


def test_determinism_across_requests_and_restarts(client, auth):
    params = {"organization_id": ORG}
    first = client.get("/v1/consents/users", params=params, headers=auth).json()
    assert client.get("/v1/consents/users", params=params, headers=auth).json() == first
    other = TestClient(create_app(SETTINGS))
    assert other.get("/v1/consents/users", params=params, headers=login(other)).json() == first
    user_id = first["data"][0]["id"]
    q = {"organization_id": ORG, "user_id": user_id}
    assert (client.get("/v1/consents/events", params=q, headers=auth).json()
            == other.get("/v1/consents/events", params=q, headers=login(other)).json())


def test_daily_delta(client, auth):
    day1, day2 = NOW, NOW + timedelta(days=1)
    client.app.state.clock = lambda: day1
    before = {u["id"]: u for u in crawl(client, auth)[0]}
    client.app.state.clock = lambda: day2
    after = {u["id"]: u for u in crawl(client, auth)[0]}
    assert set(before) < set(after), "new users appear the next day, none disappear"
    changed = [i for i in before if after[i]["updated_at"] != before[i]["updated_at"]]
    assert changed, "some existing users changed consent"
    assert all(after[i]["updated_at"] > before[i]["updated_at"] for i in changed)
    unchanged = [i for i in before if i not in changed]
    assert all(after[i] == before[i] for i in unchanged), "history is stable"
    q = {"organization_id": ORG, "user_id": changed[0], "status[$in]": ["confirmed", "pending_approval"]}
    client.app.state.clock = lambda: day1
    n1 = len(client.get("/v1/consents/events", params=q, headers=auth).json()["data"])
    client.app.state.clock = lambda: day2
    n2 = len(client.get("/v1/consents/events", params=q, headers=auth).json()["data"])
    assert n2 > n1


def test_user_is_fold_of_its_events(client, auth):
    users, _ = crawl(client, auth)
    user = next(u for u in users if u["version"] >= 3)
    events = client.get("/v1/consents/events", params={"organization_id": ORG, "user_id": user["id"]},
                        headers=auth).json()["data"]
    assert events and user["updated_at"] == events[-1]["created_at"]
    for p in user["consents"]["purposes"]:
        last = [ep for e in events for ep in e["consents"]["purposes"] if ep["id"] == p["id"] and ep["enabled"] is not None]
        assert p["enabled"] == last[-1]["enabled"]
    one = client.get(f"/v1/consents/events/{events[0]['id']}", params={"organization_id": ORG}, headers=auth)
    assert one.status_code == 200 and one.json() == events[0]
    by_id = client.get(f"/v1/consents/users/{user['id']}", params={"organization_id": ORG}, headers=auth).json()
    assert by_id == user


def test_lookup_by_organization_user_id(client, auth):
    users, _ = crawl(client, auth)
    user = next(u for u in users if u["organization_user_id"])
    r = client.get(f"/v1/consents/users/{user['organization_user_id']}",
                   params={"organization_id": ORG, "$by_organization_user_id": "true", "$merge_users": "true"},
                   headers=auth)
    assert r.json()["id"] == user["id"]
    r = client.get("/v1/consents/users", params={"organization_id": ORG,
                                                  "organization_user_id": user["organization_user_id"]}, headers=auth)
    assert [u["id"] for u in r.json()["data"]] == [user["id"]]
    r = client.get("/v1/consents/events", params={"organization_id": ORG,
                                                   "organization_user_id": user["organization_user_id"]}, headers=auth)
    assert r.status_code == 200 and r.json()["data"]
    assert client.get("/v1/consents/users/nope", params={"organization_id": ORG}, headers=auth).status_code == 404
    assert client.get("/v1/consents/events", params={"organization_id": ORG}, headers=auth).status_code == 400


def test_full_tree(client, auth):
    r = client.get("/v1/consents/users", params={"organization_id": ORG, "$include_full_tree": "true"}, headers=auth)
    user = r.json()["data"][0]
    assert "RateLimit" in r.headers
    assert user["consents"]["config_tree"]["id"]
    assert all(p["from_tree"] and p["name"]["en"] for p in user["consents"]["purposes"])
    plain = client.get("/v1/consents/users", params={"organization_id": ORG}, headers=auth)
    assert "RateLimit" not in plain.headers and "config_tree" not in plain.json()["data"][0]["consents"]


def test_post_event_overlay(client, auth):
    users, _ = crawl(client, auth)
    user = users[0]
    body = {"user": {"id": user["id"], "metadata": {"source_campaign": "demo"}},
            "consents": {"purposes": [{"id": "newsletter", "enabled": True,
                                       "values": {"topics": {"value": "tech,sports"}}}],
                         "channels": [{"id": "email", "enabled": True}],
                         "vendors": {"enabled": ["criteo"]}}}
    r = client.post("/v1/consents/events", params={"organization_id": ORG}, json=body, headers=auth)
    assert r.status_code == 200, r.text
    event = r.json()
    assert event["status"] == "confirmed" and event["source"]["type"] == "api"
    after = client.get(f"/v1/consents/users/{user['id']}", params={"organization_id": ORG}, headers=auth).json()
    newsletter = next(p for p in after["consents"]["purposes"] if p["id"] == "newsletter")
    assert newsletter["enabled"] is True and newsletter["values"]["topics"] == {"value": "tech,sports"}
    assert "criteo" in after["consents"]["vendors"]["enabled"]
    assert after["updated_at"] == event["created_at"] and after["metadata"]["source_campaign"] == "demo"
    events = client.get("/v1/consents/events", params={"organization_id": ORG, "user_id": user["id"]},
                        headers=auth).json()["data"]
    assert events[-1]["id"] == event["id"]

    # Unknown user: created on the fly, findable by organization user id.
    body = {"user": {"organization_user_id": "new.customer@example.com", "country": "DE"},
            "consents": {"purposes": [{"id": "cookies", "enabled": True}]}}
    created = client.post("/v1/consents/events", params={"organization_id": ORG}, json=body, headers=auth).json()
    found = client.get("/v1/consents/users", params={"organization_id": ORG,
                                                      "organization_user_id": "new.customer@example.com"},
                       headers=auth).json()["data"]
    assert [u["id"] for u in found] == [created["user"]["id"]]
    assert len(crawl(client, auth)[0]) == len(users) + 1


def test_post_event_validation(client, auth):
    bad = {"consents": {"purposes": [{"id": "not_a_purpose", "enabled": True},
                                     {"id": "newsletter", "values": {"topics": {"value": "tech,cars"}}},
                                     {"id": "cookies", "enabled_li": True}],
                        "vendors": {"enabled": ["nobody"]}}}
    r = client.post("/v1/consents/events", params={"organization_id": ORG}, json=bad, headers=auth)
    assert r.status_code == 400
    assert len(r.json()["errors"]) == 4
    r = client.post("/v1/consents/events", params={"organization_id": "other-org"},
                    json={"consents": {}}, headers=auth)
    assert r.status_code == 403
    assert client.post("/v1/consents/events", params={"organization_id": ORG}, json={}, headers=auth).status_code == 400


def test_pending_events_hidden_by_default(client, auth):
    client.app.state.clock = lambda: datetime(2027, 1, 1, tzinfo=timezone.utc)
    users, _ = crawl(client, auth)
    for u in users:
        q = {"organization_id": ORG, "user_id": u["id"]}
        both = client.get("/v1/consents/events", params={**q, "status[$in]": ["confirmed", "pending_approval"]},
                          headers=auth).json()["data"]
        if any(e["status"] == "pending_approval" for e in both):
            default = client.get("/v1/consents/events", params=q, headers=auth).json()["data"]
            assert all(e["status"] == "confirmed" for e in default) and len(default) < len(both)
            return
    raise AssertionError("no pending_approval event generated")
