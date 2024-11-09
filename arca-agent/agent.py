import os
import kopf
import kubernetes
from kubernetes import client, config
import logging

# Configure logging
log_level = os.getenv('LOG_LEVEL').upper()
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
namespaces_cache = {}    # Mapping from namespace name to labels

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.watching.clusterwide = True
    logger.debug("Operator configured to watch cluster-wide.")

    # Use annotations for progress storage to avoid updating the status subresource
    settings.persistence.progress_storage = kopf.AnnotationsProgressStorage()
    logger.debug("Configured operator to use annotations for progress storage.")

    # Initialize the namespaces cache
    namespaces = core_v1_api.list_namespace()
    for ns in namespaces.items:
        labels = ns.metadata.labels or {}
        namespaces_cache[ns.metadata.name] = labels
        logger.debug(f"Cached namespace {ns.metadata.name} labels: {labels}")

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, namespace, **kwargs):
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label or '=' not in discovery_label:
        logger.error("discoveryLabel must be specified in 'key=value' format in AgentConfig.")
        raise kopf.PermanentError("discoveryLabel must be specified in 'key=value' format in AgentConfig.")
    logger.info(f"Processing AgentConfig: {name} with discoveryLabel: {discovery_label}")
    agentconfigs[name] = discovery_label

@kopf.on.delete('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig_delete(name, **kwargs):
    logger.info(f"Deleting AgentConfig: {name}")
    agentconfigs.pop(name, None)

@kopf.on.create('', 'v1', 'namespaces')
@kopf.on.update('', 'v1', 'namespaces')
def handle_namespace_event(body, name, **kwargs):
    labels = body.get('metadata', {}).get('labels', {})
    namespaces_cache[name] = labels
    logger.debug(f"Updated namespace cache for {name}: {labels}")

@kopf.on.delete('', 'v1', 'namespaces')
def handle_namespace_delete(name, **kwargs):
    namespaces_cache.pop(name, None)
    logger.debug(f"Removed namespace {name} from cache")

@kopf.on.event('', 'v1', 'services')
def handle_service_event(event, namespace, **kwargs):
    service = event.get('object')
    if not service:
        return  # No service object found in the event
    service_name = service['metadata']['name']
    logger.debug(f"Received event for Service: {service_name} in Namespace: {namespace}")

    # Get the labels of the namespace
    namespace_labels = namespaces_cache.get(namespace, {})
    if not namespace_labels:
        logger.debug(f"No labels found for namespace {namespace}")
        return

    # For each AgentConfig, check if the namespace labels match the discoveryLabel
    for agentconfig_name, discovery_label in agentconfigs.items():
        key, value = discovery_label.split('=', 1)
        if namespace_labels.get(key) == value:
            logger.info(f"Service {service_name} in namespace {namespace} matches AgentConfig {agentconfig_name}")
            print_service_details(service)
            break  # Stop checking after the first match
        else:
            logger.debug(f"Namespace {namespace} does not match discoveryLabel {discovery_label} for AgentConfig {agentconfig_name}")

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
