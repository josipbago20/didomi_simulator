"""Generic (non-consent) routes: metadata, organizations, properties.
Rate limited (100 requests / 15 s per organisation), `$limit`/`$skip` paging."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from .. import catalogue as cat
from ..auth import Principal, check_org, rate_limited
from ..errors import DidomiError
from ..models import Page

router = APIRouter()
MAX_LIMIT = 100
UPDATED_AT = "2026-06-18T14:45:10.207Z"

# Partner category -> purposes it processes.
CATEGORY_PURPOSES = {
    "advertising": ["cookies", "select_basic_ads", "create_ads_profile", "select_personalized_ads",
                    "measure_ad_performance"],
    "social": ["cookies", "create_ads_profile", "select_personalized_ads"],
    "analytics": ["cookies", "measure_content_performance", "market_research"],
    "personalization": ["cookies", "create_content_profile", "select_personalized_content"],
    "marketing": ["cookies", "personalized_offers"],
    "support": ["cookies", "improve_products"],
}


def _page(items: list[dict], limit: int | None, skip: int) -> dict:
    if skip < 0 or (limit is not None and limit < 0):
        raise DidomiError(400, "$limit and $skip must be positive numbers")
    limit = MAX_LIMIT if limit is None else min(limit, MAX_LIMIT)
    return {"total": len(items), "limit": limit, "skip": skip, "data": items[skip:skip + limit]}


def _text(value: str, translations: bool):
    return {"en": value} if translations else value


def _purposes(org: str, translations: bool) -> list[dict]:
    out = []
    for p in cat.TCF_PURPOSES:
        out.append({"id": p["id"], "type": "purpose", "description": _text(p["name"], translations),
                    "details": _text(f"IAB TCF v2.2 purpose {p['iab']}: {p['name']}.", translations),
                    "reference": None, "organization_id": None, "namespaces": {"iab2": p["iab"]},
                    "regulations_id": ["gdpr"], "metadata": {}, "created_at": cat.CATALOGUE_CREATED_AT,
                    "updated_at": UPDATED_AT})
    for p in cat.CUSTOM_PURPOSES:
        out.append({"id": p["id"], "type": "purpose", "description": _text(p["name"], translations),
                    "details": _text(p["name"] + ".", translations), "reference": None, "organization_id": org,
                    "namespaces": {"custom": p["id"]}, "regulations_id": ["gdpr"],
                    "metadata": {"preferences": {pid: {"name": pref["name"], "values": list(pref["values"])}
                                                 for pid, pref in p["preferences"].items()}},
                    "created_at": cat.CATALOGUE_CREATED_AT, "updated_at": UPDATED_AT})
    return out


def _partners(org: str) -> list[dict]:
    out = []
    for v in cat.VENDORS:
        purposes = CATEGORY_PURPOSES[v["category_id"]]
        li = [p for p in purposes if v["li"] and p in cat.LI_PURPOSES]
        out.append({
            "id": v["id"], "name": v["name"], "category_id": v["category_id"], "country": v["country"],
            "organization_id": org if v["id"].startswith("c:") else None, "taxonomy_id": None, "tags": [],
            "website": None, "website_optout": None, "contact": None, "hosts": [], "url_patterns": [],
            "namespaces": {"iab2": v["iab_id"]} if v["iab_id"] else {},
            "default_purposes_id": [p for p in purposes if p not in li],
            "legitimate_interest_purposes_id": li, "spi_purposes_id": [], "essential_purposes_id": [],
            "flexible_purposes_id": [], "cookie_max_duration": 13, "cookie_max_duration_unit": "months",
            "uses_non_cookie_access": False, "deprecated": False, "notes": None, "version": 1,
            "created_at": cat.CATALOGUE_CREATED_AT, "updated_at": UPDATED_AT,
        })
    return out


@router.get("/metadata/purposes", response_model=Page, tags=["metadata"], summary="Retrieve a list of purposes")
def list_purposes(
    organization_id: str = Query(...),
    limit: int | None = Query(None, alias="$limit"),
    skip: int = Query(0, alias="$skip"),
    translations: bool = Query(False, alias="$translations"),
    who: Principal = Depends(rate_limited),
):
    check_org(who, organization_id)
    return _page(_purposes(organization_id, translations), limit, skip)


@router.get("/metadata/partners", response_model=Page, tags=["metadata"], summary="Retrieve a list of partners")
def list_partners(
    organization_id: str | None = Query(None),
    limit: int | None = Query(None, alias="$limit"),
    skip: int = Query(0, alias="$skip"),
    who: Principal = Depends(rate_limited),
):
    if organization_id:
        check_org(who, organization_id)
    return _page(_partners(who.organization_id), limit, skip)


@router.get("/organizations/{id}", tags=["organizations"], summary="Retrieve an organization")
def get_organization(id: str, who: Principal = Depends(rate_limited)):
    check_org(who, id)
    return {"id": id, "name": id.replace("-", " ").title(), "website": "https://www.demo-retail.com",
            "industry_id": "retail", "public_api_key": "4f0c2b9e-7a1d-4c3e-9b8a-2d6e5f1a0c37", "version": 3,
            "validate_purpose_id": True, "disable_preferences_in_consents": False, "auth_enabled": False,
            "auth_allow_user_creation": False, "auth_message_priority": ["email"],
            "allow_tcf_with_custom_text": False, "self_register": False, "organization_group_id": None,
            "organization_group_name": None, "iab_tcf_cmp_id": cat.DIDOMI_CMP_ID, "allow_chat_support": True,
            "created_at": "2024-11-05T08:30:00.000Z", "updated_at": UPDATED_AT}


@router.get("/properties", response_model=Page, tags=["properties"], summary="Retrieve a list of properties")
@router.get("/reports/compliances/properties", response_model=Page, tags=["properties"], include_in_schema=False)
def list_properties(
    organization_id: str = Query(...),
    limit: int | None = Query(None, alias="$limit"),
    skip: int = Query(0, alias="$skip"),
    who: Principal = Depends(rate_limited),
):
    check_org(who, organization_id)
    items = [{**p, "organization_id": organization_id, "pages_count": 10, "schedule": "0 3 * * 1", "enabled": True,
              "filters": [], "created_at": cat.CATALOGUE_CREATED_AT, "updated_at": UPDATED_AT}
             for p in cat.PROPERTIES]
    return _page(items, limit, skip)
