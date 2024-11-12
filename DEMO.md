# ARCA Demo Guide

This guide provides a step-by-step demonstration of ARCA's capabilities in automating TSB resource management.

## Prerequisites

- Kubernetes cluster with TSB installed
- ARCA installed (agent and manager)
- `kubectl` configured
- Sample application files

## Demo Flow

### Namespace Management

```bash
# Create a demo namespace
cat <<EOF | kubectl apply -f -
apiVersion: v1
kind: Namespace
metadata:
  name: demo-app
EOF

# Show no TSB workspace exists yet
kubectl get namespace demo-app -o yaml

# Add ARCA label to enable management
kubectl label namespace demo-app arca.io/managed=true

# Show automatic workspace creation
kubectl get namespace demo-app -o yaml
```

Point out:
- Label triggers workspace creation
- Automatic configuration in TSB
- Workspace settings applied

### Service Exposure

```bash
# Deploy sample application
kubectl apply -f samples/bookinfo.yaml -n demo-app

# Show services without exposure
kubectl get services -n demo-app

# Expose productpage service
kubectl annotate service productpage \
  arca.io/expose=true \
  arca.io/domain=bookinfo.example.com \
  arca.io/path=/productpage \
  -n demo-app

# Show automatic gateway configuration
kubectl get service productpage -n demo-app -o yaml
```

Highlight:
- Simple annotation-based configuration
- Automatic gateway creation
- Route configuration
- Status feedback in annotations

### Cleanup

```bash
# Remove demo resources
kubectl delete namespace demo-app

# Show automatic cleanup
kubectl get workspaces -n tsb
```
