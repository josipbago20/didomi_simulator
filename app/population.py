"""Deterministic, database-less consent population.

Every user and every scheduled consent event is a pure function of
(seed, organization_id, user index). A read at time `now` only sees users and events whose
timestamp is <= now, and a user's `consents` block is the fold of its visible events, so a
client that pulls daily sees new users and changed consents every day while history never
moves. Events created through the API are appended to the same in-memory structures (the
"overlay"); they are lost on restart.
"""
from __future__ import annotations

import base64
import random
import threading
import uuid
from bisect import bisect_right, insort
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Protocol

from . import catalogue as cat
from .config import Settings

NAMESPACE = uuid.UUID("6f1d7c1e-5b0a-4d55-9a57-3d1f2b0c9e11")
FIRST_NAMES = ["camille", "lucas", "lea", "hugo", "emma", "jonas", "sofia", "mateo", "giulia", "liam",
               "anna", "noah", "marta", "oliver", "julia", "elias", "clara", "louis", "ines", "paul"]
LAST_NAMES = ["martin", "bernard", "muller", "schmidt", "garcia", "rossi", "smith", "jansen", "peeters",
              "nowak", "andersson", "dubois", "lopez", "ricci", "brown", "devries", "kowalski", "moreau"]
MAIL_DOMAINS = ["gmail.com", "outlook.com", "yahoo.fr", "gmx.de", "orange.fr", "icloud.com", "proton.me"]
PHONE_PREFIX = {"FR": "+336", "DE": "+4915", "ES": "+346", "IT": "+393", "GB": "+447", "NL": "+316",
                "BE": "+324", "US": "+1415", "PL": "+485", "SE": "+467"}
SOURCES = {
    "sdk-web": {"type": "sdk-web", "key": "4f0c2b9e-7a1d-4c3e-9b8a-2d6e5f1a0c37", "provider": "didomi",
                "target": cat.WEB_DOMAIN, "deployment_id": "Hc7Xq2Lm"},
    "sdk-mobile": {"type": "sdk-mobile", "key": "4f0c2b9e-7a1d-4c3e-9b8a-2d6e5f1a0c37", "provider": "didomi",
                   "target": cat.APP_BUNDLE, "deployment_id": "pT9wZr4K"},
    "api": {"type": "api", "key": "crm-sync", "provider": "demo-retail-crm",
            "target": cat.PREFERENCE_CENTER_DOMAIN, "deployment_id": None},
}


def iso(dt: datetime) -> str:
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class ConsentRepository(Protocol):
    """What the routers need. A Postgres-backed implementation can replace the generator."""

    def list_users(self, org: str, now: datetime, *, after: str | None, limit: int, regulation: str,
                   organization_user_id: str | None = None, full_tree: bool = False
                   ) -> tuple[list[dict], str | None]: ...

    def get_user(self, org: str, now: datetime, user_id: str, *, by_organization_user_id: bool,
                 regulation: str, full_tree: bool = False) -> dict | None: ...

    def list_events(self, org: str, now: datetime, *, user_id: str | None, organization_user_id: str | None,
                    statuses: list[str], regulation: str) -> list[dict]: ...

    def get_event(self, org: str, now: datetime, event_id: str) -> dict | None: ...

    def create_event(self, org: str, now: datetime, body: dict, source_key: str) -> dict: ...


@dataclass
class Profile:
    id: str
    created: datetime
    country: str
    source: str
    organization_user_id: str | None
    organization_user_id_type: str | None
    email: str | None
    phone: str | None
    metadata: dict
    device_id: str | None
    # (timestamp, event) sorted by timestamp
    events: list[tuple[datetime, dict]] = field(default_factory=list)


class _Population:
    def __init__(self) -> None:
        self.profiles: dict[str, Profile] = {}
        self.sorted_ids: list[str] = []
        self.by_org_user: dict[str, str] = {}
        self.event_owner: dict[str, str] = {}

    def add(self, prof: Profile) -> None:
        self.profiles[prof.id] = prof
        if prof.organization_user_id:
            self.by_org_user.setdefault(prof.organization_user_id, prof.id)
        for _, ev in prof.events:
            self.event_owner[ev["id"]] = prof.id


class GeneratedRepository:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        self._pops: dict[str, _Population] = {}
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- generation

    def _pop(self, org: str) -> _Population:
        pop = self._pops.get(org)
        if pop is None:
            with self._lock:
                pop = self._pops.get(org)
                if pop is None:
                    pop = _Population()
                    for i in range(self.s.users):
                        pop.add(self._generate(org, i))
                    pop.sorted_ids = sorted(pop.profiles)
                    self._pops[org] = pop
        return pop

    def _opt_in(self, country: str, source: str, ts: datetime) -> float:
        p = cat.COUNTRIES[country][1]
        end = self.s.incident_end
        if end and source == self.s.incident_source and self.s.incident_start <= ts < end:
            p *= 0.35
        return p

    def _generate(self, org: str, i: int) -> Profile:
        key = f"{self.s.seed}|{org}|{i}"
        rng = random.Random(key)
        span = (self.s.past_days + self.s.future_days) * 86400
        created = self.s.anchor - timedelta(days=self.s.past_days) + timedelta(
            seconds=rng.random() * span, milliseconds=rng.randrange(1000))
        country = rng.choices(list(cat.COUNTRIES), [c[0] for c in cat.COUNTRIES.values()])[0]
        source = rng.choices(list(cat.SOURCE_TYPES), list(cat.SOURCE_TYPES.values()))[0]
        identified = source == "api" or rng.random() < (0.75 if source == "sdk-mobile" else 0.5)
        org_user_id = org_user_type = email = phone = None
        metadata: dict = {}
        if identified:
            first, last = rng.choice(FIRST_NAMES), rng.choice(LAST_NAMES)
            email = f"{first}.{last}{rng.randrange(10, 9999)}@{rng.choice(MAIL_DOMAINS)}"
            if rng.random() < 0.7:
                org_user_id, org_user_type = email, "email"
            else:
                org_user_id, org_user_type = f"CRM-{1_000_000 + i:08d}", "customer_id"
            if rng.random() < 0.4:
                phone = PHONE_PREFIX[country] + "".join(str(rng.randrange(10)) for _ in range(8))
            if rng.random() < 0.5:
                metadata = {"loyalty_tier": rng.choice(["bronze", "silver", "gold"])}
        prof = Profile(
            id=str(uuid.uuid5(NAMESPACE, f"{key}|user")), created=created, country=country, source=source,
            organization_user_id=org_user_id, organization_user_id_type=org_user_type, email=email, phone=phone,
            metadata=metadata,
            device_id=str(uuid.uuid5(NAMESPACE, f"{key}|device")) if source == "sdk-mobile" else None,
        )
        n_events = rng.choices([1, 2, 3, 4], [45, 30, 15, 10])[0]
        ts = created
        for k in range(n_events):
            if k:
                ts = ts + timedelta(hours=max(1.0, rng.expovariate(1 / (24 * 25))), milliseconds=rng.randrange(1000))
            ev_source = source if k == 0 or rng.random() < 0.7 else "api"
            ev_id = str(uuid.uuid5(NAMESPACE, f"{key}|event|{k}"))
            p = self._opt_in(country, ev_source, ts)
            status, validation, delegate = "confirmed", None, None
            if k == 0:
                consents = self._initial_choice(rng, prof, p, ev_source)
            elif rng.random() < 0.2:
                consents = self._withdrawal(prof)
            else:
                consents = self._update(rng, prof, p)
            if k and ev_source == "api":
                if rng.random() < 0.15:
                    status = "pending_approval"
                    validation = {"type": "email",
                                  "approve_url": f"https://{cat.PREFERENCE_CENTER_DOMAIN}/approve/event/{ev_id}"}
                if rng.random() < 0.25:
                    delegate = {"id": f"agent-{rng.randrange(1, 40):04d}", "name": "Customer Support Agent",
                                "metadata": {"team": "customer-care"}}
            seen = country if rng.random() > 0.05 else rng.choice(list(cat.COUNTRIES))
            prof.events.append((ts, self._event(org, prof, ev_id, ts, ev_source, consents, rng, status=status,
                                                validation=validation, delegate=delegate, seen_country=seen)))
        return prof

    @staticmethod
    def _purpose(pid: str, enabled: bool | None, enabled_li: bool | None = None, values: dict | None = None) -> dict:
        return {"id": pid, "enabled": enabled, "enabled_li": enabled_li, "metadata": {},
                "values": {k: {"value": v, "from_propagation": False} for k, v in (values or {}).items()}}

    def _pick_values(self, rng: random.Random, purpose: dict) -> dict:
        values = {}
        for pref_id, pref in purpose["preferences"].items():
            ids = list(pref["values"])
            chosen = rng.sample(ids, rng.randint(1, len(ids))) if pref["multi"] else [rng.choice(ids)]
            values[pref_id] = ",".join(v for v in ids if v in chosen)
        return values

    def _initial_choice(self, rng: random.Random, prof: Profile, p: float, source: str) -> dict:
        r = rng.random()
        mode = "accept" if r < p else ("refuse" if r < p + (1 - p) * 0.55 else "custom")
        purposes = []
        for tp in cat.TCF_PURPOSES:
            enabled = mode == "accept" or (mode == "custom" and rng.random() < min(0.98, p * tp["appeal"]))
            li = None
            if tp["li"]:
                li = mode == "accept" or (mode == "custom" and rng.random() < 0.85)
            purposes.append(self._purpose(tp["id"], enabled, li))
        if mode == "accept":
            vendors = {"enabled": list(cat.VENDOR_IDS), "disabled": [], "enabled_li": list(cat.LI_VENDORS),
                       "disabled_li": []}
        elif mode == "refuse":
            vendors = {"enabled": [], "disabled": list(cat.VENDOR_IDS), "enabled_li": [],
                       "disabled_li": list(cat.LI_VENDORS)}
        else:
            on = {v for v in cat.VENDOR_IDS if rng.random() < p}
            li_on = {v for v in cat.LI_VENDORS if rng.random() < 0.85}
            vendors = {"enabled": [v for v in cat.VENDOR_IDS if v in on],
                       "disabled": [v for v in cat.VENDOR_IDS if v not in on],
                       "enabled_li": [v for v in cat.LI_VENDORS if v in li_on],
                       "disabled_li": [v for v in cat.LI_VENDORS if v not in li_on]}
        channels = []
        if prof.organization_user_id:
            newsletter = False
            for cp in cat.CUSTOM_PURPOSES:
                enabled = rng.random() < min(0.95, p * cp["appeal"] * 1.3)
                newsletter |= enabled and cp["id"] == "newsletter"
                purposes.append(self._purpose(cp["id"], enabled, None, self._pick_values(rng, cp) if enabled else None))
            channels.append({"id": "email", "enabled": newsletter or rng.random() < p * 0.4, "metadata": {}})
            if prof.phone:
                channels.append({"id": "sms", "enabled": rng.random() < p * 0.35, "metadata": {}})
        if source == "sdk-mobile":
            channels.append({"id": "push", "enabled": rng.random() < p * 0.8, "metadata": {}})
        tcfcs = None
        if source.startswith("sdk"):
            tcfcs = "CQ" + base64.urlsafe_b64encode(rng.randbytes(54)).decode().rstrip("=") + ".YAAAAAAAAAAA"
        return {"channels": channels, "purposes": purposes, "vendors": vendors, "tcfcs": tcfcs}

    def _update(self, rng: random.Random, prof: Profile, p: float) -> dict:
        purposes, channels = [], []
        vendors = {"enabled": [], "disabled": [], "enabled_li": [], "disabled_li": []}
        kinds = ["tcf", "vendors"] + (["custom", "custom", "channel"] if prof.organization_user_id else [])
        for kind in rng.sample(kinds, rng.randint(1, min(3, len(kinds)))):
            if kind == "tcf":
                for tp in rng.sample(cat.TCF_PURPOSES, rng.randint(1, 3)):
                    purposes.append(self._purpose(tp["id"], rng.random() < p * tp["appeal"]))
            elif kind == "vendors":
                for v in rng.sample(cat.VENDOR_IDS, rng.randint(2, 5)):
                    vendors["enabled" if rng.random() < p else "disabled"].append(v)
            elif kind == "custom":
                cp = rng.choice(cat.CUSTOM_PURPOSES)
                if cp["id"] in {x["id"] for x in purposes}:
                    continue
                enabled = rng.random() < min(0.95, p * cp["appeal"] * 1.3)
                purposes.append(self._purpose(cp["id"], enabled, None, self._pick_values(rng, cp) if enabled else None))
            else:
                ch = rng.choice(["email", "sms"] if prof.phone else ["email"])
                channels.append({"id": ch, "enabled": rng.random() < 0.5, "metadata": {}})
        return {"channels": channels, "purposes": purposes, "vendors": vendors, "tcfcs": None}

    def _withdrawal(self, prof: Profile) -> dict:
        purposes = [self._purpose(tp["id"], False, False if tp["li"] else None) for tp in cat.TCF_PURPOSES]
        channels = []
        if prof.organization_user_id:
            purposes += [self._purpose(cp["id"], False) for cp in cat.CUSTOM_PURPOSES]
            channels = [{"id": "email", "enabled": False, "metadata": {}}]
            if prof.phone:
                channels.append({"id": "sms", "enabled": False, "metadata": {}})
        if prof.device_id:
            channels.append({"id": "push", "enabled": False, "metadata": {}})
        vendors = {"enabled": [], "disabled": list(cat.VENDOR_IDS), "enabled_li": [],
                   "disabled_li": list(cat.LI_VENDORS)}
        return {"channels": channels, "purposes": purposes, "vendors": vendors, "tcfcs": None}

    def _event(self, org: str, prof: Profile, ev_id: str, ts: datetime, source: str, consents: dict,
               rng: random.Random | None, *, status: str = "confirmed", validation: dict | None = None,
               delegate: dict | None = None, seen_country: str | None = None, regulation: str = "gdpr",
               source_block: dict | None = None, metadata: dict | None = None) -> dict:
        sdk = source.startswith("sdk")
        iab = {}
        if sdk and rng is not None:
            iab = {"tcf": {"version": 2, "cmp_id": cat.DIDOMI_CMP_ID, "cmp_version": 2, "consent_screen": 1,
                           "consent_language": cat.COUNTRIES[prof.country][2],
                           "vendor_list_version": 80 + (ts - datetime(2024, 1, 4, tzinfo=timezone.utc)).days // 7,
                           "publisher_cc": "FR", "use_non_standard_texts": False, "purpose_one_treatment": False}}
        return {
            "id": ev_id,
            "organization_id": org,
            "created_at": iso(ts),
            "updated_at": iso(ts),
            "metadata": metadata or {},
            "user": {"id": prof.id, "organization_user_id": prof.organization_user_id,
                     "organization_user_id_type": prof.organization_user_id_type, "metadata": dict(prof.metadata),
                     "country": prof.country, "last_seen_country": seen_country or prof.country,
                     "email": prof.email, "phone": prof.phone},
            "source": source_block or dict(SOURCES[source]),
            "consents": {**consents, "gpp_string": None, "updated_at": iso(ts)},
            "delegate": delegate,
            "device_id": prof.device_id if source == "sdk-mobile" else None,
            "proofs_id": [],
            "validation": validation,
            "status": status,
            "domain": cat.PREFERENCE_CENTER_DOMAIN if source == "api" else None,
            "regulation": regulation,
            "iab": iab,
        }

    # ---------------------------------------------------------------- reads

    @staticmethod
    def _fold(events: list[dict]) -> dict:
        channels: dict[str, dict] = {}
        purposes: dict[str, dict] = {}
        vendors = {k: {} for k in ("enabled", "disabled", "enabled_li", "disabled_li")}
        opposite = {"enabled": "disabled", "disabled": "enabled", "enabled_li": "disabled_li",
                    "disabled_li": "enabled_li"}
        tcfcs = updated = None
        for ev in events:
            c = ev["consents"]
            for ch in c.get("channels") or []:
                channels[ch["id"]] = {"id": ch["id"], "enabled": ch.get("enabled"), "metadata": dict(ch.get("metadata") or {})}
            for p in c.get("purposes") or []:
                cur = purposes.setdefault(p["id"], {"id": p["id"], "enabled": None, "enabled_li": None,
                                                    "metadata": {}, "values": {}})
                for flag in ("enabled", "enabled_li"):
                    if p.get(flag) is not None:
                        cur[flag] = p[flag]
                cur["metadata"].update(p.get("metadata") or {})
                for pref, v in (p.get("values") or {}).items():
                    cur["values"][pref] = {"value": v["value"]}
            for bucket, ids in (c.get("vendors") or {}).items():
                for vid in ids or []:
                    vendors[bucket][vid] = None
                    vendors[opposite[bucket]].pop(vid, None)
            tcfcs = c.get("tcfcs") or tcfcs
            updated = ev["created_at"]
        return {"channels": list(channels.values()), "purposes": list(purposes.values()),
                "vendors": {k: list(v) for k, v in vendors.items()}, "tcfcs": tcfcs, "updated_at": updated}

    @staticmethod
    def _full_tree(consents: dict) -> dict:
        state = {p["id"]: p for p in consents["purposes"]}
        purposes = []
        for pid, cp in cat.PURPOSES.items():
            cur = state.pop(pid, None) or {"id": pid, "enabled": None, "enabled_li": None, "metadata": {}, "values": {}}
            values = {}
            for pref_id, pref in cp.get("preferences", {}).items():
                values[pref_id] = {
                    "value": cur["values"].get(pref_id, {}).get("value", ""), "from_tree": True, "parent_id": None,
                    "name": {"en": pref["name"]}, "description": {"en": pref["name"]},
                    "all_values": {vid: {"from_tree": True, "name": {"en": label}} for vid, label in pref["values"].items()},
                }
            purposes.append({**cur, "from_tree": True, "name": {"en": cp["name"]}, "description": {"en": cp["name"]},
                             "values": values})
        purposes += [{**p, "from_tree": False} for p in state.values()]
        return {**consents, "purposes": purposes, "config_tree": dict(cat.CONFIG_TREE)}

    def _render_user(self, org: str, prof: Profile, now: datetime, regulation: str, full_tree: bool) -> dict:
        visible = [ev for ts, ev in prof.events if ts <= now and ev["status"] == "confirmed"]
        consents = self._fold([ev for ev in visible if ev["regulation"] == regulation])
        if full_tree:
            consents = self._full_tree(consents)
        last = visible[-1] if visible else None
        return {
            "id": prof.id,
            "organization_id": org,
            "organization_user_id": prof.organization_user_id,
            "organization_user_id_type": prof.organization_user_id_type,
            "version": max(1, len(visible)),
            "created_at": iso(prof.created),
            "updated_at": last["created_at"] if last else iso(prof.created),
            "email": prof.email,
            "phone": prof.phone,
            "metadata": dict(prof.metadata),
            "api_metadata": {},
            "consents": consents,
            "country": prof.country,
            "last_seen_country": last["user"]["last_seen_country"] if last else prof.country,
        }

    def list_users(self, org, now, *, after, limit, regulation, organization_user_id=None, full_tree=False):
        pop = self._pop(org)
        if organization_user_id is not None:
            uid = pop.by_org_user.get(organization_user_id)
            ids = [uid] if uid else []
        else:
            ids = pop.sorted_ids[bisect_right(pop.sorted_ids, after) if after else 0:]
        out: list[dict] = []
        for uid in ids:
            prof = pop.profiles[uid]
            if prof.created > now:
                continue
            if len(out) == limit:
                return out, out[-1]["id"]
            out.append(self._render_user(org, prof, now, regulation, full_tree))
        return out, None

    def _find_user(self, pop: _Population, now: datetime, user_id: str | None, org_user_id: str | None):
        uid = user_id if user_id else pop.by_org_user.get(org_user_id or "")
        prof = pop.profiles.get(uid or "")
        return prof if prof and prof.created <= now else None

    def get_user(self, org, now, user_id, *, by_organization_user_id, regulation, full_tree=False):
        pop = self._pop(org)
        prof = self._find_user(pop, now, None if by_organization_user_id else user_id,
                               user_id if by_organization_user_id else None)
        return self._render_user(org, prof, now, regulation, full_tree) if prof else None

    def list_events(self, org, now, *, user_id, organization_user_id, statuses, regulation):
        prof = self._find_user(self._pop(org), now, user_id, organization_user_id)
        if prof is None:
            return []
        return [ev for ts, ev in prof.events
                if ts <= now and ev["status"] in statuses and ev["regulation"] == regulation]

    def get_event(self, org, now, event_id):
        pop = self._pop(org)
        prof = pop.profiles.get(pop.event_owner.get(event_id, ""))
        if prof is None:
            return None
        return next((ev for ts, ev in prof.events if ev["id"] == event_id and ts <= now), None)

    # ---------------------------------------------------------------- writes (overlay)

    def create_event(self, org, now, body, source_key):
        pop = self._pop(org)
        user_in = body.get("user") or {}
        ts = parse_iso(body["created_at"]) if body.get("created_at") else now
        with self._lock:
            prof = pop.profiles.get(user_in.get("id") or "")
            if prof is None and user_in.get("organization_user_id"):
                prof = pop.profiles.get(pop.by_org_user.get(user_in["organization_user_id"], ""))
            if prof is None:
                org_user_id = user_in.get("organization_user_id")
                prof = Profile(
                    id=user_in.get("id") or str(uuid.uuid4()), created=ts,
                    country=(user_in.get("country") or "FR").upper(), source="api",
                    organization_user_id=org_user_id,
                    organization_user_id_type="email" if org_user_id and "@" in org_user_id else
                    ("customer_id" if org_user_id else None),
                    email=org_user_id if org_user_id and "@" in org_user_id else None,
                    phone=None, metadata={}, device_id=None,
                )
                pop.add(prof)
                insort(pop.sorted_ids, prof.id)
            else:
                if user_in.get("organization_user_id") and not prof.organization_user_id:
                    prof.organization_user_id = user_in["organization_user_id"]
                    pop.by_org_user.setdefault(prof.organization_user_id, prof.id)
            prof.metadata.update(user_in.get("metadata") or {})
            if user_in.get("country"):
                prof.country = user_in["country"].upper()
            c = body.get("consents") or {}
            consents = {
                "channels": [{"id": ch["id"], "enabled": ch.get("enabled"), "metadata": ch.get("metadata") or {}}
                             for ch in c.get("channels") or []],
                "purposes": [{"id": p["id"], "enabled": p.get("enabled"), "enabled_li": p.get("enabled_li"),
                              "metadata": p.get("metadata") or {},
                              "values": {k: {"value": v["value"], "from_propagation": False}
                                         for k, v in (p.get("values") or {}).items()}}
                             for p in c.get("purposes") or []],
                "vendors": {k: list((c.get("vendors") or {}).get(k) or [])
                            for k in ("enabled", "disabled", "enabled_li", "disabled_li")},
                "tcfcs": c.get("tcfcs"),
            }
            ev = self._event(
                org, prof, body.get("id") or str(uuid.uuid4()), ts, "api", consents, None,
                status=body.get("status") or "confirmed", delegate=body.get("delegate"),
                seen_country=user_in.get("last_seen_country") or user_in.get("country"),
                regulation=body.get("regulation") or "gdpr", metadata=body.get("metadata"),
                source_block={"type": "api", "key": source_key, "provider": None, "target": None,
                              "deployment_id": None},
            )
            ev["proofs_id"] = list(body.get("proofs_id") or [])
            ev["domain"] = None
            insort(prof.events, (ts, ev), key=lambda item: item[0])
            pop.event_owner[ev["id"]] = prof.id
        return ev
