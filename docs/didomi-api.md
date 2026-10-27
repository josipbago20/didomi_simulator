# Didomi API — Consents & Preferences reference

The Didomi platform offers a standard REST API that you can use to read the consent and
preference choices your end users made through Didomi's consent notices (CMP), mobile SDKs,
preference centers and your own backend. This page is the complete reference for the routes a
data pipeline needs: authentication, consent users, consent events, and the metadata used to
label purposes and vendors.

| | |
|---|---|
| **Base URL** | `{{BASE_URL}}` |
| **Format** | JSON in, JSON out (`Content-Type: application/json`), including errors |
| **Auth** | `POST /sessions` with an API key + secret → JWT bearer token, valid 1 hour |
| **Timestamps** | ISO 8601, UTC, millisecond precision, e.g. `2026-10-23T06:47:21.345Z` |
| **Probe** | `GET /properties?organization_id={organization_id}` (cheap, always returns data) |

> This deployment is a Didomi API simulator with the same routes, parameters, envelopes and
> error bodies as `https://api.didomi.io/v1`. Swapping the base URL is the only change needed
> to point a client at the real Didomi API.

---

## 1. Authentication

All HTTP requests must be authorized with a JWT access token sent in the `Authorization`
header (`Authorization: Bearer <access_token>`). Calls without a valid token fail with `401`.

To generate an access token, send `POST /sessions` with a JSON body:

| Key | Value | Description |
|---|---|---|
| `type` | `api-key` | Always the literal string `api-key` |
| `key` | your API key | The private API key generated in the Didomi console (Settings → Private API keys) |
| `secret` | your API secret | The secret received with the key |

**Request**

```
POST {{BASE_URL}}/sessions
Content-Type: application/json

{"type": "api-key", "key": "<key>", "secret": "<secret>"}
```

**Response `200`**

```json
{
  "type": "api-key",
  "key": "<key>",
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJkZW1vLWtleSIsIm9yZ2FuaXphdGlvbl9pZCI6ImRlbW8tb3JnIn0.c2lnbmF0dXJl"
}
```

* The token is in `access_token`. There is **no** `expires_in` and **no** refresh token.
* Tokens expire **1 hour** after issue. Cache and reuse the token; log in again when a call
  returns `401` or before the hour is up.
* Bad key/secret (or a `type` other than `api-key`) → `400 BadRequest`.
* Every API key belongs to exactly one organization. Requests for another organization's
  `organization_id` → `403 Forbidden`.

---

## 2. Errors

Standard HTTP codes: `2xx` success, `4xx` a problem with the request, `5xx` a Didomi-side
error. The body of every error is:

| Property | Description | Example |
|---|---|---|
| `name` | Error name tied to the code | `BadRequest` |
| `message` | Human explanation | `Invalid authentication information` |
| `code` | HTTP status code | `400` |
| `className` | Kebab-case error class | `bad-request` |
| `errors` | Object of per-field errors (empty when not applicable) | `{"organization_id": "Field required"}` |

```json
{"name": "BadRequest", "message": "Invalid authentication information", "code": 400, "className": "bad-request", "errors": {}}
```

| Code | `name` | When |
|---|---|---|
| 400 | `BadRequest` | Bad credentials on `/sessions`; missing/invalid parameter (e.g. no `organization_id`); invalid `$cursor`; invalid consent event body |
| 401 | `NotAuthenticated` | Missing, malformed or expired bearer token |
| 403 | `Forbidden` | `organization_id` is not the organization of your API key |
| 404 | `NotFound` | Unknown user or event id |
| 429 | `TooManyRequests` | Rate limit exceeded (see §4); honour `Retry-After` |

---

## 3. Pagination

Two styles exist, depending on the route.

**Consent users — cursor pagination.** `GET /consents/users` returns pages of **100** users and
a `cursor`. Pass it back as the `$cursor` query-string parameter to get the next page. The
returned `cursor` is `null` on the last page. The cursor is opaque; do not build or modify it.

```json
{"data": [ ...up to 100 users... ], "limit": 100, "cursor": "MGJmYWEwYjYtNmZmMS01MWQwLWI1MTgtYTE2YWUwNDdjNjkz"}
```

Users are returned in a stable order (by `id`), so a crawl started at any time visits every user
that exists when the crawl starts exactly once. Users created during the crawl may or may not
appear; they will be picked up by the next crawl.

**Generic listings — offset pagination.** All other list routes (`/metadata/*`, `/properties`)
take `$limit` (page size, at most 100, default 100) and `$skip` (offset) and answer with:

```json
{"total": 13, "limit": 5, "skip": 0, "data": [ ... ]}
```

Keep increasing `$skip` by `limit` until `skip >= total`.

**Consent events** are not paginated: `GET /consents/events` returns every event of one user in
`{"data": [...]}`.

---

## 4. Rate limiting

| Routes | Limit |
|---|---|
| `/consents/*` | No limit |
| `/consents/users` and `/consents/users/{id}` **with** `$include_full_tree=true` | 100 requests every 15 seconds per organization |
| All other routes (`/metadata/*`, `/organizations/*`, `/properties`) | 100 requests every 15 seconds per organization |

Rate-limited routes return, on every response:

* `RateLimit: limit=100, remaining=60, reset=7` — requests left in the current window and
  seconds until it resets.
* `RateLimit-Policy: 100;w=15`

When the limit is exceeded the API answers `429 TooManyRequests` with a `Retry-After: <seconds>`
header. Wait that many seconds before retrying. `/sessions` is not rate limited.

---

## 5. Consent users

A consent **user** is the *latest consent state* of one end user, for one regulation (default
`gdpr`), together with the identifiers your organization attached to it. It is the entity to
read when you want to know whether you currently have consent for a purpose, a vendor or a
channel.

### 5.1 `GET /consents/users` — list users

**Data path:** `data` · **Pagination:** cursor (`$cursor` → `cursor`), 100 per page

| Parameter | In | Required | Description |
|---|---|---|---|
| `organization_id` | query | yes | Your organization ID |
| `$cursor` | query | no | Cursor from the previous page's `cursor` |
| `organization_user_id` | query | no | Return only the user with this organization user ID |
| `regulation` | query | no | Regulation of the consent state, default `gdpr` (e.g. `cpra`). Users with no event for that regulation come back with empty consents |
| `$include_full_tree` | query | no | `true` merges the whole configuration tree into `consents` (names, descriptions, every purpose/preference even if never chosen, `config_tree`). Rate limited |
| `$by_organization_user_id`, `$merge_users`, `$disable_integrations` | query | no | Accepted for compatibility; no effect on reads |

There are **no other filters** on this route: no `updated_at[$gte]`, no date range, no sort.

### 5.2 `GET /consents/users/{id}` — one user

| Parameter | In | Required | Description |
|---|---|---|---|
| `id` | path | yes | Didomi user ID, or your organization user ID when `$by_organization_user_id=true` |
| `organization_id` | query | yes | Your organization ID |
| `$by_organization_user_id` | query | no | `true` when `id` is an organization user ID |
| `$merge_users` | query | no | Aggregate users sharing the same organization user ID (accepted) |
| `regulation`, `$include_full_tree` | query | no | As above |

Unknown id → `404 NotFound`.

### 5.3 User record

```json
{
  "id": "0b108388-d50a-5ecb-a789-3876c154af7b",
  "organization_id": "demo-org",
  "organization_user_id": "CRM-01001196",
  "organization_user_id_type": "customer_id",
  "version": 2,
  "created_at": "2026-05-01T23:56:58.644Z",
  "updated_at": "2026-05-28T07:13:36.825Z",
  "email": "mateo.rossi396@gmail.com",
  "phone": "+48547623963",
  "metadata": {},
  "api_metadata": {},
  "consents": {
    "channels": [
      {"id": "email", "enabled": true, "metadata": {}},
      {"id": "sms", "enabled": false, "metadata": {}},
      {"id": "push", "enabled": true, "metadata": {}}
    ],
    "purposes": [
      {"id": "cookies", "enabled": true, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "select_basic_ads", "enabled": true, "enabled_li": true, "metadata": {}, "values": {}},
      {"id": "create_ads_profile", "enabled": true, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "select_personalized_ads", "enabled": true, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "create_content_profile", "enabled": true, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "select_personalized_content", "enabled": true, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "measure_ad_performance", "enabled": true, "enabled_li": true, "metadata": {}, "values": {}},
      {"id": "measure_content_performance", "enabled": true, "enabled_li": true, "metadata": {}, "values": {}},
      {"id": "market_research", "enabled": true, "enabled_li": true, "metadata": {}, "values": {}},
      {"id": "improve_products", "enabled": true, "enabled_li": true, "metadata": {}, "values": {}},
      {"id": "newsletter", "enabled": true, "enabled_li": null, "metadata": {},
       "values": {"topics": {"value": "fashion,sports"}, "frequency": {"value": "monthly"}}},
      {"id": "personalized_offers", "enabled": false, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "partner_sharing", "enabled": false, "enabled_li": null, "metadata": {}, "values": {}}
    ],
    "vendors": {
      "enabled": ["google", "criteo", "facebook", "amazon", "googleana-4TXnJigR", "c:loyalty-crm"],
      "disabled": ["tiktok-KZAUQLZ9"],
      "enabled_li": ["google", "criteo", "amazon"],
      "disabled_li": []
    },
    "tcfcs": "CQ_h1uFBuqkeGfr-v7jsWcqJbMGPzwSGOzBC5FGHe31qF03TpY-NJnE6SaTA3PrlC684WzvOVy.YAAAAAAAAAAA",
    "updated_at": "2026-05-28T07:13:36.825Z"
  },
  "country": "PL",
  "last_seen_country": "PL"
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Didomi user ID (UUID). Stable primary key of the user |
| `organization_id` | string | Organization that owns the user |
| `organization_user_id` | string \| null | Your own ID for the user (email, CRM id…). `null` for anonymous website visitors who never identified |
| `organization_user_id_type` | string \| null | Kind of `organization_user_id`: `email` or `customer_id` |
| `version` | number | Revision of the user record; increases with every confirmed consent event |
| `created_at` | ISO date | When the user was first seen (first consent event) |
| `updated_at` | ISO date | Last change to the user — the timestamp of its latest confirmed event. **Use it for change detection** |
| `email`, `phone` | string \| null | Contact identifiers known for the user |
| `metadata` | object | Free-form custom data (e.g. `loyalty_tier`) |
| `api_metadata` | object | System properties (`merge_fix_user`, `merge_fix_version` on merged users); usually `{}` |
| `consents.channels[]` | array | Communication channels: `id` (`email`, `sms`, `push`), `enabled` (`true` opted in, `false` opted out, `null` no choice), `metadata` |
| `consents.purposes[]` | array | One entry per purpose the user made a choice for |
| `consents.purposes[].id` | string | Purpose ID — join with `GET /metadata/purposes` |
| `consents.purposes[].enabled` | bool \| null | Consent: `true` given, `false` refused, `null` not specified |
| `consents.purposes[].enabled_li` | bool \| null | Legitimate interest: `true` no objection, `false` objected, `null` LI not applicable to the purpose |
| `consents.purposes[].values` | object | Preference choices, keyed by preference ID; `value` is a comma-separated list of chosen value IDs (`""` = none) |
| `consents.vendors.enabled` / `.disabled` | string[] | Vendors the user consented to / refused — join with `GET /metadata/partners` |
| `consents.vendors.enabled_li` / `.disabled_li` | string[] | Vendors whose legitimate interest the user accepted / objected to |
| `consents.tcfcs` | string \| null | IAB TCF consent string, when collected by a CMP |
| `consents.updated_at` | ISO date \| null | When the consent state last changed (`null` if no event for the regulation) |
| `country` | string \| null | ISO 3166-1 alpha-2 country of the user |
| `last_seen_country` | string \| null | Country of the user's latest consent event |

With `$include_full_tree=true` each purpose additionally carries `from_tree`, `name` and
`description` (`{"en": "..."}`), each preference value carries `from_tree`, `parent_id`, `name`,
`description`, `all_values`, every purpose of the configuration tree is listed (with
`enabled: null` when never chosen) and `consents.config_tree` = `{id, created_at, updated_at}`.

---

## 6. Consent events

A consent **event** is a partial update of a user's consent state: the choices the user made at
one moment, from one source. The user record is the merge of all its confirmed events in
chronological order (later choices win; items absent from an event keep their previous value).

### 6.1 `GET /consents/events` — events of one user

**Data path:** `data` · **Pagination:** none · **Order:** `created_at` ascending

| Parameter | In | Required | Description |
|---|---|---|---|
| `organization_id` | query | yes | Your organization ID |
| `user_id` | query | one of | Didomi user ID |
| `organization_user_id` | query | one of | Your organization user ID |
| `status[$in]` | query | no | Repeatable. `confirmed` (default) and/or `pending_approval` |
| `regulation` | query | no | Default `gdpr` |

Omitting both `user_id` and `organization_user_id` → `400`. There is no "all events" listing.

### 6.2 `GET /consents/events/{id}` — one event

`organization_id` (query) is required. Unknown id → `404`.

### 6.3 `POST /consents/events` — create an event

`organization_id` in the query string (required). Body:

```json
{
  "user": {"organization_user_id": "jane.doe@example.com", "metadata": {"source_campaign": "spring"}, "country": "FR"},
  "regulation": "gdpr",
  "consents": {
    "purposes": [
      {"id": "newsletter", "enabled": true, "values": {"topics": {"value": "tech,sports"}, "frequency": {"value": "weekly"}}},
      {"id": "select_personalized_ads", "enabled": false}
    ],
    "channels": [{"id": "email", "enabled": true}],
    "vendors": {"enabled": ["criteo"], "disabled": ["facebook"]}
  }
}
```

* `user.id` or `user.organization_user_id` identify an existing user; if neither matches, a new
  user is created (random `id` when none is given).
* Optional: `id`, `created_at` (ISO date, default now), `status`, `metadata`, `delegate`,
  `proofs_id`. Query flags `$disable_integrations`, `$generate_tcfcs` are accepted.
* Choices are validated: unknown purposes, preferences, preference values, channels or vendors,
  more than one value for a single-choice preference, or `enabled_li` on a purpose without a
  legitimate-interest basis → `400` with one entry per problem in `errors`.
* The response is the created event (§6.4). It is immediately visible in the user and event reads.

### 6.4 Event record

```json
{
  "id": "e7f9c855-df74-590b-a08b-82c4a78c4e79",
  "organization_id": "demo-org",
  "created_at": "2026-05-01T23:56:58.644Z",
  "updated_at": "2026-05-01T23:56:58.644Z",
  "metadata": {},
  "user": {
    "id": "0b108388-d50a-5ecb-a789-3876c154af7b",
    "organization_user_id": "CRM-01001196",
    "organization_user_id_type": "customer_id",
    "metadata": {},
    "country": "PL",
    "last_seen_country": "PL",
    "email": "mateo.rossi396@gmail.com",
    "phone": "+48547623963"
  },
  "source": {
    "type": "sdk-mobile",
    "key": "4f0c2b9e-7a1d-4c3e-9b8a-2d6e5f1a0c37",
    "provider": "didomi",
    "target": "com.demoretail.app",
    "deployment_id": "pT9wZr4K"
  },
  "consents": {
    "channels": [{"id": "email", "enabled": true, "metadata": {}}, {"id": "push", "enabled": true, "metadata": {}}],
    "purposes": [
      {"id": "cookies", "enabled": true, "enabled_li": null, "metadata": {}, "values": {}},
      {"id": "select_basic_ads", "enabled": true, "enabled_li": true, "metadata": {}, "values": {}},
      {"id": "newsletter", "enabled": true, "enabled_li": null, "metadata": {},
       "values": {"topics": {"value": "fashion,sports", "from_propagation": false},
                  "frequency": {"value": "monthly", "from_propagation": false}}}
    ],
    "vendors": {"enabled": ["google", "criteo"], "disabled": [], "enabled_li": ["google", "criteo"], "disabled_li": []},
    "tcfcs": "CQ_h1uFBuqkeGfr-v7jsWcqJbMGPzwSGOzBC5FGHe31qF03TpY-NJnE6SaTA3PrlC684WzvOVy.YAAAAAAAAAAA",
    "gpp_string": null,
    "updated_at": "2026-05-01T23:56:58.644Z"
  },
  "delegate": null,
  "device_id": "0de060e9-2c83-5878-8f70-155d2577f325",
  "proofs_id": [],
  "validation": null,
  "status": "confirmed",
  "domain": null,
  "regulation": "gdpr",
  "iab": {"tcf": {"version": 2, "cmp_id": 7, "cmp_version": 2, "consent_screen": 1, "consent_language": "PL",
                  "vendor_list_version": 201, "publisher_cc": "FR", "use_non_standard_texts": false,
                  "purpose_one_treatment": false}}
}
```

| Field | Type | Meaning |
|---|---|---|
| `id` | string | Event ID (UUID) |
| `organization_id` | string | Owning organization |
| `created_at` / `updated_at` | ISO date | When the choice was made / last modified |
| `metadata` | object | Free-form event data |
| `user` | object | Snapshot of the user at event time: `id`, `organization_user_id`, `organization_user_id_type`, `metadata`, `country`, `last_seen_country` (country the event came from), `email`, `phone` |
| `source.type` | string | Where the choice was collected: `sdk-web` (website consent notice), `sdk-mobile` (app SDK), `api` (server-to-server, preference center, CRM, support agent) |
| `source.key` / `.provider` / `.target` / `.deployment_id` | string \| null | Collecting key, provider, target website/app/domain, notice deployment |
| `consents` | object | The **partial** choices of this event, same shape as the user's `consents` plus `gpp_string`; preference values add `from_propagation`, purposes may add `propagation` |
| `delegate` | object \| null | Third party who acted for the user (`id`, `name`, `metadata`), e.g. a support agent |
| `device_id` | string \| null | Device identifier from mobile SDKs |
| `proofs_id` | string[] | Attached proofs |
| `validation` | object \| null | `{type: "email"\|"signature", approve_url}` for events that need approval |
| `status` | string | `confirmed` (applied to the user) or `pending_approval` (not applied yet) |
| `domain` | string \| null | Preference-center domain for `api` events |
| `regulation` | string | `gdpr`, `cpra`, … |
| `iab.tcf` | object | IAB TCF context of CMP events (CMP id 7 = Didomi, vendor list version, consent language…); `{}` for API events |

A **withdrawal** is an event that sets every purpose (and every channel) to `enabled: false` and
moves every vendor to `disabled` / `disabled_li`.

---

## 7. Metadata and organization

### 7.1 `GET /metadata/purposes`

**Data path:** `data` · **Pagination:** offset (`$limit`, `$skip`; envelope `total/limit/skip/data`) · rate limited

| Parameter | Required | Description |
|---|---|---|
| `organization_id` | yes | Your organization ID |
| `$limit`, `$skip` | no | Paging |
| `$translations` | no | `true` returns `description`/`details` as `{"en": "..."}` objects instead of strings |

```json
{
  "id": "select_personalized_ads",
  "type": "purpose",
  "description": "Use profiles to select personalised advertising",
  "details": "IAB TCF v2.2 purpose 4: Use profiles to select personalised advertising.",
  "reference": null,
  "organization_id": null,
  "namespaces": {"iab2": 4},
  "regulations_id": ["gdpr"],
  "metadata": {},
  "created_at": "2025-03-04T09:12:44.512Z",
  "updated_at": "2026-06-18T14:45:10.207Z"
}
```

`description` is the purpose's display **name**; `details` its longer text. `organization_id` is
`null` for global IAB purposes and your organization for custom ones. `namespaces.iab2` is the
IAB TCF purpose number. Custom purposes list their preferences and value IDs in
`metadata.preferences`.

### 7.2 `GET /metadata/partners`

Vendors (partners). **Data path:** `data` · offset pagination · rate limited. `organization_id`
optional.

```json
{
  "id": "criteo",
  "name": "Criteo SA",
  "category_id": "advertising",
  "country": "FR",
  "organization_id": null,
  "namespaces": {"iab2": 91},
  "default_purposes_id": ["cookies", "create_ads_profile", "select_personalized_ads"],
  "legitimate_interest_purposes_id": ["select_basic_ads", "measure_ad_performance"],
  "spi_purposes_id": [],
  "essential_purposes_id": [],
  "flexible_purposes_id": [],
  "taxonomy_id": null,
  "tags": [],
  "website": null,
  "website_optout": null,
  "contact": null,
  "hosts": [],
  "url_patterns": [],
  "cookie_max_duration": 13,
  "cookie_max_duration_unit": "months",
  "uses_non_cookie_access": false,
  "deprecated": false,
  "notes": null,
  "version": 1,
  "created_at": "2025-03-04T09:12:44.512Z",
  "updated_at": "2026-06-18T14:45:10.207Z"
}
```

`category_id` is one of `advertising`, `analytics`, `social`, `personalization`, `marketing`,
`support`. IDs prefixed `c:` are custom vendors created by your organization.

### 7.3 `GET /organizations/{id}`

Your organization (`id` = your `organization_id`; another id → `403`). Rate limited. Abridged
example:

```json
{"id": "demo-org", "name": "Demo Org", "website": "https://www.demo-retail.com", "industry_id": "retail",
 "public_api_key": "4f0c2b9e-7a1d-4c3e-9b8a-2d6e5f1a0c37", "version": 3, "validate_purpose_id": true,
 "iab_tcf_cmp_id": 7, "created_at": "2024-11-05T08:30:00.000Z", "updated_at": "2026-06-18T14:45:10.207Z"}
```

### 7.4 `GET /properties` (alias `GET /reports/compliances/properties`)

Websites and apps monitored for compliance. **Data path:** `data` · offset pagination · rate
limited. `organization_id` required. This is the recommended **connection probe**: it is cheap,
needs only the token and the organization ID, and always returns at least one row.

```json
{"total": 5, "limit": 100, "skip": 0, "data": [
  {"id": "prop-web-main", "name": "Demo Retail - main website", "website": "https://www.demo-retail.com",
   "country": "fr", "organization_id": "demo-org", "pages_count": 10, "schedule": "0 3 * * 1", "enabled": true,
   "filters": [], "created_at": "2025-03-04T09:12:44.512Z", "updated_at": "2026-06-18T14:45:10.207Z"}
]}
```

---

## 8. Reading consent data in bulk — recommended pattern

The Consents API has **no filters on `/consents/*`**: you cannot ask for "users updated since
yesterday" or "events of the last day". The supported way to keep a warehouse in sync is:

1. **Log in** (`POST /sessions`), keep the token for up to an hour.
2. **Crawl all users daily**: `GET /consents/users?organization_id=…`, follow `cursor` until it
   is `null` (≈ 30 pages for 3 000 users; no rate limit on this route — do not add
   `$include_full_tree`, which is rate limited).
3. **Diff on `updated_at`**: upsert users keyed by `id`; a user is new if its `id` was unknown,
   changed if its `updated_at` is later than the stored one. Unchanged users have byte-identical
   records.
4. **Fetch history only for new/changed users**: `GET /consents/events?organization_id=…&user_id=…`
   (add `status[$in]=confirmed&status[$in]=pending_approval` to also see pending ones). Upsert
   events by `id`.
5. **Join labels** from `GET /metadata/purposes` and `GET /metadata/partners` (small, cache daily).

Typical metrics: opt-in rate per purpose / vendor / channel / country / `source.type`
(share of `enabled: true` among users with a non-null choice); withdrawals per day (events that
set every purpose to `false`); **addressable audience** (users with an `organization_user_id` or
`email` and `channels[email].enabled = true` and the relevant purpose enabled);
**consent-gated suppression** lists (identified users whose purpose or channel is `false` must
be excluded from activation).

---

## 9. Glossary

| Term | Meaning |
|---|---|
| Organization | Your Didomi account; every key, user and event belongs to one (`organization_id`) |
| Consent user | Latest consent state of one end user for one regulation |
| Consent event | One partial update of a user's choices; the user is the fold of its confirmed events |
| Purpose | Why data is processed. IAB TCF purposes (`cookies`, `select_basic_ads`, `create_ads_profile`, `select_personalized_ads`, `create_content_profile`, `select_personalized_content`, `measure_ad_performance`, `measure_content_performance`, `market_research`, `improve_products`) and custom ones (`newsletter`, `personalized_offers`, `partner_sharing`) |
| Preference / value | Sub-choice of a custom purpose (e.g. `newsletter.topics` = `tech,sports`; `newsletter.frequency` = `weekly`; `personalized_offers.product_categories`) |
| Vendor / partner | Third party that processes data; consent is recorded per vendor |
| Channel | Communication medium the user opted in or out of: `email`, `sms`, `push` |
| Legitimate interest (LI) | Legal basis that needs no consent but allows objection; `enabled_li` on purposes, `enabled_li` / `disabled_li` vendor lists. Only `select_basic_ads`, `measure_ad_performance`, `measure_content_performance`, `market_research`, `improve_products` allow it |
| Opt-in | `enabled: true` |
| Opt-out / refusal | `enabled: false` |
| Withdrawal | Later event turning previously given consent to `false` everywhere |
| TCF string (`tcfcs`) | IAB Transparency & Consent Framework string produced by the CMP |
| Regulation | Legal framework of the consent state, `gdpr` by default (`cpra`, …) |
| Source type | `sdk-web`, `sdk-mobile`, `api` |
| Pending approval | Event awaiting email/signature validation; not applied to the user |
