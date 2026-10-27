---
name: monitoring
description: 'What logging and the per-request tool trace actually show today, and how to read them when debugging a live or local run. Use when: debugging a failed request, reading Cloud Run logs, or deciding whether to add new observability. Trigger phrases: "check the logs", "why did this request fail", "read the tool trace", "is there a metric for this".'
---

# Monitoring

## When to Use This Skill

When debugging a failed or slow request locally or on Cloud Run, or before adding new
logging/metrics/tracing (to avoid assuming infrastructure that doesn't exist).

## Prerequisites

Read `.claude/rules/observability.md` first — it is the authoritative list of what exists
and what doesn't; this skill is the practical "how do I actually look" companion.

## Reading Local Logs

`logging.basicConfig(level=INFO, ...)` (`agent.py:13`) prints to stdout with
`%(asctime)s %(name)s %(levelname)s %(message)s`. Run `./run.sh` in a foreground terminal
and watch stdout — there is no separate log file.

## Reading the Per-Request Tool Trace

Every `/api/chat` response includes a `steps` array (`service.py:101`): each entry is
`{tool, args, ms, error?}`, built by `callbacks.py`'s `before_tool`/`after_tool`. The UI
renders these as cards. To inspect it directly:

```bash
curl -s -X POST http://127.0.0.1:8080/api/chat \
  -H 'content-type: application/json' \
  -d '{"question": "How often does it hit 100F?"}' | python3 -m json.tool
```

Look at `steps` for which tools ran, in what order, with what args, and how long each took.
`cards` carries the full tool result (including `status`) for each step. This is the single
best debugging signal available today — there is no separate metrics dashboard.

## Reading Cloud Run Logs

Access logs are disabled (`agent/Dockerfile:12`, `--no-access-log`), so only application
`logger.*` calls and uncaught-exception logs (`api.py:33`'s `logger.exception("request failed")`)
reach Cloud Logging. Filter by `resource.type="cloud_run_revision"` and the service name
`heat-planner` in the GCP console; there is no structured field to filter by request ID,
since none is propagated (see `.claude/rules/observability.md`).

## Diagnosing a 503

A 503 from `/api/chat` means `service.AgentError` was raised — check the log line right
before it (`service.py:96`, `logger.exception("agent run failed")`) for the real cause,
commonly a rate-limited Gemini call (`service.py:97`, detected via `"ResourceExhausted"` or
`"429"` in the exception) or a BigQuery `ToolError` surfaced through a tool result rather
than a raw exception (check `cards` in the response first).

## Before Adding New Observability

Confirm with `.claude/rules/observability.md` that what you want to add doesn't already
exist under a different name — there is currently no metrics or tracing layer at all, so
"add a metric for X" is new work, not wiring into an existing exporter.

## Checklist

- [ ] Checked the `steps`/`cards` response fields before assuming a tool silently failed
- [ ] Checked server-side logs (`logger.exception` call sites) for the real exception, not just the generic client-facing error
- [ ] Did not assume a correlation ID, metric, or trace exists that isn't documented in `.claude/rules/observability.md`

---

## Version History

| Version | Date | Author | Changes |
|---|---|---|---|
| 1.0.0 | 2026-10-27 | Claude (bootstrap v3.4.1) | Initial creation via orange-lens-ai-bootstrapper |
