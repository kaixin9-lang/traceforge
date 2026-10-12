#!/usr/bin/env bash
set -euo pipefail

# /healthz can return OK before Milvus has connected to etcd. Check a real RPC.
response=$(curl --silent --show-error --fail --max-time 5 \
  --request POST --header 'Content-Type: application/json' --data '{}' \
  http://127.0.0.1:19530/v2/vectordb/collections/list)
printf '%s\n' "$response" | grep -Eq '"code"[[:space:]]*:[[:space:]]*0[[:space:]]*[,}]'
