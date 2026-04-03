# Agentspan Deployment Guide

This guide covers every deployment path from local development to production-grade Kubernetes. Each section shows the **complete, working configuration** — not just variable names, but exactly where to put them and what values to use.

---

## Table of Contents

1. [Architecture](#architecture)
2. [Local Development](#1-local-development)
3. [Single Server — Docker](#2-single-server--docker)
4. [Production — Docker Compose](#3-production--docker-compose)
5. [Production — Kubernetes](#4-production--kubernetes)
6. [Production — Helm](#5-production--helm)
7. [Cloud-Specific Guides](#6-cloud-specific-guides)
8. [Managed Database](#7-managed-database)
9. [TLS / HTTPS](#8-tls--https)
10. [Authentication](#9-authentication)
11. [Observability](#10-observability)
12. [Backup & Restore](#11-backup--restore)
13. [Production Checklist](#12-production-checklist)
14. [Configuration Reference](#13-configuration-reference)

---

## Architecture

```
                     ┌──────────────────────────────────────────┐
                     │         Kubernetes Cluster               │
                     │         namespace: agentspan             │
Internet ──► DNS ──► LoadBalancer ──► Ingress (nginx) ──► agentspan-server:6767
                     │                                          │
                     │   agentspan-server (3 replicas, HPA 3–10)│
                     │   ┌──────────────────────────────────┐   │
                     │   │  Spring Boot (port 6767)         │   │
                     │   │  /api/**   → REST API            │   │
                     │   │  /**       → React UI (static)   │   │
                     │   └──────────────────────────────────┘   │
                     │           │                               │
                     │   agentspan-postgres (StatefulSet)        │
                     └──────────────────────────────────────────┘
```

| Component | Image | Default replicas |
|---|---|---|
| Server + UI | `agentspan/server:latest` | 3 (auto-scales to 10) |
| PostgreSQL | `postgres:16-alpine` | 1 (StatefulSet + PVC) |

The server image contains both the REST API and the React UI — no separate frontend container needed.

---

## 1. Local Development

Zero config. Uses SQLite. Data persists in `./agent-runtime.db` in the working directory.

```bash
# Install the CLI
curl -fsSL https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.sh | sh

# Set at least one LLM API key
export OPENAI_API_KEY=sk-...

# Start the server
agentspan server start

# Open the UI
open http://localhost:6767
```

**What gets created:**
- `~/.agentspan/` — server JAR and config
- `./agent-runtime.db` — SQLite database (in your working directory)

**To reset:** `rm agent-runtime.db`

---

## 2. Single Server — Docker

Best for: staging environments, demos, single-VM deployments without Postgres.

### Standalone (SQLite)

```bash
docker run -d \
  --name agentspan \
  -p 6767:6767 \
  -e OPENAI_API_KEY=sk-... \
  -v agentspan_data:/data \
  agentspan/server:latest
```

### With external PostgreSQL

```bash
docker run -d \
  --name agentspan \
  -p 6767:6767 \
  -e SPRING_PROFILES_ACTIVE=postgres \
  -e SPRING_DATASOURCE_URL=jdbc:postgresql://your-db-host:5432/agentspan \
  -e SPRING_DATASOURCE_USERNAME=agentspan \
  -e SPRING_DATASOURCE_PASSWORD=your-password \
  -e OPENAI_API_KEY=sk-... \
  agentspan/server:latest
```

**Check it's running:**
```bash
curl http://localhost:6767/health
# {"healthy":true}
```

---

## 3. Production — Docker Compose

Best for: single VM production deployments. Includes PostgreSQL with persistent storage.

### Setup

```bash
cd deployment/docker-compose
cp .env.example .env
```

Edit `.env` — at minimum set these values:

```bash
# .env

# ── Database ─────────────────────────────────────────────
POSTGRES_PASSWORD=your-strong-password-here     # ← change this

# ── LLM provider (set at least one) ─────────────────────
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=...

# ── Port (default: 6767) ─────────────────────────────────
AGENTSPAN_PORT=6767
```

### Start

```bash
docker compose up -d

# Check logs
docker compose logs -f agentspan

# Verify health
curl http://localhost:6767/health
```

### Upgrade

```bash
docker compose pull
docker compose up -d
```

### Stop / Remove

```bash
docker compose down          # stop containers, keep data
docker compose down -v       # stop containers + delete database (irreversible)
```

**Data persists in the `postgres_data` Docker volume.** Back this up before upgrading.

---

## 4. Production — Kubernetes

Best for: high availability, auto-scaling, managed cloud deployments.

### Prerequisites

| Tool | Install |
|---|---|
| `kubectl` | [kubernetes.io/docs](https://kubernetes.io/docs/tasks/tools/) |
| Kubernetes cluster | EKS, GKE, AKS, k3s, or any CNCF-conformant cluster |
| ingress-nginx | See below |
| cert-manager | See below (recommended for TLS) |
| metrics-server | See below (required for HPA) |

```bash
# ingress-nginx
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/cloud/deploy.yaml
kubectl wait --namespace ingress-nginx --for=condition=ready pod --selector=app.kubernetes.io/component=controller --timeout=120s

# cert-manager (for automatic TLS)
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

# metrics-server (for HPA auto-scaling)
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### Step 1 — Configure secrets

Edit `deployment/k8s/secret.yaml`. **Never commit this file with real values.**

```yaml
# deployment/k8s/secret.yaml
apiVersion: v1
kind: Secret
metadata:
  name: agentspan-secrets
  namespace: agentspan
type: Opaque
stringData:
  POSTGRES_PASSWORD: "your-strong-password"    # ← required, change this
  OPENAI_API_KEY: "sk-..."                     # ← at least one LLM key
  # ANTHROPIC_API_KEY: "sk-ant-..."
  # GEMINI_API_KEY: "..."
```

> **Production tip:** Use [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets), [External Secrets Operator](https://external-secrets.io/), or your cloud's secrets manager (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) instead of committing plaintext secrets.

### Step 2 — Set your domain

Edit `deployment/k8s/ingress.yaml`, replace `agentspan.example.com`:

```yaml
rules:
  - host: agentspan.yourdomain.com    # ← your domain
```

### Step 3 — Deploy

```bash
# One-shot deploy (build image, push, apply all manifests)
./deployment/deploy.sh

# With a custom image tag (private registry)
./deployment/deploy.sh --image registry.example.com/agentspan/server:v1.2.0

# Skip Docker build (image already exists)
./deployment/deploy.sh --skip-build

# Target a specific kubectl context
./deployment/deploy.sh --context my-cluster-context
```

Or deploy step-by-step:

```bash
kubectl apply -f deployment/k8s/namespace.yaml
kubectl apply -f deployment/k8s/configmap.yaml
kubectl apply -f deployment/k8s/secret.yaml
kubectl apply -f deployment/k8s/postgres.yaml
kubectl rollout status statefulset/agentspan-postgres -n agentspan
kubectl apply -f deployment/k8s/server.yaml
kubectl rollout status deployment/agentspan-server -n agentspan
kubectl apply -f deployment/k8s/ingress.yaml
kubectl apply -f deployment/k8s/hpa.yaml
```

### Step 4 — Point DNS

```bash
# Get the ingress load balancer IP
kubectl get ingress -n agentspan

# Create a DNS A record:
#   agentspan.yourdomain.com → <EXTERNAL-IP>
```

### Useful commands

```bash
# Check pod status
kubectl get pods -n agentspan

# Tail server logs
kubectl logs -f deployment/agentspan-server -n agentspan

# Restart to pick up a new image
kubectl rollout restart deployment/agentspan-server -n agentspan

# Port-forward for local debugging (bypasses ingress)
kubectl port-forward svc/agentspan-server 6767:6767 -n agentspan

# Scale manually
kubectl scale deployment/agentspan-server --replicas=5 -n agentspan

# Tear down everything
kubectl delete namespace agentspan
```

### ConfigMap reference

These go in `deployment/k8s/configmap.yaml` — safe to commit, no sensitive values:

| Key | Default | Description |
|---|---|---|
| `SPRING_PROFILES_ACTIVE` | `postgres` | Must be `postgres` for K8s |
| `POSTGRES_HOST` | `agentspan-postgres` | PostgreSQL service name |
| `POSTGRES_DB` | `agentspan` | Database name |
| `JAVA_OPTS` | `-Xms512m -Xmx1536m ...` | JVM heap — increase for large deployments |
| `LOGGING_LEVEL_ROOT` | `WARN` | Set to `INFO` for more verbose logs |
| `OLLAMA_HOST` | _(unset)_ | Set if using local Ollama models |

---

## 5. Production — Helm

Best for: GitOps workflows, templated multi-environment deployments.

```bash
# Install
helm install agentspan ./deployment/helm/agentspan \
  --namespace agentspan \
  --create-namespace \
  --set postgres.password=your-strong-password \
  --set llm.openaiApiKey=sk-...

# Upgrade
helm upgrade agentspan ./deployment/helm/agentspan \
  --namespace agentspan \
  --set image.tag=0.0.15

# Uninstall
helm uninstall agentspan --namespace agentspan
```

See `deployment/helm/README.md` for all values.

---

## 6. Cloud-Specific Guides

### AWS EKS

```bash
# Use gp3 storage for PostgreSQL PVC
# In deployment/k8s/postgres.yaml, set:
storageClassName: gp3

# Use AWS Load Balancer Controller instead of nginx (optional)
kubectl apply -f https://github.com/kubernetes-sigs/aws-load-balancer-controller/...

# For managed PostgreSQL, use RDS — see section 7
```

### GCP GKE

```bash
# Default standard storage class works as-is
# No changes needed to postgres.yaml

# For managed PostgreSQL, use Cloud SQL — see section 7
```

### Azure AKS

```bash
# Use managed-premium storage for PostgreSQL PVC
# In deployment/k8s/postgres.yaml, set:
storageClassName: managed-premium

# For managed PostgreSQL, use Azure Database for PostgreSQL — see section 7
```

---

## 7. Managed Database

For production, use a managed PostgreSQL service instead of the bundled StatefulSet. This gives you automated backups, failover, and point-in-time recovery.

| Cloud | Service |
|---|---|
| AWS | RDS for PostgreSQL |
| GCP | Cloud SQL for PostgreSQL |
| Azure | Azure Database for PostgreSQL |
| Self-hosted | [CloudNativePG](https://cloudnative-pg.io/) |

### How to connect

**Docker Compose** — update `.env`:
```bash
POSTGRES_HOST=your-rds-endpoint.rds.amazonaws.com
POSTGRES_USER=agentspan
POSTGRES_PASSWORD=your-password
POSTGRES_DB=agentspan
```

**Kubernetes** — update `deployment/k8s/secret.yaml`:
```yaml
stringData:
  POSTGRES_PASSWORD: "your-password"
```

And `deployment/k8s/configmap.yaml`:
```yaml
data:
  POSTGRES_HOST: "your-rds-endpoint.rds.amazonaws.com"
  POSTGRES_DB: "agentspan"
```

**CLI (local)** — set env vars before starting:
```bash
export SPRING_PROFILES_ACTIVE=postgres
export SPRING_DATASOURCE_URL=jdbc:postgresql://your-host:5432/agentspan
export SPRING_DATASOURCE_USERNAME=agentspan
export SPRING_DATASOURCE_PASSWORD=your-password
agentspan server start
```

---

## 8. TLS / HTTPS

### cert-manager (recommended for Kubernetes)

**Step 1** — Create a ClusterIssuer:

```yaml
# deployment/k8s/cluster-issuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@yourdomain.com           # ← your email for cert expiry alerts
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

```bash
kubectl apply -f deployment/k8s/cluster-issuer.yaml
```

**Step 2** — Enable TLS in `deployment/k8s/ingress.yaml`:

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"   # ← uncomment
spec:
  tls:
    - hosts:
        - agentspan.yourdomain.com
      secretName: agentspan-tls                           # ← uncomment
```

### Reverse proxy (Docker / single server)

Put nginx or Caddy in front of the server:

```nginx
# /etc/nginx/sites-available/agentspan
server {
    listen 443 ssl;
    server_name agentspan.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/agentspan.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agentspan.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:6767;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE (streaming) support
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 3600s;
    }
}
```

---

## 9. Authentication

Authentication is enabled by default. The server generates a random admin password on first start — check the logs:

```bash
# CLI
agentspan server logs | grep "Admin password"

# Docker
docker logs agentspan | grep "Admin password"

# Kubernetes
kubectl logs deployment/agentspan-server -n agentspan | grep "Admin password"
```

### Set a fixed admin password

**Docker Compose** — add to `.env`:
```bash
AGENTSPAN_AUTH_ADMIN_PASSWORD=your-secure-password
```

**Kubernetes** — add to `deployment/k8s/secret.yaml`:
```yaml
stringData:
  AGENTSPAN_AUTH_ADMIN_PASSWORD: "your-secure-password"
```

**CLI** — set before starting:
```bash
export AGENTSPAN_AUTH_ADMIN_PASSWORD=your-secure-password
agentspan server start
```

### API keys

```bash
# Create an API key via CLI
agentspan login                         # log in with admin password
agentspan credential store MY_API_KEY value   # store a credential

# Or use the REST API
curl -X POST http://localhost:6767/api/auth/token \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"your-password"}'
```

### Disable auth (development only)

```bash
AGENTSPAN_AUTH_ENABLED=false agentspan server start
```

---

## 10. Observability

### Prometheus metrics

Metrics are exposed at `/actuator/prometheus` on the server:

```bash
curl http://localhost:6767/actuator/prometheus
```

**Prometheus scrape config:**
```yaml
# prometheus.yml
scrape_configs:
  - job_name: agentspan
    static_configs:
      - targets: ['agentspan:6767']
    metrics_path: /actuator/prometheus
```

**Key metrics:**
| Metric | Description |
|---|---|
| `agentspan_agent_executions_total` | Total agent runs |
| `agentspan_agent_duration_seconds` | Execution duration histogram |
| `agentspan_tool_calls_total` | Tool invocations |
| `agentspan_guardrail_failures_total` | Guardrail failure count |
| `jvm_memory_used_bytes` | JVM memory usage |

### Health endpoints

```bash
curl http://localhost:6767/actuator/health           # overall health
curl http://localhost:6767/actuator/health/liveness  # liveness probe
curl http://localhost:6767/actuator/health/readiness # readiness probe
```

### OpenTelemetry (opt-in)

Enable distributed tracing by setting these env vars:

```bash
MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED=true
MANAGEMENT_OTLP_METRICS_EXPORT_URL=http://your-otel-collector:4318/v1/metrics
```

### Log levels

```bash
# More verbose (troubleshooting)
LOGGING_LEVEL_ROOT=INFO
LOGGING_LEVEL_DEV_AGENTSPAN=DEBUG

# Quiet (production default)
LOGGING_LEVEL_ROOT=WARN
LOGGING_LEVEL_DEV_AGENTSPAN=INFO
```

---

## 11. Backup & Restore

### PostgreSQL (Docker Compose)

```bash
# Backup
docker exec agentspan-postgres-1 pg_dump -U agentspan agentspan > backup_$(date +%Y%m%d).sql

# Restore
docker exec -i agentspan-postgres-1 psql -U agentspan agentspan < backup_20260101.sql
```

### PostgreSQL (Kubernetes)

```bash
# Backup
kubectl exec -n agentspan statefulset/agentspan-postgres -- \
  pg_dump -U agentspan agentspan > backup_$(date +%Y%m%d).sql

# Restore
kubectl exec -i -n agentspan statefulset/agentspan-postgres -- \
  psql -U agentspan agentspan < backup_20260101.sql
```

### SQLite (local dev)

```bash
# Backup — just copy the file
cp agent-runtime.db agent-runtime.db.backup

# Restore
cp agent-runtime.db.backup agent-runtime.db
```

**Automate backups** — run the backup command via cron or a Kubernetes CronJob before every upgrade.

---

## 12. Production Checklist

Before going live, verify each item:

### Security
- [ ] Change default PostgreSQL password (`POSTGRES_PASSWORD=changeme` → strong password)
- [ ] Set a fixed admin password (`AGENTSPAN_AUTH_ADMIN_PASSWORD`)
- [ ] Enable TLS / HTTPS (cert-manager or reverse proxy)
- [ ] Rotate any API keys that were committed or shared
- [ ] Use a secrets manager for K8s secrets (Sealed Secrets / External Secrets)
- [ ] Confirm `secret.yaml` is in `.gitignore` — never commit real secrets

### Database
- [ ] Use PostgreSQL in production (not SQLite)
- [ ] Use a managed database service (RDS, Cloud SQL) for HA + automated backups
- [ ] Schedule automated backups
- [ ] Test restore from backup before go-live

### Reliability
- [ ] At least 2 replicas running (`kubectl get pods -n agentspan`)
- [ ] HPA configured (`kubectl get hpa -n agentspan`)
- [ ] PodDisruptionBudget in place (included in `server.yaml`)
- [ ] Health checks passing (`curl /actuator/health`)
- [ ] Readiness/liveness probes responding

### Observability
- [ ] Prometheus scraping `/actuator/prometheus`
- [ ] Log aggregation configured (CloudWatch, Datadog, Loki, etc.)
- [ ] Alerting on error rate and latency

### Operations
- [ ] Runbook written for: restart, scale up, rollback
- [ ] Backup tested end-to-end (backup → restore → verify)
- [ ] On-call rotation knows the server URL and admin credentials

---

## 13. Configuration Reference

Complete list of environment variables. Column **"Where to set"** shows the exact file or command for each deployment method.

### Core

| Variable | Default | Description | Where to set |
|---|---|---|---|
| `SERVER_PORT` | `6767` | HTTP port | `.env` / `-e` flag / K8s ConfigMap |
| `SPRING_PROFILES_ACTIVE` | `default` (SQLite) | Set to `postgres` for PostgreSQL | `.env` / ConfigMap |

### Database — SQLite (default, dev only)

| Variable | Default | Description | Where to set |
|---|---|---|---|
| `SPRING_DATASOURCE_URL` | `jdbc:sqlite:agent-runtime.db` | SQLite file path | `.env` / `-e` flag |

### Database — PostgreSQL

| Variable | Default | Description | Where to set |
|---|---|---|---|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://localhost:5432/agentspan` | Full JDBC URL | `.env` / K8s ConfigMap |
| `SPRING_DATASOURCE_USERNAME` | `postgres` | DB user | `.env` / K8s ConfigMap |
| `SPRING_DATASOURCE_PASSWORD` | `postgres` | DB password | `.env` / **K8s Secret** |
| `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` | `8` | Connection pool size | ConfigMap |

### Authentication

| Variable | Default | Description | Where to set |
|---|---|---|---|
| `AGENTSPAN_AUTH_ENABLED` | `true` | Enable/disable auth | `.env` / ConfigMap |
| `AGENTSPAN_AUTH_ADMIN_PASSWORD` | _(random)_ | Admin password | `.env` / **K8s Secret** |

### LLM Providers — set at least one

| Variable | Provider | Where to set |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI | `.env` / **K8s Secret** |
| `ANTHROPIC_API_KEY` | Anthropic | `.env` / **K8s Secret** |
| `GEMINI_API_KEY` | Google Gemini | `.env` / **K8s Secret** |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI | `.env` / **K8s Secret** |
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI | `.env` / **K8s Secret** |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI | `.env` / K8s ConfigMap |
| `AWS_ACCESS_KEY_ID` | AWS Bedrock | `.env` / **K8s Secret** |
| `AWS_SECRET_ACCESS_KEY` | AWS Bedrock | `.env` / **K8s Secret** |
| `AWS_REGION` | AWS Bedrock | `.env` / K8s ConfigMap |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI | `.env` / K8s ConfigMap |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI | `.env` / K8s ConfigMap |
| `MISTRAL_API_KEY` | Mistral | `.env` / **K8s Secret** |
| `COHERE_API_KEY` | Cohere | `.env` / **K8s Secret** |
| `XAI_API_KEY` | Grok / xAI | `.env` / **K8s Secret** |
| `PERPLEXITY_API_KEY` | Perplexity | `.env` / **K8s Secret** |
| `OLLAMA_HOST` | Ollama (local) | `.env` / K8s ConfigMap |

### JVM Tuning

| Variable | Default | Description | Where to set |
|---|---|---|---|
| `JAVA_TOOL_OPTIONS` | `-Xms512m -Xmx1536m -XX:+UseG1GC` | JVM heap and GC settings | `.env` / ConfigMap |

**Guidelines:**
- Development: `-Xms256m -Xmx512m`
- Production (small): `-Xms512m -Xmx1536m`
- Production (large): `-Xms1g -Xmx3g`
- Never set `Xmx` above 75% of the container's memory limit

### Observability

| Variable | Default | Description | Where to set |
|---|---|---|---|
| `LOGGING_LEVEL_ROOT` | `WARN` | Root log level | `.env` / ConfigMap |
| `LOGGING_LEVEL_DEV_AGENTSPAN` | `INFO` | App log level | `.env` / ConfigMap |
| `MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED` | `false` | Enable OpenTelemetry | ConfigMap |
| `MANAGEMENT_OTLP_METRICS_EXPORT_URL` | _(unset)_ | OTLP collector URL | ConfigMap |

---

> **Bold = sensitive** — never put **K8s Secret** values in ConfigMaps or commit them to git.
