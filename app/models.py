"""Response and request schemas, following developers.didomi.io (Users schema, Consent event
schema) and the OpenAPI document served at api.didomi.io/docs. Optional fields only appear
when set (routes use response_model_exclude_unset), e.g. the `$include_full_tree` extras."""
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class Session(BaseModel):
    type: str
    key: str
    access_token: str


class SessionInput(BaseModel):
    type: str
    key: str
    secret: str


class Channel(BaseModel):
    id: str
    enabled: bool | None = None
    metadata: dict[str, Any] = {}


class PreferenceValue(BaseModel):
    value: str
    from_propagation: bool | None = None
    from_tree: bool | None = None
    parent_id: str | None = None
    name: dict[str, str] | None = None
    description: dict[str, str] | None = None
    all_values: dict[str, dict[str, Any]] | None = None


class Purpose(BaseModel):
    id: str
    enabled: bool | None = None
    enabled_li: bool | None = None
    metadata: dict[str, Any] = {}
    values: dict[str, PreferenceValue] = {}
    propagation: bool | None = None
    from_tree: bool | None = None
    name: dict[str, str] | None = None
    description: dict[str, str] | None = None


class Vendors(BaseModel):
    enabled: list[str] = []
    disabled: list[str] = []
    enabled_li: list[str] = []
    disabled_li: list[str] = []


class ConfigTree(BaseModel):
    id: str
    created_at: str
    updated_at: str


class UserConsents(BaseModel):
    channels: list[Channel]
    purposes: list[Purpose]
    vendors: Vendors
    tcfcs: str | None
    updated_at: str | None
    config_tree: ConfigTree | None = None


class ConsentUser(BaseModel):
    id: str
    organization_id: str
    organization_user_id: str | None
    organization_user_id_type: str | None
    version: int
    created_at: str
    updated_at: str | None
    email: str | None
    phone: str | None
    metadata: dict[str, Any]
    api_metadata: dict[str, Any]
    consents: UserConsents
    country: str | None
    last_seen_country: str | None


class UserPage(BaseModel):
    data: list[ConsentUser]
    limit: int
    cursor: str | None


class EventUser(BaseModel):
    id: str
    organization_user_id: str | None
    organization_user_id_type: str | None
    metadata: dict[str, Any]
    country: str | None
    last_seen_country: str | None
    email: str | None
    phone: str | None


class Source(BaseModel):
    type: str
    key: str | None
    provider: str | None
    target: str | None
    deployment_id: str | None


class EventConsents(BaseModel):
    channels: list[Channel]
    purposes: list[Purpose]
    vendors: Vendors
    tcfcs: str | None
    gpp_string: str | None
    updated_at: str | None


class Delegate(BaseModel):
    id: str
    name: str | None = None
    metadata: dict[str, Any] = {}


class Validation(BaseModel):
    type: Literal["email", "signature"]
    approve_url: str | None = None


class ConsentEvent(BaseModel):
    id: str
    organization_id: str
    created_at: str
    updated_at: str | None
    metadata: dict[str, Any]
    user: EventUser
    source: Source
    consents: EventConsents
    delegate: Delegate | None
    device_id: str | None
    proofs_id: list[str]
    validation: Validation | None
    status: Literal["confirmed", "pending_approval"]
    domain: str | None
    regulation: str
    iab: dict[str, Any]


class EventList(BaseModel):
    data: list[ConsentEvent]


# ---------------------------------------------------------------- POST /consents/events body

class _In(BaseModel):
    model_config = ConfigDict(extra="ignore")


class ChannelIn(_In):
    id: str
    enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class ValueIn(_In):
    value: str


class PurposeIn(_In):
    id: str
    enabled: bool | None = None
    enabled_li: bool | None = None
    metadata: dict[str, Any] | None = None
    values: dict[str, ValueIn] | None = None


class VendorsIn(_In):
    enabled: list[str] = []
    disabled: list[str] = []
    enabled_li: list[str] = []
    disabled_li: list[str] = []


class ConsentsIn(_In):
    channels: list[ChannelIn] = []
    purposes: list[PurposeIn] = []
    vendors: VendorsIn | None = None
    tcfcs: str | None = None


class EventUserIn(_In):
    id: str | None = None
    organization_user_id: str | None = None
    metadata: dict[str, Any] | None = None
    country: str | None = Field(None, min_length=2, max_length=2)
    last_seen_country: str | None = Field(None, min_length=2, max_length=2)


class ConsentEventIn(_In):
    id: str | None = None
    organization_id: str | None = None
    created_at: str | None = None
    status: Literal["confirmed", "pending_approval"] | None = None
    regulation: str | None = None
    metadata: dict[str, Any] | None = None
    user: EventUserIn = EventUserIn()
    consents: ConsentsIn
    delegate: Delegate | None = None
    proofs_id: list[str] | None = None


# ---------------------------------------------------------------- generic listings

class Page(BaseModel):
    total: int
    limit: int
    skip: int
    data: list[dict[str, Any]]
