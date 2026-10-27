#!/usr/bin/env bash
# Build the BigQuery side of area names: which ZIP code area (and city) each census tract sits in.
#
#   tract_areas   every census tract -> the ZIP code area and city it sits in. Built in BigQuery from the US Census ZIP
#                 boundaries in bigquery-public-data (US Government data, public domain), by testing which ZIP polygon
#                 holds each tract's centre point.
#
# Neighbourhood names ("Oak Cliff") are NOT stored here: the app asks Google Maps live for them (reverse geocoding and
# Places search) and keeps them in memory only, which is what Google's terms allow. OpenStreetMap is deliberately not
# used: it is ODbL, which this challenge's data rules exclude.
#
# Safe to re-run: both tables are replaced. Needs `bq` and a project: gcloud config set project YOUR_PROJECT_ID
#
#   bash scripts/build_areas.sh
set -euo pipefail
cd "$(dirname "$0")/.."

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
DATASET="${DATASET:-a4i_climate}"
[ -n "$PROJECT" ] || { echo "No project set. Run: gcloud config set project YOUR_PROJECT_ID" >&2; exit 1; }

echo "==> tract_areas in ${PROJECT}.${DATASET}"
bq --project_id="$PROJECT" query --use_legacy_sql=false --nouse_cache >/dev/null <<SQL
CREATE OR REPLACE TABLE \`${PROJECT}.${DATASET}.tract_areas\` AS
SELECT t.geo_id,
       z.zip_code,
       REGEXP_REPLACE(z.city, r' city\$', '') AS city
FROM \`${PROJECT}.${DATASET}.tract_demographics\` AS t
JOIN \`bigquery-public-data.geo_us_boundaries.zip_codes\` AS z
  ON ST_CONTAINS(z.zip_code_geom, ST_GEOGPOINT(t.tract_lon, t.tract_lat))
SQL

bq --project_id="$PROJECT" query --use_legacy_sql=false --format=pretty \
  "SELECT COUNT(*) AS tracts_mapped, COUNT(DISTINCT zip_code) AS zip_areas FROM \`${PROJECT}.${DATASET}.tract_areas\`"
