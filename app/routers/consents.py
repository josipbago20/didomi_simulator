"""/consents/users and /consents/events. No rate limit, except `$include_full_tree=true` reads."""
from __future__ import annotations

import base64
import binascii

from fastapi import APIRouter, Depends, Query, Request, Response

from .. import catalogue as cat
from ..auth import Principal, check_org, principal
from ..errors import DidomiError
from ..models import ConsentEvent, ConsentEventIn, ConsentUser, EventList, UserPage
from ..population import ConsentRepository, parse_iso

router = APIRouter(prefix="/consents", tags=["consents"])
EXCLUDE = {"response_model_exclude_unset": True}


def repo_of(request: Request) -> ConsentRepository:
    return request.app.state.repository


def _cursor_encode(user_id: str | None) -> str | None:
    return base64.urlsafe_b64encode(user_id.encode()).decode() if user_id else None


def _cursor_decode(cursor: str | None) -> str | None:
    if not cursor:
        return None
    try:
        return base64.b64decode(cursor.encode(), altchars=b"-_", validate=True).decode()
    except (binascii.Error, UnicodeDecodeError, ValueError):
        raise DidomiError(400, "Invalid cursor", {"$cursor": "Invalid cursor"})


def _full_tree_limit(request: Request, response: Response, who: Principal, full_tree: bool) -> None:
    if full_tree:
        request.app.state.rate_limiter.hit(who.organization_id, response)


@router.get("/users", response_model=UserPage, summary="Retrieve users", **EXCLUDE)
def list_users(
    request: Request,
    response: Response,
    organization_id: str = Query(..., description="The ID of the organization for which to retrieve users"),
    cursor: str | None = Query(None, alias="$cursor", description="Cursor returned by the previous page"),
    organization_user_id: str | None = Query(None, description="The organization user ID to retrieve"),
    regulation: str = Query("gdpr"),
    by_organization_user_id: bool = Query(False, alias="$by_organization_user_id"),
    merge_users: bool = Query(False, alias="$merge_users"),
    include_full_tree: bool = Query(False, alias="$include_full_tree"),
    disable_integrations: bool = Query(False, alias="$disable_integrations"),
    who: Principal = Depends(principal),
    repo: ConsentRepository = Depends(repo_of),
):
    check_org(who, organization_id)
    _full_tree_limit(request, response, who, include_full_tree)
    page_size = request.app.state.settings.page_size
    users, last_id = repo.list_users(organization_id, request.app.state.clock(), after=_cursor_decode(cursor),
                                     limit=page_size, regulation=regulation,
                                     organization_user_id=organization_user_id, full_tree=include_full_tree)
    return {"data": users, "limit": page_size, "cursor": _cursor_encode(last_id)}


@router.get("/users/{id}", response_model=ConsentUser, summary="Retrieve a user", **EXCLUDE)
def get_user(
    request: Request,
    response: Response,
    id: str,
    organization_id: str = Query(...),
    regulation: str = Query("gdpr"),
    by_organization_user_id: bool = Query(False, alias="$by_organization_user_id"),
    merge_users: bool = Query(False, alias="$merge_users"),
    include_full_tree: bool = Query(False, alias="$include_full_tree"),
    who: Principal = Depends(principal),
    repo: ConsentRepository = Depends(repo_of),
):
    check_org(who, organization_id)
    _full_tree_limit(request, response, who, include_full_tree)
    user = repo.get_user(organization_id, request.app.state.clock(), id,
                         by_organization_user_id=by_organization_user_id, regulation=regulation,
                         full_tree=include_full_tree)
    if user is None:
        raise DidomiError(404, f"No record found for id '{id}'")
    return user


@router.get("/events", response_model=EventList, summary="Retrieve events", **EXCLUDE)
def list_events(
    request: Request,
    organization_id: str = Query(...),
    user_id: str | None = Query(None),
    organization_user_id: str | None = Query(None),
    status_in: list[str] | None = Query(None, alias="status[$in]"),
    status: str | None = Query(None),
    regulation: str = Query("gdpr"),
    include_full_tree: bool = Query(False, alias="$include_full_tree"),
    who: Principal = Depends(principal),
    repo: ConsentRepository = Depends(repo_of),
):
    check_org(who, organization_id)
    if not user_id and not organization_user_id:
        raise DidomiError(400, "You must provide either user_id or organization_user_id when querying events")
    statuses = status_in or ([status] if status else ["confirmed"])
    events = repo.list_events(organization_id, request.app.state.clock(), user_id=user_id,
                              organization_user_id=organization_user_id, statuses=statuses, regulation=regulation)
    return {"data": events}


@router.get("/events/{id}", response_model=ConsentEvent, summary="Retrieve an event", **EXCLUDE)
def get_event(
    request: Request,
    id: str,
    organization_id: str = Query(...),
    who: Principal = Depends(principal),
    repo: ConsentRepository = Depends(repo_of),
):
    check_org(who, organization_id)
    event = repo.get_event(organization_id, request.app.state.clock(), id)
    if event is None:
        raise DidomiError(404, f"No record found for id '{id}'")
    return event


def _validate(event: ConsentEventIn) -> None:
    """API v2 validation: only purposes, preferences and values that exist in the organisation."""
    errors: dict[str, str] = {}
    for i, p in enumerate(event.consents.purposes):
        purpose = cat.PURPOSES.get(p.id)
        if purpose is None:
            errors[f"consents.purposes[{i}].id"] = f"Unknown purpose '{p.id}'"
            continue
        for pref_id, v in (p.values or {}).items():
            pref = purpose.get("preferences", {}).get(pref_id)
            if pref is None:
                errors[f"consents.purposes[{i}].values.{pref_id}"] = f"Unknown preference '{pref_id}' for purpose '{p.id}'"
                continue
            chosen = [x for x in v.value.split(",") if x]
            bad = [x for x in chosen if x not in pref["values"]]
            if bad:
                errors[f"consents.purposes[{i}].values.{pref_id}.value"] = f"Unknown value(s) {','.join(bad)}"
            elif len(chosen) > 1 and not pref["multi"]:
                errors[f"consents.purposes[{i}].values.{pref_id}.value"] = "Only one value is allowed"
        if p.enabled_li is not None and p.id not in cat.LI_PURPOSES:
            errors[f"consents.purposes[{i}].enabled_li"] = f"Legitimate interest does not apply to '{p.id}'"
    for i, ch in enumerate(event.consents.channels):
        if ch.id not in cat.CHANNELS:
            errors[f"consents.channels[{i}].id"] = f"Unknown channel '{ch.id}'"
    if event.consents.vendors:
        for bucket, ids in event.consents.vendors.model_dump().items():
            for vid in ids:
                if vid not in cat.VENDOR_IDS:
                    errors[f"consents.vendors.{bucket}"] = f"Unknown vendor '{vid}'"
    if event.created_at:
        try:
            parse_iso(event.created_at)
        except ValueError:
            errors["created_at"] = "created_at must be an ISO 8601 date"
    if errors:
        raise DidomiError(400, "Invalid consent event", errors)


@router.post("/events", response_model=ConsentEvent, summary="Create a new event", **EXCLUDE)
def create_event(
    request: Request,
    event: ConsentEventIn,
    organization_id: str | None = Query(None, description="The ID of the organization for which to create an event"),
    disable_integrations: bool = Query(False, alias="$disable_integrations"),
    generate_tcfcs: bool = Query(False, alias="$generate_tcfcs"),
    who: Principal = Depends(principal),
    repo: ConsentRepository = Depends(repo_of),
):
    org = organization_id or event.organization_id
    if not org:
        raise DidomiError(400, "organization_id is required", {"organization_id": "Field required"})
    check_org(who, org)
    if event.organization_id and event.organization_id != org:
        raise DidomiError(400, "organization_id in the body does not match the query string")
    _validate(event)
    return repo.create_event(org, request.app.state.clock(), event.model_dump(exclude_none=True), who.key)
