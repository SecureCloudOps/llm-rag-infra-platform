#!/usr/bin/env bash

set -euo pipefail

API_URL="${RAG_API_URL:-http://127.0.0.1:8000}"
QDRANT_URL="${QDRANT_HTTP_URL:-http://127.0.0.1:6333}"
SAMPLE_FILE="${SMOKE_TEST_FILE:-services/rag-api/sample.txt}"
MAX_ATTEMPTS="${SMOKE_TEST_MAX_ATTEMPTS:-30}"

if [[ ! -f "${SAMPLE_FILE}" ]]; then
  echo "Smoke-test file not found: ${SAMPLE_FILE}" >&2
  exit 1
fi

wait_for_endpoint() {
  local name="$1"
  local url="$2"
  local attempt

  for ((attempt = 1; attempt <= MAX_ATTEMPTS; attempt++)); do
    if curl --fail --silent --output /dev/null "${url}"; then
      echo "${name} is ready"
      return 0
    fi
    sleep 1
  done

  echo "${name} did not become ready after ${MAX_ATTEMPTS} attempts" >&2
  return 1
}

assert_json() {
  local expression="$1"
  local description="$2"

  RESPONSE_JSON="${response}" python3 -c \
    "import json, os; data = json.loads(os.environ['RESPONSE_JSON']); assert ${expression}, '${description}'"
  echo "PASS: ${description}"
}

wait_for_endpoint "Qdrant" "${QDRANT_URL}/healthz"
wait_for_endpoint "RAG API" "${API_URL}/health"

response="$(curl --fail --silent --show-error \
  --form "file=@${SAMPLE_FILE};type=text/plain" \
  "${API_URL}/documents/upload")"
assert_json \
  "data['filename'] == '$(basename "${SAMPLE_FILE}")' and data['embedding_count'] >= 1" \
  "document upload generated embeddings"

response="$(curl --fail --silent --show-error "${API_URL}/documents")"
assert_json \
  "data['total_documents'] >= 1 and data['total_chunks'] >= 1" \
  "Qdrant reports stored documents and chunks"

response="$(curl --fail --silent --show-error \
  --header "Content-Type: application/json" \
  --data '{"query":"What is vLLM used for?","top_k":3}' \
  "${API_URL}/search")"
assert_json \
  "len(data['results']) >= 1 and 'vLLM' in data['results'][0]['chunk_text']" \
  "semantic search retrieved the expected content"

response="$(curl --fail --silent --show-error \
  --header "Content-Type: application/json" \
  --data '{"question":"What is vLLM used for?","top_k":3}' \
  "${API_URL}/ask")"
assert_json \
  "data['retrieved_chunks'] >= 1 and len(data['sources']) >= 1 and data['answer']" \
  "RAG answer includes retrieved sources"

metrics="$(curl --fail --silent --show-error "${API_URL}/metrics")"
for metric in \
  rag_api_http_requests_total \
  rag_api_ask_latency_seconds \
  rag_api_qdrant_retrieval_latency_seconds; do
  if ! grep --quiet "^${metric}" <<<"${metrics}"; then
    echo "Expected metric not found: ${metric}" >&2
    exit 1
  fi
  echo "PASS: metric ${metric} is exposed"
done

echo "Compose smoke test passed"
