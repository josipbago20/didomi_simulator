from tests.conftest import ORG


def test_purposes_paging(client, auth):
    seen, skip = [], 0
    while True:
        r = client.get("/v1/metadata/purposes", params={"organization_id": ORG, "$limit": 5, "$skip": skip},
                       headers=auth)
        body = r.json()
        assert set(body) == {"total", "limit", "skip", "data"} and body["limit"] == 5 and body["skip"] == skip
        seen += [p["id"] for p in body["data"]]
        skip += 5
        if skip >= body["total"]:
            break
    assert len(seen) == len(set(seen)) == body["total"] == 13
    assert {"cookies", "newsletter"} <= set(seen)
    r = client.get("/v1/metadata/purposes", params={"organization_id": ORG, "$translations": "true"}, headers=auth)
    assert r.json()["data"][0]["description"] == {"en": "Store and/or access information on a device"}


def test_partners_and_properties(client, auth):
    partners = client.get("/v1/metadata/partners", params={"$limit": 1000}, headers=auth).json()
    assert partners["limit"] == 100 and partners["total"] == len(partners["data"])
    assert {"google", "criteo", "c:loyalty-crm"} <= {p["id"] for p in partners["data"]}
    props = client.get("/v1/properties", params={"organization_id": ORG}, headers=auth).json()
    assert props["total"] == 5 and props["data"][0]["website"].startswith("https://")
    alias = client.get("/v1/reports/compliances/properties", params={"organization_id": ORG}, headers=auth).json()
    assert alias == props
    org = client.get(f"/v1/organizations/{ORG}", headers=auth).json()
    assert org["id"] == ORG


def test_rate_limit_on_non_consent_routes(client, auth):
    for i in range(100):
        r = client.get("/v1/properties", params={"organization_id": ORG}, headers=auth)
        assert r.status_code == 200
    assert r.headers["RateLimit"].startswith("limit=100, remaining=0")
    assert r.headers["RateLimit-Policy"] == "100;w=15"
    r = client.get("/v1/metadata/purposes", params={"organization_id": ORG}, headers=auth)
    assert r.status_code == 429 and r.json()["name"] == "TooManyRequests" and int(r.headers["Retry-After"]) > 0
    # Consent routes are not throttled.
    assert client.get("/v1/consents/users", params={"organization_id": ORG}, headers=auth).status_code == 200


def test_reference_doc_served(client):
    r = client.get("/docs/didomi-api.md")
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/markdown")
    assert "/consents/users" in r.text
    assert "http://testserver/v1/sessions" in r.text and "{{BASE_URL}}" not in r.text
