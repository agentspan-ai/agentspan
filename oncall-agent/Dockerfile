# On-call triage poller. Build from the REPO ROOT (needs sdk/python):
#   docker build -f oncall-agent/Dockerfile -t oncall-agent:latest .
# The agentspan server is NOT in this image — it runs as a sidecar
# (agentspan/server:latest), see deploy/k8s.yaml.
FROM python:3.11-slim

WORKDIR /app

# Conductor Agent SDK from this repo, then the poller's own deps.
COPY sdk/python /opt/conductor-agent-sdk
RUN pip install --no-cache-dir /opt/conductor-agent-sdk

COPY oncall-agent/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oncall-agent/src ./src
COPY oncall-agent/docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

ENV PYTHONPATH=/app/src \
    PYTHONUNBUFFERED=1 \
    ONCALL_STATE_FILE=/state/oncall_state.json

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["--loop"]
