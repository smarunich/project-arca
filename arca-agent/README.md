# Arca-Agent

The Arca-Agent is a Kubernetes operator designed to manage custom resources and deploy agent components based on the `AgentConfig` custom resource definition.

## Prerequisites

- Docker
- Kubernetes cluster (minikube or kind for local development)
- kubectl
- Helm 3.0+
- Python 3.9+
- Taskfile

## Build Steps

To build the Docker image for the Arca-Agent, use the Taskfile commands:

1. **Clone the repository**:
   ```sh
   git clone https://github.com/smarunich/project-arca.git arca-agent
   cd project-arca/arca-agent
   ```

2. **Build the Docker image**:
   ```sh
   task build-image
   ```

## Installation

To install the Arca-Agent on your Kubernetes cluster using Helm:

1. **Add the Helm repository** (if not already added):
   ```sh
   helm repo add arca-helm https://example.com/helm
   helm repo update
   ```

2. **Install the Arca-Agent using Helm**:
   ```sh
   helm install arca-agent ./helm -n arca-system  --create-namespace
   # helm   install arca-agent arca-helm/arca-agent -n arca-system
   ```

This will deploy the Arca-Agent to your Kubernetes cluster using the default configuration. You can customize the installation by modifying the `values.yaml` file or by providing additional configuration parameters during the Helm install command.
