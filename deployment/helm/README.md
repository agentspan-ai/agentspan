# Agentspan Helm Chart

This directory contains a Helm chart for deploying Agentspan on Kubernetes.

## Chart Path

`deployment/helm/agentspan`

## Quick Start

```bash
helm upgrade --install agentspan ./deployment/helm/agentspan \
  --namespace agentspan \
  --create-namespace \
  --set secrets.postgresPassword='change-me'
```

For local/k3d installs without ingress:

```bash
helm upgrade --install agentspan ./deployment/helm/agentspan \
  --namespace agentspan \
  --create-namespace \
  --set ingress.enabled=false \
  --set image.pullPolicy=IfNotPresent \
  --set secrets.postgresPassword='change-me'
```

## Validate

```bash
helm lint ./deployment/helm/agentspan
helm template agentspan ./deployment/helm/agentspan --namespace agentspan >/tmp/agentspan-rendered.yaml
```

## Notes

- Use either bundled Postgres (`postgres.enabled=true`) or external Postgres (`externalDatabase.enabled=true`), but not both.
- Set `postgres.persistence.enabled=false` for ephemeral local dev DB storage (`emptyDir`), or keep `true` for PVC-backed durable storage.
- For production, prefer `secrets.existingSecret` and disable chart-managed Secret creation.
- If using persistent Postgres storage, treat password changes as a DB migration/rotation operation.
