import os
import kopf
import kubernetes
from kubernetes import client, config
import logging

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# Load the Kubernetes configuration
try:
    config.load_incluster_config()
    logger.debug("Loaded in-cluster Kubernetes configuration.")
except config.ConfigException:
    config.load_kube_config()
    logger.debug("Loaded local Kubernetes configuration.")

# Create Kubernetes API clients
core_v1_api = client.CoreV1Api()

# Global caches
agentconfigs = {}        # Mapping from AgentConfig name to discoveryLabel
matching_namespaces = set()  # Set of namespaces matching any AgentConfig's discoveryLabel

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.watching.clusterwide = True
    logger.debug("Operator configured to watch cluster-wide.")

    # Use annotations for progress storage to avoid updating the status subresource
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage()
    logger.debug("Configured operator to use annotations for progress storage.")

    # Initialize the matching namespaces set
    initialize_matching_namespaces()

def initialize_matching_namespaces():
    # Clear existing matching namespaces
    matching_namespaces.clear()
    # Rebuild the matching namespaces based on current AgentConfigs
    if agentconfigs:
        for ns in core_v1_api.list_namespace().items:
            ns_labels = ns.metadata.labels or {}
            ns_name = ns.metadata.name
            for discovery_label in agentconfigs.values():
                key, value = discovery_label.split('=', 1)
                if ns_labels.get(key) == value:
                    matching_namespaces.add(ns_name)
                    logger.debug(f"Namespace {ns_name} added to matching namespaces.")
                    break  # Stop checking after the first match

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, namespace, **kwargs):
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label or '=' not in discovery_label:
        logger.error("discoveryLabel must be specified in 'key=value' format in AgentConfig.")
        raise kopf.PermanentError("discoveryLabel must be specified in 'key=value' format in AgentConfig.")
    logger.info(f"Processing AgentConfig: {name} with discoveryLabel: {discovery_label}")

    agentconfigs[name] = discovery_label

    # Rebuild the matching namespaces set
    initialize_matching_namespaces()

@kopf.on.delete('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig_delete(name, **kwargs):
    logger.info(f"Deleting AgentConfig: {name}")
    agentconfigs.pop(name, None)

    # Rebuild the matching namespaces set
    initialize_matching_namespaces()

@kopf.on.create('', 'v1', 'namespaces')
@kopf.on.update('', 'v1', 'namespaces')
def handle_namespace_event(body, name, **kwargs):
    ns_labels = body.get('metadata', {}).get('labels', {})
    logger.debug(f"Received event for Namespace: {name} with labels: {ns_labels}")

    # Check if the namespace matches any AgentConfig's discoveryLabel
    namespace_matched = False
    for discovery_label in agentconfigs.values():
        key, value = discovery_label.split('=', 1)
        if ns_labels.get(key) == value:
            matching_namespaces.add(name)
            logger.debug(f"Namespace {name} matches discoveryLabel {discovery_label} and added to matching namespaces.")
            namespace_matched = True
            break
    if not namespace_matched and name in matching_namespaces:
        matching_namespaces.discard(name)
        logger.debug(f"Namespace {name} no longer matches any discoveryLabel and removed from matching namespaces.")

@kopf.on.delete('', 'v1', 'namespaces')
def handle_namespace_delete(name, **kwargs):
    matching_namespaces.discard(name)
    logger.debug(f"Removed namespace {name} from matching namespaces.")

@kopf.on.event('', 'v1', 'services')
def handle_service_event(event, namespace, **kwargs):
    service = event.get('object')
    if not service:
        return  # No service object found in the event
    service_name = service['metadata']['name']
    logger.debug(f"Received event for Service: {service_name} in Namespace: {namespace}")

    # Check if the service's namespace is in the set of matching namespaces
    if namespace in matching_namespaces:
        logger.info(f"Service {service_name} in namespace {namespace} matches a discoveryLabel.")
        print_service_details(service)
    else:
        logger.debug(f"Service {service_name} in namespace {namespace} does not match any discoveryLabel.")

def print_service_details(service):
    """
    Print detailed information about a Kubernetes service.
    """
    metadata = service.get('metadata', {})
    spec = service.get('spec', {})
    logger.info(f"Service Name: {metadata.get('name')}")
    logger.info(f"Namespace: {metadata.get('namespace')}")
    logger.info(f"Labels: {metadata.get('labels')}")
    logger.info(f"Annotations: {metadata.get('annotations')}")
    logger.info(f"Cluster IP: {spec.get('clusterIP')}")
    logger.info(f"Ports: {spec.get('ports')}")
    logger.info(f"Type: {spec.get('type')}")
    logger.info(f"Session Affinity: {spec.get('sessionAffinity')}")
    if spec.get('selector'):
        logger.info(f"Selector: {spec.get('selector')}")
