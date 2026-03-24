#!/usr/bin/env sh
set -eu

: "${INFISICAL_TOKEN:?INFISICAL_TOKEN is required}"
: "${INFISICAL_PROJECT_ID:?INFISICAL_PROJECT_ID is required}"

export INFISICAL_API_URL="${INFISICAL_API_URL:-http://host.docker.internal:8085/api}"
export INFISICAL_DISABLE_UPDATE_CHECK="${INFISICAL_DISABLE_UPDATE_CHECK:-true}"

set -- infisical run \
  --silent \
  --token="${INFISICAL_TOKEN}" \
  --projectId="${INFISICAL_PROJECT_ID}" \
  --env="${INFISICAL_ENV:-dev}" \
  --path="${INFISICAL_PATH:-/}" \
  -- /bin/sh -c '
    if [ -z "${SLACK_CHANNEL_ID:-}" ]; then
      mapped_channel_id="$(printenv team-devops-internal-slack-id 2>/dev/null || true)"
      if [ -n "$mapped_channel_id" ]; then
        export SLACK_CHANNEL_ID="$mapped_channel_id"
      fi
    fi
    exec uv run daily_status.py "$@"
  ' sh \
  -- \
  "$@"

exec "$@"
