#!/bin/bash
# imapbox hook, used with: --hook newmail,"./hook-addToElasticSearch.sh"
#
# Indexes the metadata of a newly backed up email into Elasticsearch,
# based on the curl example in the imapbox README ("Elasticsearch" section).
#
# Reads the event JSON payload from stdin (one JSON array item per newmail),
# extracts directory + metadata, and PUTs it into Elasticsearch.
#
# Override the Elasticsearch endpoint with the ES_URL environment variable.


ES_URL="${ES_URL:-http://elasticsearch:9200}"

# consume the JSON payload from stdin
json_data=$(cat -)
# example: getting single value name=$(echo "$json_data" | jq -r '.date')

# extract the mail directory from the event item
# (pure shell: mail folder names never contain a double quote, so grep/cut is safe)
DIR="$(printf '%s' "$json_data" | grep -o '"directory"[[:space:]]*:[[:space:]]*"[^"]*"' | head -n1 | cut -d '"' -f4)"

if [ -z "${DIR}" ]; then
    echo "hook-addToElasticSearch.sh: no directory in event payload" >&2
    exit 1
fi

METADATA="${DIR}/metadata.json"
if [ ! -f "${METADATA}" ]; then
    exit 0
fi

ID="$(basename "${DIR}")"

# make sure the index exists (idempotent PUT)
curl -s -o /dev/null -XPUT "${ES_URL}/imapbox" || true

# ES 8+/9 dropped mapping types; use _doc and an explicit content-type
curl -s --retry 5 --retry-delay 2 -XPUT -H "Content-Type: application/json" "${ES_URL}/imapbox/_doc/${ID}" --data-binary "@${METADATA}" || true