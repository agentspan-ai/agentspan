# Agentspan Docker Compose Deployment

This directory contains a turn-key Docker Compose stack for running Agentspan server + PostgreSQL locally or on a single VM.

## Path

`deployment/docker-compose`

## Prerequisites

```bash
docker --version
docker compose version
```

## Quick Start

```bash
cd deployment/docker-compose
cp .env.example .env
# Generate and set the encryption master key
# openssl rand -base64 32
# Set at least one provider key in .env (for example OPENAI_API_KEY)
docker compose up -d
```

Open:
- UI: `http://localhost:6767`
- Health: `http://localhost:6767/actuator/health`

If `6767` is already in use, set a different host port in `.env`:

```bash
AGENTSPAN_PORT=16767
```

## Validate

```bash
docker compose config
docker compose ps
docker compose logs --tail=200 agentspan
curl -fsS http://localhost:6767/actuator/health
```

## Stop / Cleanup

```bash
docker compose down
docker compose down -v   # removes postgres volume/data
```

## Notes

- All runtime values are environment-driven; no secrets are hardcoded in `compose.yaml`.
- `depends_on` waits for Postgres health before starting Agentspan.
- `host.docker.internal` is mapped so the container can reach host services (for example local Ollama).
- If you change `POSTGRES_USER` / `POSTGRES_PASSWORD`, keep datasource credentials aligned.
- For production HA/scaling, use Kubernetes manifests or the Helm chart under `deployment/helm/agentspan`.
