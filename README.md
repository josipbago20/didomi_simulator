# Didomi API simulator

A FastAPI stand-in for the [Didomi API](https://developers.didomi.io/api-and-platform/introduction)
(`https://api.didomi.io/v1`) for demos without a Didomi licence. Same routes, parameters, envelopes
and error bodies as the real API for what a consent-data pipeline touches, so a client only has to
swap the base URL.

The reference a client (or AirForge's `learn_api_type`) learns from is
[`docs/didomi-api.md`](docs/didomi-api.md), also served at `GET /docs/didomi-api.md` with the
service's own base URL filled in. Swagger UI is at `/docs`.

## What it serves

| Route | Notes |
|---|---|
| `POST /v1/sessions` | `{"type":"api-key","key","secret"}` → `{"type","key","access_token"}` (HS256 JWT, 1 h). Bad credentials → 400 |
| `GET /v1/consents/users` | Cursor paging (`$cursor` → `cursor`, 100/page), envelope `{data, limit, cursor}`; `organization_user_id`, `regulation`, `$include_full_tree`, `$by_organization_user_id`, `$merge_users`, `$disable_integrations` |
| `GET /v1/consents/users/{id}` | By Didomi id, or by organization user id with `$by_organization_user_id=true` |
| `GET /v1/consents/events` | `user_id` or `organization_user_id` required, `status[$in]`, `regulation`; envelope `{data}` |
| `GET /v1/consents/events/{id}` | |
| `POST /v1/consents/events` | Validated against the catalogue, stored in memory, visible on the next read |
| `GET /v1/metadata/purposes`, `/v1/metadata/partners` | `$limit`/`$skip`, `{total, limit, skip, data}`; `$translations` on purposes |
| `GET /v1/organizations/{id}` | |
| `GET /v1/properties` (alias `/v1/reports/compliances/properties`) | The connection probe |
| `GET /health` | For load balancers |

Every `/v1` route except `/sessions` needs `Authorization: Bearer <token>` (401 otherwise) and
answers 403 when `organization_id` is not the token's organisation. Non-consent routes, and consent
user reads with `$include_full_tree=true`, are limited to 100 requests / 15 s per organisation
(`RateLimit`, `RateLimit-Policy` headers; 429 with `Retry-After`).

## How the data works

No database. Each organisation gets `DIDOMI_SIM_USERS` users generated purely from
`(DIDOMI_SIM_SEED, organization_id, index)`: `created_at` spread over
`[ANCHOR − PAST_DAYS, ANCHOR + FUTURE_DAYS)`, each with 1–4 scheduled consent events (initial
choice, partial updates, ~20 % withdrawals, some `pending_approval` API events). A request at time
`now` sees only users/events with timestamp ≤ now; a user's `consents` is the fold of its visible
confirmed events and `updated_at` is its last one. So a daily crawl always sees new users and
changed consents, while history and unchanged users stay byte-identical, across restarts too.

Built in for the demo narrative: country mix with different opt-in rates (DE ≈ 45 % … US ≈ 75 %),
`source.type` mix (`sdk-web` 60 %, `sdk-mobile` 30 %, `api` 10 %), half of web visitors anonymous
(no `organization_user_id`, so not addressable), legitimate interest on TCF purposes 2, 7–10 and on
IAB vendors, three custom purposes with preferences (`newsletter.topics/frequency`,
`personalized_offers.product_categories`, `partner_sharing`), `email`/`sms`/`push` channels, and an
**incident window** in which opt-in drops to 35 % of normal for one source type (default: 5 days
from 2026-10-13 on `sdk-mobile`).

Generation sits behind the `ConsentRepository` protocol in `app/population.py`; a database-backed
implementation can replace `GeneratedRepository` without touching the routers.

## Run locally

```bash
.venv/bin/pip install -r requirements.txt
```

```bash
.venv/bin/uvicorn app.main:app --port 8000
```

```bash
curl -s -X POST localhost:8000/v1/sessions -H 'content-type: application/json' -d '{"type":"api-key","key":"demo-key","secret":"demo-secret"}'
```

Without any env the service accepts `demo-key` / `demo-secret` for organisation `demo-org`.

Tests (FastAPI TestClient; auth, cursor coverage, determinism, daily delta, POST overlay,
validation, metadata paging, rate limiting):

```bash
.venv/bin/python -m pytest -q
```

## Environment

See [`.env.example`](.env.example).

| Variable | Default | Meaning |
|---|---|---|
| `DIDOMI_SIM_KEYS` | `[{"key":"demo-key","secret":"demo-secret","organization_id":"demo-org"}]` | JSON list of key/secret pairs, each bound to an organisation |
| `DIDOMI_SIM_JWT_SECRET` | `change-me` | Token signing secret — **set it** in any shared deployment |
| `DIDOMI_SIM_SEED` | `didomi-sim` | Changing it produces a different population |
| `DIDOMI_SIM_USERS` | `3000` | Users per organisation |
| `DIDOMI_SIM_ANCHOR` | `2026-10-27` | Centre of the timeline |
| `DIDOMI_SIM_PAST_DAYS` / `DIDOMI_SIM_FUTURE_DAYS` | `180` / `60` | Users appear over this window; after `ANCHOR + FUTURE_DAYS` no new users appear (move the anchor to extend) |
| `DIDOMI_SIM_INCIDENT_START` / `_DAYS` / `_SOURCE` | `2026-10-13` / `5` / `sdk-mobile` | Opt-in drop window; empty start disables it |
| `DIDOMI_SIM_NOW` | unset | Freeze the clock (ISO 8601) for reproducible demos |

## Deploy on DigitalOcean App Platform

The service is stateless apart from the in-memory POST overlay and rate-limit counters, so run
**one instance** (the smallest size is enough; the population takes a few tens of MB).

**From GitHub (recommended).** Create App → GitHub → `josipbago20/didomi_simulator`, branch `main`;
App Platform detects the `Dockerfile`. Set HTTP port `8080`, health check path `/health`, one
instance, and paste the environment variables (see `.env.example`; mark `DIDOMI_SIM_KEYS` and
`DIDOMI_SIM_JWT_SECRET` as encrypted). Or, with `doctl`, fill the two `REPLACE_ME` secrets in
[`.do/app.yaml`](.do/app.yaml) and run `doctl apps create --spec .do/app.yaml`.

**From a container registry**, instead:

1. Build for amd64 and push to your DigitalOcean Container Registry:

   ```bash
   doctl registry login
   ```

   ```bash
   docker build --platform linux/amd64 -t registry.digitalocean.com/<registry>/didomi-sim:1 .
   ```

   ```bash
   docker push registry.digitalocean.com/<registry>/didomi-sim:1
   ```

2. Create the app from a spec (`didomi-sim.yaml`):

   ```yaml
   name: didomi-sim
   services:
     - name: api
       image:
         registry_type: DOCR
         repository: didomi-sim
         tag: "1"
       http_port: 8080
       instance_count: 1
       instance_size_slug: basic-xxs
       health_check:
         http_path: /health
       envs:
         - key: DIDOMI_SIM_KEYS
           type: SECRET
           value: '[{"key":"<key>","secret":"<secret>","organization_id":"demo-org"}]'
         - key: DIDOMI_SIM_JWT_SECRET
           type: SECRET
           value: "<32+ random bytes>"
   ```

   ```bash
   doctl apps create --spec didomi-sim.yaml
   ```

   (Alternatively push this folder to GitHub and point the App Platform service at the repo; it
   detects the `Dockerfile`.) Add a custom domain such as `didomi-sim.<your-domain>` in the app's
   settings; App Platform provides TLS. The container honours `X-Forwarded-*`, so the served
   reference shows the public `https://…/v1` base URL.

## Registering it in AirForge

From `GET <base>/docs/didomi-api.md`: auth type `login`, token endpoint `/sessions`, JSON body with
static `{"type": "api-key"}` plus credential fields `key` and `secret` (secret),
`token_path: access_token`, no `expires_in` (tokens live 1 hour); cursor pagination on
`/consents/users` (`cursor_param: $cursor`, `cursor_path: cursor`, page size 100, `data_path: data`);
offset pagination (`$limit`/`$skip`, max 100) on metadata; probe `GET /properties?organization_id=…`.

## Verified against the real Didomi docs (2026-10-27)

Field lists were checked against developers.didomi.io (Users schema, Consent event schema, Query
user, Query/Create consent events, Authentication, Errors, Pagination, Rate limiting) and the
OpenAPI document embedded at `https://api.didomi.io/docs/`. The Stoplight reference itself was not
reachable, but these sources carry the same schemas. Where they differ from the original plan
(`air_forge_backend/docs/plans/didomi-simulator.md`), the simulator follows the real docs:

* `POST /sessions` returns `{"type", "key", "access_token"}` (Didomi's `sessions` schema), not only
  `access_token`. `token_path` is unchanged.
* `GET /consents/users` also accepts an `organization_user_id` filter (in Didomi's OpenAPI).
* `$include_full_tree=true` on consent-user reads **is** rate limited (rate-limiting page); without
  it `/consents/*` is unlimited. With it, purposes gain `from_tree`, `name`, `description`, values
  gain `from_tree`, `parent_id`, `name`, `description`, `all_values`, and `consents.config_tree` appears.
* Events' preference values carry `from_propagation`; events' `consents` has `gpp_string`; users'
  values carry only `value`. Event-level `metadata` is free-form (the plan's `metadata.url/user_agent`
  is not a Didomi field and is left out).
* `POST /consents/events` takes `organization_id` in the query string (Didomi's examples), and
  also accepts it in the body (OpenAPI).
* Didomi purposes in `/metadata/purposes` use `description` for the name and `details` for the text
  (strings, or `{"en": …}` objects with `$translations=true`); partners use `category_id`,
  `default_purposes_id`, `legitimate_interest_purposes_id`, `namespaces.iab2`.
* Didomi's properties route is `/reports/compliances/properties`; `/properties` (used in Didomi's
  authentication example) is served too, with the same handler.
* The OpenAPI document lists `/consents/users` and `/metadata/partners` as returning bare arrays;
  the developer docs show the `{data, limit, cursor}` and `{total, limit, skip, data}` envelopes,
  which the simulator follows.

## Not simulated

Preference-center widgets, notices, compliance reports, batch exports, proofs retrieval, integrations,
`$merge_users` semantics (accepted, ignored), `PATCH`/`DELETE` on users and events, TC strings that
decode to the actual choices (`tcfcs` only looks like one), and persistence of POSTed events across
restarts.
