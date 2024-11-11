import os
import kopf
from kubernetes import client, config as kube_config
import logging
from tetrate import TSBConnection

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logger = logging.getLogger('arca-agent')
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(log_level)

# Load the Kubernetes configuration
try:
    kube_config.load_incluster_config()
except kube_config.ConfigException:
    kube_config.load_kube_config()

# Create Kubernetes API client
core_v1_api = client.CoreV1Api()

# Global variables
tsb = None
agent_config = None
DEFAULT_CONFIG_NAME = "default"

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings."""
    settings.execution.max_workers = 10

def process_agentconfig(name: str, spec: dict) -> dict:
    """Process AgentConfig and return a structured configuration."""
    config = {
        'name': name,
        'discovery_label': spec.get('discoveryLabel'),
        'tsb': spec.get('tetrate')
    }

    if config['discovery_label']:
        try:
            key, value = config['discovery_label'].split('=', 1)
            config.update({'discovery_key': key, 'discovery_value': value})
        except ValueError:
            raise ValueError(f"Invalid discoveryLabel format: '{config['discovery_label']}'")

    return config

def initialize_tsb_connection(tsb_config):
    """Initialize TSB connection if configuration is present."""
    global tsb
    if tsb_config:
        tsb = TSBConnection(
            endpoint=tsb_config.get('endpoint'),
            api_token=tsb_config.get('apiToken'),
            username=tsb_config.get('username'),
            password=tsb_config.get('password'),
            organization=tsb_config.get('organization'),
            tenant=tsb_config.get('tenant')
        )
        logger.info("TSB connection initialized")

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, **kwargs):
    """Handle creation and updates of AgentConfig resources."""
    global agent_config

    if name != DEFAULT_CONFIG_NAME:
        logger.info(f"Ignoring non-default AgentConfig '{name}'")
        return

    try:
        agent_config = process_agentconfig(name, spec)
        initialize_tsb_connection(agent_config['tsb'])
        logger.info(f"Configuration updated for AgentConfig '{name}'")
    except Exception as e:
        logger.error(f"Failed to process AgentConfig '{name}': {str(e)}")
        raise kopf.PermanentError(f"Configuration failed: {str(e)}")

@kopf.on.delete('operator.arca.io', 'v1alpha1', 'agentconfigs')
def delete_agentconfig(name, **kwargs):
    """Handle deletion of AgentConfig resources."""
    global agent_config

    if name == DEFAULT_CONFIG_NAME:
        agent_config = None
        logger.info("Default AgentConfig removed")

@kopf.index('operator.arca.io', 'v1alpha1', 'agentconfigs')
def agentconfigs_indexer(body, **kwargs):
    """Index AgentConfig resources based on their discoveryLabel."""
    try:
        name = body['metadata'].get('name')
        if name == DEFAULT_CONFIG_NAME:
            config = process_agentconfig(name, body.get('spec', {}))
            if config.get('discovery_key') and config.get('discovery_value'):
                return [(config['discovery_key'], config['discovery_value'])]
    except Exception as e:
        logger.error(f"Failed to index AgentConfig: {str(e)}")
    return []

@kopf.on.create('', 'v1', 'namespaces')
@kopf.on.update('', 'v1', 'namespaces')
def namespace_event_handler(name, namespace, logger, indexes, **kwargs):
    """Handle namespace creation and update events."""
    if not agent_config:
        logger.warning("No configuration available")
        return

    namespace_labels = kwargs['body'].get('metadata', {}).get('labels', {})
    namespace_name = kwargs['body']['metadata']['name']

    for key, value in namespace_labels.items():
        agentconfigs = indexes['agentconfigs_indexer'].get((key, value), [])
        for agentconfig_body in agentconfigs:
            if agentconfig_body['metadata'].get('name') == DEFAULT_CONFIG_NAME:
                logger.debug(f"Processing namespace '{namespace_name}'")
                process_namespace_services(namespace_name)

def process_namespace_services(namespace_name):
    """Process services in the given namespace."""
    try:
        services = core_v1_api.list_namespaced_service(namespace_name)
        for svc in services.items:
            service_name = svc.metadata.name
            logger.info(f"Processing Service '{service_name}' in namespace '{namespace_name}'")
            process_service(namespace_name, service_name)
    except Exception as e:
        logger.error(f"Error processing services in namespace '{namespace_name}': {str(e)}")

def process_service(namespace_name, service_name):
    """Process an individual service."""
    if not tsb:
        logger.warning("TSB connection not initialized")
        return

    try:
        # Add your service processing logic here
        logger.debug(f"Processing Service '{service_name}' in namespace '{namespace_name}'")
    except Exception as e:
        logger.error(f"Error processing service '{service_name}': {str(e)}")

@kopf.timer('operator.arca.io', 'v1alpha1', 'agentconfigs', interval=60, sharp=True)
def reconcile_agentconfig(spec, name, logger, **kwargs):
    """Periodically reconcile namespaces and services."""
    if not agent_config or not agent_config.get('discovery_label'):
        logger.warning("No valid configuration for reconciliation")
        return

    try:
        logger.info(f"Reconciling with label '{agent_config['discovery_label']}'")
        namespaces = core_v1_api.list_namespace(
            label_selector=f"{agent_config['discovery_key']}={agent_config['discovery_value']}"
        )
        for ns in namespaces.items:
            namespace_name = ns.metadata.name
            logger.debug(f"Reconciling namespace '{namespace_name}'")
            process_namespace_services(namespace_name)
    except Exception as e:
        logger.error(f"Reconciliation failed: {str(e)}")
