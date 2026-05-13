# Kubernetes Deployment

Deploy Agentspan to a Kubernetes cluster using raw manifests.

## Prerequisites

- `kubectl` configured and pointing at your cluster
- `docker` for building the image
- ingress-nginx controller installed

## Quick Start

```bash
# 1. Edit secrets
cp deployment/k8s/agentspan/secret.yaml deployment/k8s/agentspan/secret.yaml.bak
vi deployment/k8s/agentspan/secret.yaml  # set real passwords + API keys

# 2. Generate and set master key
openssl rand -base64 32
# paste the output into secret.yaml under AGENTSPAN_MASTER_KEY

# 3. Deploy
./deployment/k8s/deploy.sh
```

## Options

```
--namespace <name>    Kubernetes namespace (default: agentspan)
--context   <name>    kubectl context to use
--image     <tag>     Full image tag (default: agentspan/server:latest)
--skip-build          Skip Docker build, use existing image
```

## Manifests

All manifests live in `agentspan/`:

| File | Resource |
|------|----------|
| `namespace.yaml` | Namespace |
| `configmap.yaml` | Non-sensitive config |
| `secret.yaml` | Credentials + master key |
| `postgres.yaml` | PostgreSQL StatefulSet + PVC |
| `server.yaml` | Agentspan Deployment (3 replicas) |
| `ingress.yaml` | nginx Ingress |
| `hpa.yaml` | HorizontalPodAutoscaler |

## Cleanup

```bash
kubectl delete namespace agentspan
```
