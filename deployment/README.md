# Agentspan Deployment Guide

Agentspan is a durable execution runtime for AI agents. This guide covers every deployment path from a single-command local start to a production Kubernetes cluster with auto-scaling, TLS, and managed PostgreSQL.

---

## Table of Contents

1. [Quick Start](#1-quick-start)
2. [Architecture](#2-architecture)
3. [Deployment Options](#3-deployment-options)
4. [Local Development](#4-local-development)
5. [Single Server — Docker](#5-single-server--docker)
6. [Production — Docker Compose](#6-production--docker-compose)
7. [Production — Kubernetes](#7-production--kubernetes)
8. [Production — Helm](#8-production--helm)
9. [Managed Database (RDS / Cloud SQL / Azure DB)](#9-managed-database)
10. [TLS / HTTPS](#10-tls--https)
11. [Observability](#11-observability)
12. [Backup & Restore](#12-backup--restore)
13. [Production Checklist](#13-production-checklist)
14. [Configuration Reference](#14-configuration-reference)

---

## 1. Quick Start

```bash
# Install the CLI
curl -fsSL https://raw.githubusercontent.com/agentspan-ai/agentspan/main/cli/install.sh | sh

# Start the server (SQLite, no setup needed)
export OPENAI_API_KEY=sk-...
agentspan server start
```

Open the UI at **http://localhost:6767**

---

## 2. Architecture

### Components

| Component | Description |
|---|---|
| **API Server** | REST API at `/api/**` and React UI at `/**`, both served from port 6767 |
| **Execution Engine** | Durable state machine — survives restarts, picks up in-progress agents |
| **Sweeper** | Background process that monitors running agent executions |
| **Tool Worker** | Executes built-in tools (HTTP, file, code, search) |
| **Credential Store** | AES-256-GCM encrypted storage for API keys and secrets |

A single `agentspan/server` Docker image contains all components — no separate frontend container.

### Infrastructure

| Layer | Development | Production |
|---|---|---|
| Database | SQLite (file) | PostgreSQL 16 |
| Storage | Local file | PVC (K8s) or Docker volume |
| Scaling | Single process | 3–10 replicas + HPA |
| Networking | localhost:6767 | Ingress → LoadBalancer |

### Deployment topology (Kubernetes)

```
Internet ──► DNS ──► LoadBalancer ──► Ingress (nginx) ──► agentspan-server:6767
                                                                │
                                              agentspan-postgres (StatefulSet + PVC)
```

---

## 3. Deployment Options

Choose the stack that fits your environment:

| Environment | Method | Database | Best for |
|---|---|---|---|
| Local dev | `agentspan server start` | SQLite | Development, testing |
| Single VM (demo) | `docker run` | SQLite | Demos, staging |
| Single VM (prod) | Docker Compose | PostgreSQL | Small teams, single-region |
| Multi-instance | Kubernetes | PostgreSQL | HA, auto-scaling, production SaaS |
| GitOps | Helm | PostgreSQL | Templated multi-env deployments |

### Database backends

| Backend | When to use |
|---|---|
| **SQLite** | Local development only. Single process, no setup, data in `agent-runtime.db`. |
| **PostgreSQL** | All production deployments. ACID-compliant, supports multiple replicas. |

---

## 4. Local Development

Zero config. Uses SQLite. Data persists in `./agent-runtime.db`.

```bash
export OPENAI_API_KEY=sk-...
agentspan server start
```

**Files created:**
- `~/.agentspan/` — server JAR and config
- `./agent-runtime.db` — SQLite database (working directory)

**Reset:** `rm agent-runtime.db`

---

## 5. Single Server — Docker

### Standalone (SQLite — no external DB needed)

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

**Verify:**
```bash
curl http://localhost:6767/actuator/health
# {"status":"UP"}
```

---

## 6. Production — Docker Compose

Best for: single VM production. Includes PostgreSQL with a persistent volume.

### Setup

```bash
cd deployment/docker-compose
cp .env.example .env
```

Edit `.env` — set at minimum:

```bash
# Generate and set the encryption master key
AGENTSPAN_MASTER_KEY=$(openssl rand -base64 32)

# Change the database password
POSTGRES_PASSWORD=your-strong-password

# Set at least one LLM provider key
OPENAI_API_KEY=sk-...
# ANTHROPIC_API_KEY=sk-ant-...
# GEMINI_API_KEY=...
```

### Start

```bash
docker compose up -d

# Stream logs
docker compose logs -f agentspan

# Verify health
curl http://localhost:6767/actuator/health
```

### Upgrade

```bash
docker compose pull
docker compose up -d
```

### Stop

```bash
docker compose down        # stop, keep data
docker compose down -v     # stop + delete database (irreversible)
```

Data persists in the `postgres_data` Docker volume. Back it up before upgrading.

---

## 7. Production — Kubernetes

Best for: high availability, auto-scaling, managed cloud.

### Prerequisites

| Tool | Purpose |
|---|---|
| `kubectl` | Kubernetes CLI |
| ingress-nginx | Ingress controller |
| cert-manager | Automatic TLS (optional but recommended) |
| metrics-server | Required for HPA auto-scaling |

```bash
# ingress-nginx
kubectl apply -f https://raw.githubusercontent.com/kubernetes/ingress-nginx/controller-v1.10.1/deploy/static/provider/cloud/deploy.yaml

# cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/latest/download/cert-manager.yaml

# metrics-server
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

### Step 1 — Secrets

Edit `deployment/k8s/agentspan/secret.yaml`. **Never commit this file with real values.**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: agentspan-secrets
  namespace: agentspan
type: Opaque
stringData:
  AGENTSPAN_MASTER_KEY: "..."                  # openssl rand -base64 32
  POSTGRES_PASSWORD: "your-strong-password"    # required
  POSTGRES_USER: "agentspan"
  OPENAI_API_KEY: "sk-..."                     # at least one LLM key
  # ANTHROPIC_API_KEY: "sk-ant-..."
  # GEMINI_API_KEY: "..."
```

> **Tip:** Use [Sealed Secrets](https://github.com/bitnami-labs/sealed-secrets), [External Secrets Operator](https://external-secrets.io/), or your cloud secrets manager (AWS Secrets Manager, GCP Secret Manager, Azure Key Vault) instead of committing plaintext.

### Step 2 — Config

Non-sensitive settings go in `deployment/k8s/agentspan/configmap.yaml` (safe to commit):

```yaml
data:
  SPRING_PROFILES_ACTIVE: "postgres"
  POSTGRES_HOST: "agentspan-postgres"
  POSTGRES_DB: "agentspan"
  JAVA_OPTS: "-Xms512m -Xmx1536m -XX:+UseG1GC -XX:MaxGCPauseMillis=200"
  LOGGING_LEVEL_ROOT: "WARN"
  LOGGING_LEVEL_DEV_AGENTSPAN: "INFO"
```

### Step 3 — Domain

Edit `deployment/k8s/agentspan/ingress.yaml`, replace `agentspan.example.com` with your domain:

```yaml
rules:
  - host: agentspan.yourdomain.com
```

### Step 4 — Deploy

```bash
# Deploy everything in order
kubectl apply -f deployment/k8s/agentspan/namespace.yaml
kubectl apply -f deployment/k8s/agentspan/configmap.yaml
kubectl apply -f deployment/k8s/agentspan/secret.yaml
kubectl apply -f deployment/k8s/agentspan/postgres.yaml
kubectl rollout status statefulset/agentspan-postgres -n agentspan
kubectl apply -f deployment/k8s/agentspan/server.yaml
kubectl rollout status deployment/agentspan-server -n agentspan
kubectl apply -f deployment/k8s/agentspan/ingress.yaml
kubectl apply -f deployment/k8s/agentspan/hpa.yaml
```

Or use the deploy script:

```bash
./deployment/k8s/deploy.sh
./deployment/k8s/deploy.sh --image registry.example.com/agentspan/server:v1.2.0
./deployment/k8s/deploy.sh --skip-build --context my-cluster-context
```

### Step 5 — DNS

```bash
# Get the load balancer IP
kubectl get ingress -n agentspan

# Create an A record:
#   agentspan.yourdomain.com → <EXTERNAL-IP>
```

### Useful commands

```bash
# Pod status
kubectl get pods -n agentspan

# Server logs
kubectl logs -f deployment/agentspan-server -n agentspan

# Restart (pick up new image)
kubectl rollout restart deployment/agentspan-server -n agentspan

# Local port-forward (bypass ingress)
kubectl port-forward svc/agentspan-server 6767:6767 -n agentspan

# Manual scale
kubectl scale deployment/agentspan-server --replicas=5 -n agentspan

# Tear down
kubectl delete namespace agentspan
```

### Horizontal scaling

The default HPA scales between 3 and 10 replicas based on CPU (70%) and memory (80%). All replicas share the same PostgreSQL database — no additional coordination needed.

To change limits, edit `deployment/k8s/agentspan/hpa.yaml` or set Helm values (see section 8).

---

## 8. Production — Helm

Best for: GitOps, templated multi-environment deployments.

### Install

```bash
helm install agentspan ./deployment/helm/agentspan \
  --namespace agentspan \
  --create-namespace \
  --set secrets.masterKey=$(openssl rand -base64 32) \
  --set secrets.postgresPassword=your-strong-password \
  --set secrets.openaiApiKey=sk-...
```

### Common overrides

```bash
# Use an external (managed) database instead of the bundled one
helm install agentspan ./deployment/helm/agentspan \
  --namespace agentspan \
  --create-namespace \
  --set postgres.enabled=false \
  --set externalDatabase.enabled=true \
  --set externalDatabase.host=your-rds-endpoint.rds.amazonaws.com \
  --set externalDatabase.database=agentspan \
  --set secrets.postgresPassword=your-password \
  --set secrets.openaiApiKey=sk-...

# Enable ingress + TLS
helm upgrade agentspan ./deployment/helm/agentspan \
  --set ingress.enabled=true \
  --set ingress.hosts[0].host=agentspan.yourdomain.com \
  --set ingress.tls[0].hosts[0]=agentspan.yourdomain.com \
  --set ingress.tls[0].secretName=agentspan-tls

# Change image tag for a version upgrade
helm upgrade agentspan ./deployment/helm/agentspan \
  --set image.tag=0.0.15
```

### Uninstall

```bash
helm uninstall agentspan --namespace agentspan
```

See `deployment/helm/agentspan/values.yaml` for all configurable values.

---

## 9. Managed Database

For production, replace the bundled PostgreSQL StatefulSet with a managed service for automated backups, failover, and point-in-time recovery.

| Cloud | Service |
|---|---|
| AWS | RDS for PostgreSQL |
| GCP | Cloud SQL for PostgreSQL |
| Azure | Azure Database for PostgreSQL |
| Self-hosted | [CloudNativePG](https://cloudnative-pg.io/) |

### Docker Compose — update `.env`

```bash
POSTGRES_HOST=your-rds-endpoint.rds.amazonaws.com
POSTGRES_USER=agentspan
POSTGRES_PASSWORD=your-password
POSTGRES_DB=agentspan
```

### Kubernetes — update configmap + secret

`deployment/k8s/agentspan/configmap.yaml`:
```yaml
POSTGRES_HOST: "your-rds-endpoint.rds.amazonaws.com"
POSTGRES_DB: "agentspan"
```

`deployment/k8s/agentspan/secret.yaml`:
```yaml
POSTGRES_USER: "agentspan"
POSTGRES_PASSWORD: "your-password"
```

Also remove the `postgres.yaml` manifest — the bundled DB is no longer needed.

### Helm — use `externalDatabase`

```bash
helm upgrade agentspan ./deployment/helm/agentspan \
  --set postgres.enabled=false \
  --set externalDatabase.enabled=true \
  --set externalDatabase.host=your-rds-endpoint.rds.amazonaws.com \
  --set secrets.postgresUser=agentspan \
  --set secrets.postgresPassword=your-password
```

### Cloud-specific storage class

When using the bundled PostgreSQL StatefulSet on cloud K8s, set the right storage class for your provider:

| Cloud | storageClassName |
|---|---|
| AWS EKS | `gp3` |
| GCP GKE | _(default — no change needed)_ |
| Azure AKS | `managed-premium` |

Edit `deployment/k8s/agentspan/postgres.yaml` or set `postgres.persistence.storageClass` in Helm values.

---

## 10. TLS / HTTPS

### Kubernetes — cert-manager (recommended)

**Step 1** — Create a ClusterIssuer:

```yaml
# deployment/k8s/agentspan/cluster-issuer.yaml
apiVersion: cert-manager.io/v1
kind: ClusterIssuer
metadata:
  name: letsencrypt-prod
spec:
  acme:
    server: https://acme-v02.api.letsencrypt.org/directory
    email: ops@yourdomain.com
    privateKeySecretRef:
      name: letsencrypt-prod
    solvers:
      - http01:
          ingress:
            class: nginx
```

```bash
kubectl apply -f deployment/k8s/agentspan/cluster-issuer.yaml
```

**Step 2** — Uncomment TLS in `deployment/k8s/agentspan/ingress.yaml`:

```yaml
metadata:
  annotations:
    cert-manager.io/cluster-issuer: "letsencrypt-prod"
spec:
  tls:
    - hosts:
        - agentspan.yourdomain.com
      secretName: agentspan-tls
```

### Docker / single server — nginx reverse proxy

```nginx
server {
    listen 443 ssl;
    server_name agentspan.yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/agentspan.yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/agentspan.yourdomain.com/privkey.pem;

    location / {
        proxy_pass http://localhost:6767;
        proxy_set_header Host              $host;
        proxy_set_header X-Real-IP         $remote_addr;
        proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # SSE / streaming support
        proxy_buffering    off;
        proxy_cache        off;
        proxy_read_timeout 3600s;
    }
}
```

---

## 11. Observability

### Health endpoints

```bash
curl http://localhost:6767/actuator/health           # overall
curl http://localhost:6767/actuator/health/liveness  # liveness probe
curl http://localhost:6767/actuator/health/readiness # readiness probe
```

### Prometheus metrics

Metrics are exposed at `/actuator/prometheus`:

```bash
curl http://localhost:6767/actuator/prometheus
```

Prometheus scrape config:

```yaml
scrape_configs:
  - job_name: agentspan
    static_configs:
      - targets: ['agentspan:6767']
    metrics_path: /actuator/prometheus
```

Key metrics:

| Metric | Description |
|---|---|
| `agentspan_agent_executions_total` | Total agent runs |
| `agentspan_agent_duration_seconds` | Execution duration histogram |
| `agentspan_tool_calls_total` | Tool invocations |
| `agentspan_guardrail_failures_total` | Guardrail failures |
| `jvm_memory_used_bytes` | JVM heap usage |

### Log levels

```bash
# Verbose (troubleshooting)
LOGGING_LEVEL_ROOT=INFO
LOGGING_LEVEL_DEV_AGENTSPAN=DEBUG

# Default (production)
LOGGING_LEVEL_ROOT=WARN
LOGGING_LEVEL_DEV_AGENTSPAN=INFO
```

### OpenTelemetry (opt-in)

Distributed tracing is disabled by default. Enable via env vars:

```bash
MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED=true
MANAGEMENT_OTLP_METRICS_EXPORT_URL=http://your-otel-collector:4318/v1/metrics
```

---

## 12. Backup & Restore

### PostgreSQL — Docker Compose

```bash
# Backup
docker exec agentspan-postgres-1 pg_dump -U agentspan agentspan > backup_$(date +%Y%m%d).sql

# Restore
docker exec -i agentspan-postgres-1 psql -U agentspan agentspan < backup_20260101.sql
```

### PostgreSQL — Kubernetes

```bash
# Backup
kubectl exec -n agentspan statefulset/agentspan-postgres -- \
  pg_dump -U agentspan agentspan > backup_$(date +%Y%m%d).sql

# Restore
kubectl exec -i -n agentspan statefulset/agentspan-postgres -- \
  psql -U agentspan agentspan < backup_20260101.sql
```

### SQLite — local dev

```bash
# Backup
cp agent-runtime.db agent-runtime.db.$(date +%Y%m%d).bak

# Restore
cp agent-runtime.db.20260101.bak agent-runtime.db
```

Run a backup before every upgrade.

---

## 13. Production Checklist

### Security
- [ ] `AGENTSPAN_MASTER_KEY` set to a generated key (`openssl rand -base64 32`)
- [ ] `POSTGRES_PASSWORD` changed from `changeme` to a strong password
- [ ] TLS / HTTPS enabled
- [ ] K8s secrets managed via Sealed Secrets or a cloud secrets manager
- [ ] `secret.yaml` added to `.gitignore` — no plaintext secrets in git
- [ ] LLM API keys rotated if ever committed or shared

### Database
- [ ] PostgreSQL in use (not SQLite)
- [ ] Managed database service used (RDS, Cloud SQL) — not a stateful pod
- [ ] Automated backups scheduled
- [ ] Restore tested before go-live

### Reliability
- [ ] 2+ replicas running (`kubectl get pods -n agentspan`)
- [ ] HPA configured (`kubectl get hpa -n agentspan`)
- [ ] PodDisruptionBudget in place (`minAvailable: 2`)
- [ ] Liveness and readiness probes responding

### Observability
- [ ] Prometheus scraping `/actuator/prometheus`
- [ ] Log aggregation set up (CloudWatch, Datadog, Loki, etc.)
- [ ] Alerting on error rate and latency

### Operations
- [ ] Upgrade runbook written: pull → `docker compose up -d` or `kubectl rollout restart`
- [ ] Backup → restore → verify tested end-to-end

---

## 14. Configuration Reference

All env vars. **Bold** = sensitive — set in K8s Secret or `.env`, never in ConfigMap or git.

### Encryption

| Variable | Default | Description |
|---|---|---|
| **`AGENTSPAN_MASTER_KEY`** | _(auto-generated)_ | AES-256-GCM key for credential encryption (base64-encoded 32 bytes). Generate with `openssl rand -base64 32`. **Required in production** — auto-generated keys are ephemeral in containers. |

### Server

| Variable | Default | Description |
|---|---|---|
| `SERVER_PORT` | `6767` | HTTP listen port |
| `SPRING_PROFILES_ACTIVE` | `default` (SQLite) | Set to `postgres` for PostgreSQL |

### Database — SQLite (dev only)

| Variable | Default | Description |
|---|---|---|
| `SPRING_DATASOURCE_URL` | `jdbc:sqlite:agent-runtime.db` | SQLite file path |

### Database — PostgreSQL

| Variable | Default | Description |
|---|---|---|
| `SPRING_DATASOURCE_URL` | `jdbc:postgresql://localhost:5432/agentspan` | Full JDBC URL |
| `SPRING_DATASOURCE_USERNAME` | `postgres` | DB user |
| **`SPRING_DATASOURCE_PASSWORD`** | `postgres` | DB password |
| `SPRING_DATASOURCE_HIKARI_MAXIMUM_POOL_SIZE` | `8` | Connection pool size |

### JVM

| Variable | Default | Description |
|---|---|---|
| `JAVA_TOOL_OPTIONS` | `-Xms512m -Xmx1536m -XX:+UseG1GC` | JVM heap + GC settings |

Guidelines:
- Dev: `-Xms256m -Xmx512m`
- Prod small: `-Xms512m -Xmx1536m`
- Prod large: `-Xms1g -Xmx3g`
- Never set `-Xmx` above 75% of the container memory limit

### LLM Providers

Set at least one API key. The server auto-detects and enables providers when their key is present.

| Variable | Provider |
|---|---|
| **`OPENAI_API_KEY`** | OpenAI |
| **`ANTHROPIC_API_KEY`** | Anthropic |
| **`GEMINI_API_KEY`** | Google Gemini |
| **`AZURE_OPENAI_API_KEY`** | Azure OpenAI |
| **`AZURE_OPENAI_ENDPOINT`** | Azure OpenAI |
| `AZURE_OPENAI_DEPLOYMENT` | Azure OpenAI (model deployment name) |
| **`AWS_ACCESS_KEY_ID`** | AWS Bedrock |
| **`AWS_SECRET_ACCESS_KEY`** | AWS Bedrock |
| `AWS_REGION` | AWS Bedrock (default: `us-east-1`) |
| `GOOGLE_CLOUD_PROJECT` | Vertex AI |
| `GOOGLE_CLOUD_LOCATION` | Vertex AI (default: `us-central1`) |
| **`MISTRAL_API_KEY`** | Mistral |
| **`COHERE_API_KEY`** | Cohere |
| **`XAI_API_KEY`** | Grok / xAI |
| **`PERPLEXITY_API_KEY`** | Perplexity |
| `OLLAMA_HOST` | Ollama (e.g. `http://localhost:11434`) |

### Observability

| Variable | Default | Description |
|---|---|---|
| `LOGGING_LEVEL_ROOT` | `WARN` | Root log level |
| `LOGGING_LEVEL_DEV_AGENTSPAN` | `INFO` | App log level |
| `MANAGEMENT_OTLP_METRICS_EXPORT_ENABLED` | `false` | Enable OpenTelemetry export |
| `MANAGEMENT_OTLP_METRICS_EXPORT_URL` | _(unset)_ | OTLP collector endpoint |

---

> **Bold variables are sensitive** — store them in K8s Secrets (not ConfigMaps) and in `.env` (not committed to git).
