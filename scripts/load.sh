#!/usr/bin/env bash
#
# A4I 2026 - Challenge 1: Community Climate Resilience: Urban Heat
# Headless fallback for notebooks/c1_01_load_explore.ipynb
#
# Rebuilds the same three BigQuery tables the notebook produces, from a
# pre-staged snapshot in Cloud Storage. Use this when a Colab Enterprise
# runtime is slow, unavailable, or the upstream NOAA service is down.
#
# Run it from the repo root in Cloud Shell (no chmod needed - invoke with bash):
#     bash scripts/load.sh              # defaults to dallas
#     bash scripts/load.sh atlanta
#     bash scripts/load.sh --list       # show available cities
#
# You still want the notebook if you can run it. It explains every cleaning
# decision, and several of those explanations will save you time later. This
# script gets you the same tables without the teaching.

set -euo pipefail

BUCKET="gs://class-demo/a4i-2026/challenge-1-walkability"
DATASET="a4i_climate"
LOCATION="US"
TABLES=(heat_observations station_daily_temps tract_demographics)

# --------------------------------------------------------------------------
# Helpers
# --------------------------------------------------------------------------
bold()  { printf '\033[1m%s\033[0m\n' "$*"; }
info()  { printf '  %s\n' "$*"; }
fail()  { printf '\n\033[1mERROR:\033[0m %s\n\n%s\n\n' "$*" \
          "This script is safe to run again - every table load replaces whatever was there." >&2
          exit 1; }

# Interrupting is safe. Say so, so nobody is left wondering.
on_interrupt() {
  printf '\n\n\033[1mInterrupted.\033[0m Nothing is broken.\n'
  printf 'Every load replaces the whole table, so just run this script again:\n'
  printf '    bash scripts/load.sh %s\n\n' "${CITY:-<city>}"
  exit 130
}
trap on_interrupt INT TERM

list_cities() {
  bold "Cities available in the snapshot"
  if ! gcloud storage ls "${BUCKET}/" 2>/dev/null | sed 's|.*/\([^/]*\)/$|  \1|' | grep -v '^\s*$'; then
    fail "Could not list ${BUCKET}/. Check that you have network access."
  fi
  echo
  echo "Usage: bash scripts/load.sh <city>"
}

# --------------------------------------------------------------------------
# Arguments
# --------------------------------------------------------------------------
CITY="${1:-dallas}"

if [[ "${CITY}" == "--list" || "${CITY}" == "-l" ]]; then
  list_cities
  exit 0
fi

if [[ "${CITY}" == "--help" || "${CITY}" == "-h" ]]; then
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
  exit 0
fi

# Normalize: lowercase, and any run of characters that is not a letter or digit becomes one
# hyphen, so "Los Angeles (Central)" and "Oakland/Berkeley" become folder names rather than
# nested paths. Compare against what --list prints if a city is not found.
CITY="$(echo "${CITY}" | tr '[:upper:]' '[:lower:]' | sed 's/[^a-z0-9]\+/-/g; s/^-//; s/-$//')"
SRC="${BUCKET}/${CITY}"

# --------------------------------------------------------------------------
# Preflight
# --------------------------------------------------------------------------
bold "A4I Challenge 1 - loading data for: ${CITY}"
echo

command -v bq     >/dev/null 2>&1 || fail "'bq' not found. Run this in Cloud Shell."
command -v gcloud >/dev/null 2>&1 || fail "'gcloud' not found. Run this in Cloud Shell."

PROJECT_ID="$(gcloud config get-value project 2>/dev/null || true)"
[[ -n "${PROJECT_ID}" && "${PROJECT_ID}" != "(unset)" ]] \
  || fail "No project set. Run: gcloud config set project YOUR_PROJECT_ID"

info "Project : ${PROJECT_ID}"
info "Source  : ${SRC}"
info "Dataset : ${DATASET} (${LOCATION})"
echo

if ! gcloud storage ls "${SRC}/" >/dev/null 2>&1; then
  echo
  bold "No snapshot found for '${CITY}'."
  echo
  list_cities
  exit 1
fi

# --------------------------------------------------------------------------
# Create the dataset
# --------------------------------------------------------------------------
bold "1/3  Creating dataset"

# `bq ls -d NAME` lists the datasets in a PROJECT called NAME - it does not test
# whether one dataset exists, so it always looked "missing" and mk then failed on
# the second run. `bq show --dataset` is the correct existence test.
dataset_exists() {
  bq --project_id="${PROJECT_ID}" show --dataset --format=none \
     "${PROJECT_ID}:${DATASET}" >/dev/null 2>&1
}

if dataset_exists; then
  info "${DATASET} already exists - reusing it"

  # A dataset in the wrong region fails every load with a confusing error.
  existing_loc="$(bq --project_id="${PROJECT_ID}" --format=json show --dataset \
                    "${PROJECT_ID}:${DATASET}" 2>/dev/null \
                  | tr ',' '\n' | grep -i '"location"' | head -1 \
                  | sed 's/.*: *"\([^"]*\)".*/\1/' || true)"
  if [[ -n "${existing_loc}" && "${existing_loc^^}" != "${LOCATION^^}" ]]; then
    fail "Dataset ${DATASET} already exists in '${existing_loc}', but this script loads into
       '${LOCATION}'. BigQuery cannot load across regions. Either delete the dataset
       (bq rm -r -d ${DATASET}) or edit LOCATION at the top of this script to match."
  fi
else
  # Belt and braces: if the check above ever misfires, or two teammates run this
  # at the same moment, an "already exists" error is fine. Anything else is not.
  if mk_out="$(bq --project_id="${PROJECT_ID}" --location="${LOCATION}" \
                  mk --dataset "${PROJECT_ID}:${DATASET}" 2>&1)"; then
    info "created ${DATASET}"
  elif grep -qi "already exists" <<<"${mk_out}"; then
    info "${DATASET} already exists - reusing it"
  else
    fail "Could not create dataset ${DATASET}:
       ${mk_out}"
  fi
fi
echo

# --------------------------------------------------------------------------
# Load each table
# --------------------------------------------------------------------------
# Every load below uses --replace, so re-running this script from scratch is always
# safe: each table is fully overwritten, never appended to.
bold "2/3  Loading tables"
for table in "${TABLES[@]}"; do
  # BigQuery's EXPORT DATA may shard into several parts, so we load the folder.
  uri="${SRC}/${table}/*.parquet"

  if ! gcloud storage ls "${SRC}/${table}/" >/dev/null 2>&1; then
    fail "Missing ${SRC}/${table}/. The snapshot for '${CITY}' looks incomplete - tell a coach."
  fi

  info "loading ${table}..."
  bq --project_id="${PROJECT_ID}" --location="${LOCATION}" load \
     --source_format=PARQUET \
     --replace \
     "${DATASET}.${table}" \
     "${uri}" >/dev/null

  info "  done"
done
echo

# --------------------------------------------------------------------------
# Verify - never trust a load you did not check
# --------------------------------------------------------------------------
bold "3/3  Verifying"
FAILED=0
for table in "${TABLES[@]}"; do
  rows="$(bq --project_id="${PROJECT_ID}" --location="${LOCATION}" \
            query --use_legacy_sql=false --format=csv \
            "SELECT COUNT(*) FROM \`${PROJECT_ID}.${DATASET}.${table}\`" \
          | tail -n 1)"

  if [[ "${rows}" == "0" ]]; then
    printf '  %-22s %s\n' "${table}" "0 rows  <-- EMPTY"
    FAILED=1
  else
    printf '  %-22s %s rows\n' "${table}" "${rows}"
  fi
done
echo

# Sanity check the one number that matters: intra-city temperature spread.
spread="$(bq --project_id="${PROJECT_ID}" --location="${LOCATION}" \
            query --use_legacy_sql=false --format=csv \
            "SELECT ROUND(MAX(temp_f) - MIN(temp_f), 1)
             FROM \`${PROJECT_ID}.${DATASET}.heat_observations\`" \
          | tail -n 1 || echo "")"

if [[ -n "${spread}" ]]; then
  info "Intra-city temperature spread: ${spread} F"
  info "(That spread is the whole challenge. If it were near zero,"
  info " there would be nothing for a model to learn.)"
fi
echo

if [[ "${FAILED}" -eq 1 ]]; then
  fail "One or more tables loaded empty. Tell a coach before you build on this."
fi

bold "Ready."
echo
echo "  Your tables are in ${PROJECT_ID}.${DATASET}"
echo "  Safe to re-run at any time - each load replaces the whole table."
echo
echo "  Next: train your BigQuery ML model, and have your agent call it."
echo "  See the README for what to predict and why."
echo
