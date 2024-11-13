# ARCA - Automated Resource and Configuration Assistant

ARCA is a Kubernetes operator that automates gateway lifecycle management and service exposure in Tetrate Service Bridge (TSB) environments. It provides a seamless experience for developers to expose services while maintaining platform team control.

## Overview

ARCA consists of two main components:
- **ARCA Agent**: Manages TSB resources (workspaces, gateway groups, gateways)
- **ARCA Manager**: Handles local Kubernetes resources and gateway deployment

### Key Features
- 🔄 Automated gateway lifecycle management
- 🚀 Simple service exposure via annotations
- 🔒 Standardized gateway configurations
- 📊 Centralized policy enforcement

## Quick Start

1. **Install ARCA**
```bash
# Install CRDs and operators
kubectl apply -f helm/crds/
helm install arca-agent ./arca-agent/helm -n arca-system
helm install arca-manager ./arca-manager/helm -n arca-system
```

2. **Label Your Namespace**
```bash
kubectl label namespace my-namespace arca.io/managed=true
```

3. **Expose Your Service**
```yaml
apiVersion: v1
kind: Service
metadata:
  name: my-service
  annotations:
    arca.io/expose: "true"
    arca.io/domain: "myapp.example.com"
    arca.io/path: "/api"
```

## Documentation

- [Architecture](ARCHITECTURE.md) - Detailed system design
- [Demo Guide](DEMO.md) - Step-by-step demonstration
- [User Stories](USER_STORIES.md) - Use cases and scenarios
- [PRD](PRD.md) - Product requirements

## Development

### Prerequisites
- Python 3.9+
- Docker
- Kubernetes cluster
- TSB access

### Build and Test
```bash
# Build and deploy
task release-now
```

## Configuration

### Agent Config
```yaml
apiVersion: operator.arca.io/v1alpha1
kind: AgentConfig
metadata:
  name: default
spec:
  discoveryLabel: "arca.io/managed=true"
  serviceFabric: "aks-arca-eastus-0"
  tetrate:
    endpoint: "https://tsb.example.com"
    organization: "tetrate"
    tenant: "arca"
    clusterName: "cluster1"
```

### Manager Config
```yaml
apiVersion: operator.arca.io/v1alpha1
kind: ManagerConfig
metadata:
  name: default
spec:
  discoveryLabel: "arca.io/managed=true"
  tetrate:
    clusterName: "cluster1"
```

## Demo

Run the interactive demo:
```bash
# Run with default namespace
./demo.sh

# Run with custom namespace
./demo.sh -n my-demo
```

See [SUGGESTIONS.md](SUGGESTIONS.md) for improvement ideas.

## License

[MIT License](LICENSE.md) 