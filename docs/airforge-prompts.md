# AirForge prompts for the Didomi consent demo

Assumes the Didomi API type is learned and a data source "Didomi" is registered with the
demo-org credentials, and that a target database data source exists (below called "my
ClickHouse"; swap the name for whatever the demo uses).

## 0. Sanity check

> Test the Didomi data source and show me what one consent user and one of their consent events look like. How many users are there right now?

## Layer 1 — ingestion

> Create a daily pipeline called "Didomi consent ingestion" that pulls everything from the Didomi source into my ClickHouse. Crawl all consent users with the cursor until it is empty, upsert them into a table consent_users_raw keyed by id (keep the full JSON of the consents block too). For every user that is new or whose updated_at changed since the last run, fetch their consent events and upsert them into consent_events_raw keyed by event id. Also refresh two small tables from the metadata routes: dim_purposes and dim_vendors. Run it every day at 06:00 UTC, and run it once now so we have data.

> Show me the run and how many users and events landed. Then query consent_users_raw and give me the count of users per country.

## Layer 2 — curated model (chained after ingestion)

> Create a pipeline "Consent curated model" that runs right after "Didomi consent ingestion" finishes. From consent_users_raw build three long tables: consent_purpose_state (user_id, purpose_id, enabled, enabled_li, as_of_date), consent_vendor_state (user_id, vendor_id, status in enabled/disabled/enabled_li/disabled_li) and consent_channel_state (user_id, channel_id, enabled). From consent_events_raw build consent_events_flat with one row per event: event id, user id, created_at, source type, country, regulation, status, number of purposes enabled and disabled in the event, and a flag is_withdrawal when every purpose in the event is false. Finally build consent_user_daily: one row per user per day with country, days since first consent, number of enabled purposes, number of enabled vendors, email/sms/push flags and the source type of their latest event. Append today's snapshot each run, don't rewrite history.

## Layer 3 — KPI marts (each chained after the curated model)

> Add a pipeline "Consent opt-in rates" after "Consent curated model". For each day, purpose, country and source type compute the opt-in rate: users with enabled true divided by users with a non-null choice. Do the same per vendor and per channel. Join the purpose and vendor names from dim_purposes and dim_vendors. Write to kpi_optin_rates.

> Add a pipeline "Consent withdrawals and freshness" after "Consent curated model". Compute withdrawals per day and per source type, the median time from first consent to withdrawal, how many withdrawn users consented again later, and the distribution of consent age in buckets (under 30 days, 30-90, 90-180, 180-365, over a year). Also list how many users will cross 12 months of consent age in the next 30 days. Write to kpi_withdrawals and kpi_consent_freshness.

> Add a pipeline "Vendor reach" after "Consent curated model". For each vendor compute the addressable audience: users with that vendor enabled who also have every purpose in the vendor's default_purposes_id enabled, split by country, and separately the audience that rests only on legitimate interest. Write to kpi_vendor_reach.

## Layer 4 — derived and cross-source

> Create an endpoint group "Consent audiences" with an endpoint that takes a list of purpose ids, an optional vendor id and an optional country and returns the number of addressable identified users (users with an email, the email channel enabled and all the given purposes enabled), plus a paged list of their organization_user_ids. Read from the curated tables.

> Create a one-time job that generates a sample CRM table crm_customers with 5,000 rows: customer_id, email, country, segment and last_purchase_date. Reuse the emails from consent_users_raw for about 60% of the rows so they join, make the rest new.

> Create a pipeline "Consent-gated CRM export" that runs after "Consent curated model". Join crm_customers with the consent state and produce two tables: crm_activation_allowed (customers with email channel enabled and the newsletter purpose enabled) and crm_suppression_list (the rest, with the reason: no consent record, channel opted out, purpose refused, or withdrawn). Show me the counts per reason after the first run.

> Create a pipeline "Consent anomaly check" after "Consent opt-in rates". For each source type and country compare today's opt-in rate for the cookies purpose with the trailing 30-day mean and standard deviation, and write any day where it drops more than two standard deviations to consent_anomalies with the z-score. Run it now and tell me if it finds the mobile dip in mid October.

> Add a pipeline "Consent cohort retention" after "Consent curated model". Group users by the week of their first consent event and compute the share still fully opted in after 30, 60 and 90 days. Write to kpi_consent_cohorts.

## Layer 5 — contexts, MCP and app

> Create a context "Consent analytics" that links all the consent tables and the Didomi source and explains what each KPI table means, which fields to use for opt-in rates and what counts as a withdrawal.

> Create an MCP server "Consent assistant" for our DPO and marketing team with tools to get the opt-in rate for a purpose and country, to compute an addressable audience for a campaign, to check whether one customer email can be contacted, and to list the latest anomalies. Use the Consent analytics context.

> Build an app "Consent dashboard" with the opt-in rate trend per purpose, a country map of opt-in rates, withdrawals per day, the consent-age distribution, the vendor reach table and the latest anomalies.
