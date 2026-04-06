#!/usr/bin/env bash
# deploy.sh — Deploy Agentspan to a Kubernetes cluster
#
# Usage:
#   ./deployment/k8s/deploy.sh [options]
#
# Options:
#   --namespace  <name>    Kubernetes namespace (default: agentspan)
#   --context    <name>    kubectl context to use
#   --image      <tag>     Full image tag to build and push (default: agentspan/server:latest)
#   --skip-build           Skip Docker build (use existing image)
#
# Prerequisites:
#   - kubectl configured and pointing at your cluster
#   - docker (for building the image)
#   - ingress-nginx controller installed in the cluster
#   - Edit deployment/k8s/agentspan/secret.yaml with your credentials FIRST
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
K8S_DIR="$REPO_ROOT/deployment/k8s/agentspan"

NAMESPACE="${NAMESPACE:-agentspan}"
CONTEXT="${CONTEXT:-}"
IMAGE="${IMAGE:-agentspan/server:latest}"
SKIP_BUILD="${SKIP_BUILD:-false}"

# ── Helpers ────────────────────────────────────────────────────────────────────
log()  { echo "[deploy] $*"; }
fail() { echo "[deploy] ERROR: $*" >&2; exit 1; }

kctl() {
  if [[ -n "$CONTEXT" ]]; then
    kubectl --context="$CONTEXT" "$@"
  else
    kubectl "$@"
  fi
}

wait_for_rollout() {
  local resource=$1
  log "  Waiting for $resource..."
  kctl rollout status "$resource" -n "$NAMESPACE" --timeout=300s
}

# ── Parse args ─────────────────────────────────────────────────────────────────
while [[ $# -gt 0 ]]; do
  case $1 in
    --namespace)  NAMESPACE="$2"; shift 2 ;;
    --context)    CONTEXT="$2";   shift 2 ;;
    --image)      IMAGE="$2";     shift 2 ;;
    --skip-build) SKIP_BUILD=true; shift ;;
    *) fail "Unknown argument: $1" ;;
  esac
done

# ── Preflight ──────────────────────────────────────────────────────────────────
command -v kubectl >/dev/null 2>&1 || fail "kubectl not found"
kctl cluster-info >/dev/null 2>&1   || fail "Cannot reach Kubernetes cluster. Check your kubeconfig."

log "Deploying Agentspan"
log "  Namespace : $NAMESPACE"
log "  Image     : $IMAGE"
[[ -n "$CONTEXT" ]] && log "  Context   : $CONTEXT"
echo ""

# Refuse to proceed with placeholder password
if grep -q "changeme" "$K8S_DIR/secret.yaml"; then
  fail "secret.yaml still contains the default placeholder password.\nEdit deployment/k8s/agentspan/secret.yaml before deploying."
fi

# ── Build & push image ─────────────────────────────────────────────────────────
if [[ "$SKIP_BUILD" != "true" ]]; then
  log "Building image (UI + server combined)..."
  docker build -f "$REPO_ROOT/server/Dockerfile" -t "$IMAGE" "$REPO_ROOT"
  log "Pushing $IMAGE..."
  docker push "$IMAGE"
else
  log "Skipping build (--skip-build)"
fi

# ── Apply manifests ────────────────────────────────────────────────────────────
log "1/6  Namespace"
kctl apply -f "$K8S_DIR/namespace.yaml"

log "2/6  ConfigMap + Secret"
kctl apply -f "$K8S_DIR/configmap.yaml"
kctl apply -f "$K8S_DIR/secret.yaml"

log "3/6  PostgreSQL"
kctl apply -f "$K8S_DIR/postgres.yaml"
kctl rollout status statefulset/agentspan-postgres -n "$NAMESPACE" --timeout=120s

log "4/6  Agentspan Server (3 replicas)"
# Patch the image tag if a custom one was specified
if [[ "$IMAGE" != "agentspan/server:latest" ]]; then
  kctl set image deployment/agentspan-server server="$IMAGE" -n "$NAMESPACE" 2>/dev/null || true
fi
kctl apply -f "$K8S_DIR/server.yaml"
wait_for_rollout deployment/agentspan-server

log "5/6  Ingress"
kctl apply -f "$K8S_DIR/ingress.yaml"

log "6/6  HPA"
kctl apply -f "$K8S_DIR/hpa.yaml"

# ── Summary ────────────────────────────────────────────────────────────────────
echo ""
echo "╔══════════════════════════════════════════════════════════╗"
echo "║          Agentspan deployed successfully!                ║"
echo "╚══════════════════════════════════════════════════════════╝"
echo ""
kctl get pods -n "$NAMESPACE"
echo ""

INGRESS_IP=$(kctl get svc -n ingress-nginx ingress-nginx-controller \
  -o jsonpath='{.status.loadBalancer.ingress[0].ip}' 2>/dev/null || echo "<pending>")

echo "Load balancer IP : $INGRESS_IP"
echo ""
echo "Next steps:"
echo "  1. Point your domain DNS A record → $INGRESS_IP"
echo "  2. Update 'host:' in deployment/k8s/agentspan/ingress.yaml to your domain"
echo "  3. (Optional) Set up TLS — see deployment/README.md"
echo "  4. Open http://<your-domain>"
echo ""
