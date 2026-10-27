"""Runtime settings, read once from the environment."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


@dataclass(frozen=True)
class ApiKey:
    key: str
    secret: str
    organization_id: str


@dataclass(frozen=True)
class Settings:
    keys: tuple[ApiKey, ...] = (ApiKey("demo-key", "demo-secret", "demo-org"),)
    jwt_secret: str = "change-me"
    seed: str = "didomi-sim"
    users: int = 3000
    # Population timeline: created_at spreads over [anchor - past_days, anchor + future_days).
    anchor: datetime = datetime(2026, 10, 27, tzinfo=timezone.utc)
    past_days: int = 180
    future_days: int = 60
    # Incident window: opt-in rates drop for events from one source type.
    incident_start: datetime | None = datetime(2026, 10, 13, tzinfo=timezone.utc)
    incident_days: int = 5
    incident_source: str = "sdk-mobile"
    # Optional frozen clock (ISO-8601). None = real UTC time.
    now: datetime | None = None
    rate_limit: int = 100
    rate_window_s: int = 15
    page_size: int = 100

    @property
    def incident_end(self) -> datetime | None:
        if self.incident_start is None or self.incident_days <= 0:
            return None
        return self.incident_start + timedelta(days=self.incident_days)


def _date(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def parse_keys(value: str) -> tuple[ApiKey, ...]:
    """JSON list of {key, secret, organization_id}, or the brace-free form
    `key:secret:organization_id[,key:secret:organization_id...]` for env editors that reject braces."""
    value = value.strip()
    if value.startswith("["):
        return tuple(ApiKey(k["key"], k["secret"], k["organization_id"]) for k in json.loads(value))
    keys = []
    for entry in filter(None, (e.strip() for e in value.split(","))):
        parts = entry.split(":")
        if len(parts) != 3 or not all(parts):
            raise ValueError("DIDOMI_SIM_KEYS entries must be key:secret:organization_id")
        keys.append(ApiKey(*parts))
    return tuple(keys)


def load_settings() -> Settings:
    env = os.environ
    kwargs: dict = {}
    if env.get("DIDOMI_SIM_KEYS"):
        kwargs["keys"] = parse_keys(env["DIDOMI_SIM_KEYS"])
    for name, attr, cast in [
        ("DIDOMI_SIM_JWT_SECRET", "jwt_secret", str),
        ("DIDOMI_SIM_SEED", "seed", str),
        ("DIDOMI_SIM_USERS", "users", int),
        ("DIDOMI_SIM_ANCHOR", "anchor", _date),
        ("DIDOMI_SIM_PAST_DAYS", "past_days", int),
        ("DIDOMI_SIM_FUTURE_DAYS", "future_days", int),
        ("DIDOMI_SIM_INCIDENT_DAYS", "incident_days", int),
        ("DIDOMI_SIM_INCIDENT_SOURCE", "incident_source", str),
        ("DIDOMI_SIM_NOW", "now", _date),
    ]:
        if env.get(name):
            kwargs[attr] = cast(env[name])
    if "DIDOMI_SIM_INCIDENT_START" in env:
        kwargs["incident_start"] = _date(env["DIDOMI_SIM_INCIDENT_START"]) if env["DIDOMI_SIM_INCIDENT_START"] else None
    return Settings(**kwargs)
