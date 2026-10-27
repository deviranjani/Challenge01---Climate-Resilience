---
name: security
description: 'Review heat_planner code for secret handling, SQL-injection-by-LLM, and GCP scope issues. Use when: adding a new BigQuery query, a new environment variable, a new external API key, or reviewing a PR that touches agent/heat_planner/. Trigger phrases: "security review", "check for secrets", "is this SQL safe", "review this for security", "can the model inject SQL here".'
---

# Security

## When to Use This Skill

Before merging any change that adds a BigQuery query, a new environment variable/secret, a
new external API key, or touches `agent/heat_planner/bq.py` or `agent/heat_planner/tools/`.

## Prerequisites

Read `.claude/rules/security.md` and `.claude/rules/bigquery.md` first — this skill is the
checklist version of those rules, not a replacement for them.

## Secret Handling Checklist

- [ ] Every new secret/config value is read from `os.environ` (ideally through `config.py:load_settings()`), never hardcoded.
- [ ] No `.env` file is committed — confirm `.gitignore` still excludes it.
- [ ] A new Google Maps / client-exposed key is documented as needing API + URL restriction in `agent/README.md`, matching the existing `GOOGLE_MAPS_API_KEY` guidance.
- [ ] No GCP service-account JSON key file appears anywhere in the diff — this repo uses Application Default Credentials / the Cloud Run runtime service account, never a key file.

### ✅ Correct

```python
# config.py pattern — read from environment with a documented default
api_key = os.environ.get("NEW_SERVICE_API_KEY", "")
```

### ❌ Anti-pattern

```python
# Never do this — hardcoded secret in source
api_key = "AIzaSyD-hardcoded-key-example"
```

## SQL-Injection-by-LLM Checklist

The LLM supplies tool *arguments* only, never SQL text. For every new or changed query:

- [ ] The query string is fixed Python source text (an f-string is fine for table names/LIMIT constants the tool itself controls), with every LLM-/user-influenced value passed as a `bigquery.ScalarQueryParameter`.
- [ ] The tool validates its numeric/string arguments with `tools/_common.py`'s `validate_coordinates()` / `clamp_int()` (or an equivalent) before building the query.
- [ ] The tool is wrapped in `@safe_tool` so any failure becomes `{"status": "error", ...}`, never a raw exception reaching the model or the HTTP client.

### ✅ Correct

```python
rows = run_query(
    "SELECT * FROM t WHERE lat = @lat AND lon = @lon",
    [bigquery.ScalarQueryParameter("lat", "FLOAT64", lat),
     bigquery.ScalarQueryParameter("lon", "FLOAT64", lon)],
    settings,
)
```

### ❌ Anti-pattern

```python
# Never interpolate a user/model-supplied value directly into SQL text
rows = run_query(f"SELECT * FROM t WHERE lat = {lat} AND lon = {lon}")
```

## Cost/Blast-Radius Checklist

- [ ] The query goes through `bq.run_query()`, which enforces `maximum_bytes_billed` and `max_rows` — don't call `bigquery.Client` directly.
- [ ] A new tool with an unbounded result set (e.g. "list all X") has an explicit cap, following `rank_response_sites`'s `clamp_int(top_n, 1, MAX_RANKED_SITES, ...)` pattern.

## GCP Service-Account Scope Checklist

- [ ] Any new GCP API call is covered by the three scopes already granted at deploy time (`BigQuery Job User`, `BigQuery Data Viewer`, `Vertex AI User` — see `agent/README.md`'s deploy command). If not, the deploy command and PR description must say so explicitly, not assume it will "just work" in production.

## Checklist

Before committing:

- [ ] No hardcoded secret, API key, or project ID anywhere in the diff
- [ ] Every new/changed BigQuery call uses parameters for LLM-/user-influenced values
- [ ] The tool is wrapped in `@safe_tool`
- [ ] New external API keys documented with their restriction requirement

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
