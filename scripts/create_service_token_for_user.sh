#!/usr/bin/env bash
set -euo pipefail

# Create a user (optional) and a service token via admin API.
# Usage: ./scripts/create_service_token_for_user.sh [-U username] [-p password] [-u user_id] [-n token_name]

ADMIN_TOKEN="${ADMIN_API_TOKEN:-$(grep -m1 '^ADMIN_API_TOKEN=' .env 2>/dev/null | cut -d'=' -f2-) }"
if [ -z "${ADMIN_TOKEN// }" ]; then
  echo "ADMIN_API_TOKEN not set (export or set in .env)" >&2
  exit 1
fi

USER_ID=""
USERNAME=""
PASSWORD="testpass"
TOKEN_NAME="auto-token-$(date +%s)"

while getopts ":U:p:u:n:" opt; do
  case ${opt} in
    U ) USERNAME=$OPTARG ;;
    p ) PASSWORD=$OPTARG ;;
    u ) USER_ID=$OPTARG ;;
    n ) TOKEN_NAME=$OPTARG ;;
    \? ) echo "Usage: $0 [-U username] [-p password] [-u user_id] [-n token_name]" >&2; exit 1 ;;
  esac
done

if [ -z "$USER_ID" ] && [ -n "$USERNAME" ]; then
  echo "Creating user $USERNAME inside minutes container..."
  USER_ID=$(docker compose exec -T minutes python3 - <<PY
from minutes.db import session_scope
from minutes.models import User
from minutes.auth import get_password_hash
username = "${USERNAME}"
password = "${PASSWORD}"
u = User(username=username, password_hash=get_password_hash(password))
with session_scope() as db:
    db.add(u)
    db.flush()
    print(u.id)
PY
)
  USER_ID=$(echo "$USER_ID" | tail -n1 | tr -d '\r')
  if [ -z "$USER_ID" ]; then
    echo "failed to create user" >&2
    exit 1
  fi
  echo "Created user id: $USER_ID"
fi

if [ -z "$USER_ID" ]; then
  echo "Creating service token without user association..."
  DATA="{\"name\": \"${TOKEN_NAME}\", \"user_id\": null}"
else
  echo "Creating service token for user $USER_ID"
  DATA="{\"name\": \"${TOKEN_NAME}\", \"user_id\": \"${USER_ID}\"}"
fi

echo "Calling admin API to create service token..."
RESPONSE=$(curl -sS -X POST http://localhost/api/service-tokens -H "X-Admin-Token: ${ADMIN_TOKEN}" -H 'Content-Type: application/json' -d "$DATA")

if [ -z "$RESPONSE" ]; then
  echo "empty response from admin API" >&2
  exit 1
fi

TOKEN=$(echo "$RESPONSE" | python3 -c 'import sys,json; obj=json.load(sys.stdin); print(obj.get("token") or "")')
TID=$(echo "$RESPONSE" | python3 -c 'import sys,json; obj=json.load(sys.stdin); print(obj.get("id") or "")')

if [ -z "$TOKEN" ]; then
  echo "failed to create token, response: $RESPONSE" >&2
  exit 1
fi

echo "Service token created:"
echo "  token: $TOKEN"
echo "  id:    $TID"
if [ -n "$USER_ID" ]; then
  echo "  user:  $USER_ID"
fi

echo "You can test with:"
echo "  curl -H \"Authorization: Bearer $TOKEN\" http://localhost/api/buckets -X POST -H 'Content-Type: application/json' -d '{\"name\":\"test-bkt\"}'"
