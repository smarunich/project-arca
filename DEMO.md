# ARCA Demo Guide

This guide provides a step-by-step demonstration of ARCA's capabilities in automating TSB resource management.

## Prerequisites

- Kubernetes cluster with TSB installed
- ARCA installed (agent and manager)
- `kubectl` configured
- Sample application files

## Demo Flow

### 1. Initial Setup (2 minutes)

```bash
# Verify ARCA installation
kubectl get pods -n arca-system

# Show current configuration
kubectl get agentconfig default -n arca-system -o yaml
kubectl get managerconfig default -n arca-system -o yaml
```

Expected output shows running pods and configurations.

### 2. Namespace Management (3 minutes)

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

### 3. Service Exposure (5 minutes)

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

### 4. Multi-Service Setup (5 minutes)

```bash
# Expose reviews service
kubectl annotate service reviews \
  arca.io/expose=true \
  arca.io/domain=reviews.example.com \
  -n demo-app

# Expose ratings service
kubectl annotate service ratings \
  arca.io/expose=true \
  arca.io/domain=ratings.example.com \
  -n demo-app

# Show gateway configurations
kubectl get gateways -n demo-app
```

Demonstrate:
- Multiple service exposure
- Gateway grouping
- Traffic routing

### 5. Security Features (3 minutes)

```bash
# Show default security settings
kubectl get workspacesettings -n demo-app default -o yaml

# Show mTLS configuration
kubectl get gateway productpage-gateway -n demo-app -o yaml
```

Highlight:
- Automatic mTLS configuration
- Security policies
- Traffic management

### 6. Operational Features (4 minutes)

```bash
# Show logs
kubectl logs -n arca-system -l app=arca-agent
kubectl logs -n arca-system -l app=arca-manager

# Demonstrate reconciliation
kubectl label namespace demo-app arca.io/managed-

# Watch automatic cleanup
kubectl get workspaces -n tsb

# Re-enable management
kubectl label namespace demo-app arca.io/managed=true

# Watch automatic recreation
kubectl get workspaces -n tsb
```

Show:
- Automatic reconciliation
- Error handling
- Status reporting

### 7. Cleanup (2 minutes)

```bash
# Remove demo resources
kubectl delete namespace demo-app

# Show automatic cleanup
kubectl get workspaces -n tsb
```

## Key Talking Points

1. **Automation Benefits**
   - Reduced manual operations
   - Consistent configuration
   - Error prevention

2. **Developer Experience**
   - Simple label/annotation interface
   - Clear status feedback
   - Self-service capabilities

3. **Platform Team Benefits**
   - Centralized management
   - Policy enforcement
   - Operational visibility

4. **Security Features**
   - Automatic mTLS
   - Consistent policies
   - Access control

## Common Questions

1. **How does it scale?**
   - Designed for large deployments
   - Efficient resource management
   - Batch operations support

2. **What about customization?**
   - Flexible annotation system
   - Override capabilities
   - Extension points

3. **Integration with existing tools?**
   - Standard Kubernetes resources
   - TSB API compatibility
   - CI/CD friendly

## Next Steps

1. Provide access to:
   - GitHub repository
   - Documentation
   - Support channels

2. Discuss:
   - POC requirements
   - Integration needs
   - Support options 