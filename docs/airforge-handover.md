# Handing the Didomi simulator to AirForge

*2026-10-27. Live deployment verified end to end (login, 23 cursor pages / 2 249 users visible
today, user by id, events per user, full tree, metadata, properties, organization, every error
code, rate-limit headers).*

## The document AirForge learns from

| | |
|---|---|
| **Docs URL** (give this to AirForge) | `https://didomi-simulator-4lltg.ondigitalocean.app/docs/didomi-api.md` |
| **Base URL** | `https://didomi-simulator-4lltg.ondigitalocean.app/v1` |
| **OpenAPI** (secondary) | `https://didomi-simulator-4lltg.ondigitalocean.app/openapi.json` |
| **Organization id** | `demo-org` |
| **Probe** | `GET /properties?organization_id=demo-org` |

The served copy is the same file as `docs/didomi-api.md` in this repo, with the base URL
filled in from the request host, so it always matches the deployment it is served from.

## What to say to AirForge (paste into the chat)

> Learn a new private API type for this project from
> https://didomi-simulator-4lltg.ondigitalocean.app/docs/didomi-api.md — it is the Didomi
> Consents & Preferences API (a simulator with the same routes as api.didomi.io). Name it
> `didomi`, display name "Didomi". Use the login auth flow described in section 1, cursor
> pagination on /consents/users, offset pagination on /metadata and /properties, and
> `GET /properties?organization_id=…` as the probe. Document every response field from
> sections 5.3, 6.4 and 7, and put the bulk-reading pattern from section 8 into the usage guide.

## The learned type, field by field (for checking what AirForge produced)

| Setting | Value |
|---|---|
| `auth.type` | `login` |
| `auth.fields` | `key` (text), `secret` (secret, password), `organization_id` (text) |
| `auth.login.url` | `/sessions` |
| `auth.login.send` / `body_format` | `body` / `json` |
| `auth.login.body` | `{"type": "api-key"}` |
| `auth.login.token_path` | `access_token` |
| `auth.login.token_header` / `token_prefix` | `Authorization` / `Bearer ` |
| `auth.login.expires_path` | `null` (no `expires_in`; tokens live 1 hour) |
| `spec.pagination` (default) | `offset`: `size_param` `$limit`, `offset_param` `$skip`, `max_page_size` 100 |
| `consents/users` endpoint pagination | `cursor`: `cursor_param` `$cursor`, `cursor_path` `cursor`, `max_page_size` 100 |
| `data_path` | `data` on every list route |
| `spec.rate_limit` | 100 requests / 15 s per organization on everything except `/consents/*` (unless `$include_full_tree=true`) |
| `spec.probe` | endpoint `list_properties`, params `{"organization_id": "demo-org"}` |

Endpoints worth registering: `create_session` (only if the learner wants it explicit; the login
block already covers it), `list_consent_users`, `get_consent_user`, `list_consent_events`,
`get_consent_event`, `create_consent_event` (write, optional), `list_purposes`,
`list_partners`, `get_organization`, `list_properties`.

## Registering the data source

In AirForge: Data sources → Register → API → Didomi. Fill in the key, the secret and
`organization_id = demo-org`, then press Test (it calls the probe).

Credentials: the deployment currently answers to the README defaults (`demo-key` /
`demo-secret`), which means `DIDOMI_SIM_KEYS` and `DIDOMI_SIM_JWT_SECRET` were **not** set on
App Platform. Before the customer demo, paste the contents of this folder's `.env` into the
app's environment (Settings → App-level environment variables → Bulk editor, mark both secrets
as encrypted) and redeploy; then register the source with the key/secret from `.env` instead.

## What the daily pipeline should do (section 8 of the reference)

1. Login once per run; 2. crawl `/consents/users` with `$cursor` until `cursor` is `null`;
3. upsert by `id`, detect changes on `updated_at`; 4. fetch `/consents/events?user_id=…` only
for new or changed users; 5. join `/metadata/purposes` and `/metadata/partners` for names.
Today's population shows 2 249 users; new users and consent changes appear every day, and
an opt-in dip on `sdk-mobile` events sits between 2026-10-13 and 2026-10-17 for the
anomaly story.
