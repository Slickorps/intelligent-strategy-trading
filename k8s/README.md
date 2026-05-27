# Kubernetes Deployment — Intelligent Strategy Trading

## Architecture

```
                   ┌──────────────┐
                   │   Ingress    │
                   │  (Optional)  │
                   └──────┬───────┘
                          │
                  ┌───────┴────────┐
                  │  ist-api-lb    │
                  │  (LoadBalancer)│
                  └───────┬────────┘
                          │
          ┌───────────────┼───────────────────┐
          │               │                   │
   ┌──────┴──────┐ ┌─────┴──────┐ ┌──────────┴─────────┐
   │  ist-api    │ │ ist-monitor │ │   ist-dashboard    │
   │  (2-10 PoD) │ │  (1 PoD)   │ │    (2-6 PoD)       │
   └──────┬──────┘ └─────┬──────┘ └──────────┬─────────┘
          │              │                    │
   ┌──────┴──────┐       │                    │
   │  ConfigMap  │       │                    │
   │ + Secret    │       │                    │
   └─────────────┘       │                    │
                         │                    │
              ┌──────────┴──────────┐
              │  External Services  │
              │  (Postgres, Redis)  │
              └─────────────────────┘
```

## Prerequisites

- Kubernetes cluster v1.24+
- `kubectl` configured with cluster access
- Container images built and pushed to registry

## Quick Start

### 1. Apply in Order

```bash
# 1. Namespace first
kubectl apply -f k8s/namespace.yaml

# 2. Configuration
kubectl apply -f k8s/configmap.yaml

# 3. Secrets (create manually or use sealed-secrets)
# kubectl create secret generic ist-trading-secret \
#   --namespace=ist-trading \
#   --from-literal=database_password=your_password \
#   --from-literal=redis_password=your_password

# 4. Deployments
kubectl apply -f k8s/deployment.yaml

# 5. Services
kubectl apply -f k8s/service.yaml

# 6. Autoscaling
kubectl apply -f k8s/hpa.yaml
```

### 2. Verify Deployment

```bash
# Check all resources
kubectl get all -n ist-trading

# Check pods status
kubectl get pods -n ist-trading -w

# Check services
kubectl get svc -n ist-trading

# Check HPA
kubectl get hpa -n ist-trading
```

### 3. Access Services

```bash
# Port-forward API
kubectl port-forward -n ist-trading svc/ist-trading-api 8000:8000

# Port-forward Monitor
kubectl port-forward -n ist-trading svc/ist-monitor 8080:8080

# Port-forward Dashboard
kubectl port-forward -n ist-trading svc/ist-dashboard 3000:80

# Or get LoadBalancer IP (cloud provider)
kubectl get svc ist-trading-api-lb -n ist-trading
```

## Configuration

### Environment Variables

All configuration is managed via `ConfigMap` (`configmap.yaml`):

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_HOST` | PostgreSQL host | `postgres.ist-trading.svc.cluster.local` |
| `DATABASE_PORT` | PostgreSQL port | `5432` |
| `REDIS_HOST` | Redis host | `redis.ist-trading.svc.cluster.local` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `TRADING_MODE` | paper / live | `paper` |

### Secrets

Create secrets manually for sensitive data:

```bash
kubectl create secret generic ist-trading-secret \
  --namespace=ist-trading \
  --from-literal=database_password='<your-db-password>' \
  --from-literal=redis_password='<your-redis-password>'
```

## Autoscaling

Two HPAs are configured:

| HPA | Min | Max | CPU Trigger | Memory Trigger |
|-----|-----|-----|-------------|----------------|
| `ist-trading-api-hpa` | 2 | 10 | 70% | 80% |
| `ist-dashboard-hpa` | 2 | 6 | 80% | — |

### Scaling Behavior

- **Scale Up**: Aggressive (100% increase per minute)
- **Scale Down**: Conservative (25% decrease per 2 minutes, 5 min stabilization)

## Monitoring

```bash
# View pod logs
kubectl logs -n ist-trading -l app=intelligent-strategy-trading,component=api

# Stream live logs
kubectl logs -n ist-trading -l app=intelligent-strategy-trading,component=api -f

# Describe pod for debugging
kubectl describe pod -n ist-trading -l app=intelligent-strategy-trading,component=api

# Check resource usage
kubectl top pods -n ist-trading
```

## Updating

### Rolling Update

```bash
# Update image
kubectl set image deployment/ist-trading-api -n ist-trading api=ist-trading-api:v2.0.0

# Check rollout status
kubectl rollout status deployment/ist-trading-api -n ist-trading

# Rollback if needed
kubectl rollout undo deployment/ist-trading-api -n ist-trading
```

### Configuration Changes

```bash
# Update ConfigMap
kubectl apply -f k8s/configmap.yaml

# Restart pods to pick up changes
kubectl rollout restart deployment -n ist-trading -l app=intelligent-strategy-trading
```

## Clean Up

```bash
# Delete namespace (removes ALL resources)
kubectl delete namespace ist-trading

# Or selectively
kubectl delete -f k8s/
```

## Production Considerations

1. **External Database**: Use managed PostgreSQL (AWS RDS, GCP Cloud SQL) instead of in-cluster
2. **External Redis**: Use managed Redis (AWS ElastiCache, GCP Memorystore)
3. **Ingress**: Configure TLS and domain for production ingress
4. **Network Policies**: Restrict pod-to-pod communication
5. **Pod Disruption Budgets**: Ensure availability during maintenance
6. **Backup**: Regular etcd backups for cluster state
7. **Secrets Management**: Use SealedSecrets or External Secrets Operator
8. **Resource Quotas**: Set namespace-level resource limits