# agent.py

import kopf
import kubernetes
from kubernetes import client, config

# Load the Kubernetes configuration
config.load_incluster_config()

# Create Kubernetes API clients
core_v1_api = client.CoreV1Api()

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, namespace, **kwargs):
    """
    Handle creation and updates to AgentConfig resources.
    """
    agent_setting = spec.get('agentSetting', 'default-value')
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label:
        raise kopf.PermanentError("discoveryLabel must be specified in AgentConfig.")

    # Fetch namespaces that match the discovery label
    namespaces = core_v1_api.list_namespace(label_selector=discovery_label)
    for ns in namespaces.items:
        print(f"Scanning namespace: {ns.metadata.name}")
        services = core_v1_api.list_namespaced_service(ns.metadata.name)
        for svc in services.items:
            print_service_details(svc)

    print("Namespace scanning complete.")

def print_service_details(service):
    """
    Print detailed information about a Kubernetes service.
    """
    print(f"Service Name: {service.metadata.name}")
    print(f"Namespace: {service.metadata.namespace}")
    print(f"Labels: {service.metadata.labels}")
    print(f"Annotations: {service.metadata.annotations}")
    print(f"Cluster IP: {service.spec.cluster_ip}")
    print(f"Ports: {service.spec.ports}")
    print(f"Type: {service.spec.type}")
    print(f"Session Affinity: {service.spec.session_affinity}")
    if service.spec.selector:
        print(f"Selector: {service.spec.selector}")
    print("-----")
