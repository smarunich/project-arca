import os
import kopf
from kubernetes import client, config
import logging

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logger = logging.getLogger('arca-operator')
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(log_level)

# Load the Kubernetes configuration
try:
    config.load_incluster_config()
except config.ConfigException:
    # For local testing outside the cluster
    config.load_kube_config()

# Create Kubernetes API client
core_v1_api = client.CoreV1Api()

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """
    Configure operator settings if necessary.
    """
    # Adjust the number of concurrent workers if needed
    settings.execution.max_workers = 10

@kopf.index('operator.arca.io', 'v1alpha1', 'agentconfigs')
def agentconfigs_indexer(body, **kwargs):
    """
    Index AgentConfig resources based on their discoveryLabel.
    """
    discovery_label = body.get('spec', {}).get('discoveryLabel')
    if discovery_label:
        try:
            key, value = discovery_label.split('=', 1)
            return [ (key, value) ]
        except ValueError:
            logger.error(f"Invalid discoveryLabel format in AgentConfig '{body['metadata']['name']}': '{discovery_label}'")
            return []
    else:
        return []

@kopf.on.create('', 'v1', 'namespaces')
@kopf.on.update('', 'v1', 'namespaces')
def namespace_event_handler(spec, name, namespace, logger, indexes, **kwargs):
    """
    Handle namespace creation and update events.
    """
    namespace_labels = kwargs['body'].get('metadata', {}).get('labels', {})
    namespace_name = kwargs['body']['metadata']['name']

    # Find matching AgentConfigs based on the namespace labels
    for key, value in namespace_labels.items():
        agentconfigs = indexes['agentconfigs_indexer'].get((key, value), [])
        for agentconfig_body in agentconfigs:
            agentconfig_name = agentconfig_body['metadata']['name']
            discovery_label = agentconfig_body['spec']['discoveryLabel']
            logger.debug(f"Namespace '{namespace_name}' matches discoveryLabel '{discovery_label}' for AgentConfig '{agentconfig_name}'")
            process_namespace_services(namespace_name, agentconfig_name)

def process_namespace_services(namespace_name, agentconfig_name):
    """
    Process services in the given namespace.
    """
    try:
        services = core_v1_api.list_namespaced_service(namespace_name)
        for svc in services.items:
            service_name = svc.metadata.name
            logger.info(f"Processing Service '{service_name}' in namespace '{namespace_name}' for AgentConfig '{agentconfig_name}'")
            # Implement any additional processing or reconciliation logic for the services
            process_service(namespace_name, service_name, agentconfig_name)
    except Exception as e:
        logger.error(f"Error processing services in namespace '{namespace_name}': {str(e)}")

def process_service(namespace_name, service_name, agentconfig_name):
    """
    Process an individual service.
    """
    try:
        # Implement your service processing logic here
        # Ensure the logic is idempotent
        logger.debug(f"Processing Service '{service_name}' in namespace '{namespace_name}' for AgentConfig '{agentconfig_name}'")
    except Exception as e:
        logger.error(f"Error processing service '{service_name}' in namespace '{namespace_name}': {str(e)}")

@kopf.timer('operator.arca.io', 'v1alpha1', 'agentconfigs', interval=60, sharp=True)
def reconcile_agentconfig(spec, name, logger, **kwargs):
    """
    Periodically reconcile namespaces and services based on the AgentConfig's discoveryLabel.
    """
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label:
        logger.error(f"AgentConfig '{name}' missing discoveryLabel.")
        return

    try:
        key, value = discovery_label.split('=', 1)
    except ValueError:
        logger.error(f"Invalid discoveryLabel format in AgentConfig '{name}': '{discovery_label}'")
        return

    logger.info(f"Reconciling namespaces for AgentConfig '{name}' with discoveryLabel '{discovery_label}'")
    # List namespaces matching the discoveryLabel
    namespaces = core_v1_api.list_namespace(label_selector=f"{key}={value}")
    for ns in namespaces.items:
        namespace_name = ns.metadata.name
        logger.debug(f"Reconciling namespace '{namespace_name}' for AgentConfig '{name}'")
        process_namespace_services(namespace_name, name)
