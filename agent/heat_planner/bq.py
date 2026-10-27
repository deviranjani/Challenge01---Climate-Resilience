"""Thin BigQuery layer: one place that owns the client, cost limits and logging.

Tools never build SQL from model-generated text. They pass fixed SQL plus query
parameters here, so the LLM cannot inject SQL.
"""

import functools
import logging
from typing import Any, Sequence

from google.cloud import bigquery

from .config import Settings, load_settings

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """A failure we can explain to the user (bad input, no data, BigQuery refused)."""


@functools.lru_cache(maxsize=1)
def _client(project_id: str, location: str) -> bigquery.Client:
    return bigquery.Client(project=project_id or None, location=location)


def table(settings: Settings, name: str) -> str:
    """Fully qualified, backtick-quoted table or model reference."""
    project = settings.project_id or _client("", settings.location).project
    return f"`{project}.{settings.dataset}.{name}`"


def run_query(
    sql: str,
    params: Sequence[bigquery.ScalarQueryParameter] = (),
    settings: Settings | None = None,
    max_rows: int | None = None,
) -> list[dict[str, Any]]:
    """Run a read-only parameterised query and return rows as dicts."""
    settings = settings or load_settings()
    config = bigquery.QueryJobConfig(
        query_parameters=list(params),
        maximum_bytes_billed=settings.max_bytes_billed,
    )
    try:
        job = _client(settings.project_id, settings.location).query(sql, job_config=config)
        rows = job.result(max_results=max_rows or settings.max_rows)
        result = [dict(row.items()) for row in rows]
    except Exception as exc:  # google.api_core errors vary; normalise them
        logger.exception("BigQuery query failed")
        raise ToolError(f"BigQuery request failed: {type(exc).__name__}: {exc}") from exc
    logger.info("BigQuery returned %d rows", len(result))
    return result
