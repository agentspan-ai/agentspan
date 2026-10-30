#!/bin/sh
# Wait for the agentspan server sidecar before starting the poller — otherwise
# the SDK's auto-start kicks in and tries to download the CLI inside the
# container. /health returns non-500 once the server is up.
set -e

BASE="${AGENTSPAN_SERVER_URL:-http://localhost:6767/api}"
HEALTH="${BASE%/api}/health"

echo "waiting for agentspan server at ${HEALTH}..."
i=0
until python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('${HEALTH}', timeout=2).status < 500 else 1)" 2>/dev/null; do
  i=$((i+1))
  if [ "$i" -gt 120 ]; then
    echo "agentspan server not ready after 120 attempts" >&2
    exit 1
  fi
  sleep 2
done
echo "agentspan server is ready"

exec python -m oncall_agent.main "$@"
