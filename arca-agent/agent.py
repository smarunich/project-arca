import os
import kopf
from kubernetes import client, config as kube_config
import logging
from tetrate import TSBConnection, Workspace, Tenant, Organization

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
    # For local testing outside the cluster
    kube_config.load_kube_config()

# Create Kubernetes API client
core_v1_api = client.CoreV1Api()

# Global variables
tsb = None
current_config = {}

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings."""
    settings.execution.max_workers = 10

def process_agentconfig(name: str, spec: dict) -> dict:
    """
    Process AgentConfig and return a structured configuration.
    Raises ValueError if configuration is invalid.
    """
    config = {
        'name': name,
        'discovery_label': None,
        'discovery_key': None,
        'discovery_value': None,
        'tsb': None
    }

    # Process discovery label
    discovery_label = spec.get('discoveryLabel')
    if discovery_label:
        try:
            key, value = discovery_label.split('=', 1)
            config['discovery_label'] = discovery_label
            config['discovery_key'] = key
            config['discovery_value'] = value
        except ValueError:
            raise ValueError(f"Invalid discoveryLabel format: '{discovery_label}'")

    # Process TSB configuration
    tsb_config = spec.get('tetrate')
    if tsb_config:
        config['tsb'] = {
            'endpoint': tsb_config.get('endpoint'),
            'api_token': tsb_config.get('apiToken'),
            'username': tsb_config.get('username'),
            'password': tsb_config.get('password'),
            'organization': tsb_config.get('organization'),
            'tenant': tsb_config.get('tenant')
        }

    return config

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, namespace, logger, **kwargs):
    """
    Handle creation and updates of AgentConfig resources.
    Initializes or updates both TSB connection and discovery configuration.
    """
    global tsb, current_config

    try:
        # Process the entire configuration
        new_config = process_agentconfig(name, spec)
        
        # Initialize/update TSB connection if TSB config is present
        if new_config['tsb']:
            tsb = TSBConnection(
                endpoint=new_config['tsb']['endpoint'],
                api_token=new_config['tsb']['api_token'],
                username=new_config['tsb']['username'],
                password=new_config['tsb']['password'],
                organization=new_config['tsb']['organization'],
                tenant=new_config['tsb']['tenant']
            )
            logger.info(f"TSB connection initialized for AgentConfig '{name}'")

        # Update the current configuration
        current_config = new_config
        logger.info(f"Configuration updated for AgentConfig '{name}'")

    except Exception as e:
        logger.error(f"Failed to process AgentConfig '{name}': {str(e)}")
        raise kopf.PermanentError(f"Configuration failed: {str(e)}")

@kopf.index('operator.arca.io', 'v1alpha1', 'agentconfigs')
def agentconfigs_indexer(body, **kwargs):
    """Index AgentConfig resources based on their discoveryLabel."""
    try:
        config = process_agentconfig(
            body['metadata']['name'],
            body.get('spec', {})
        )
        if config['discovery_key'] and config['discovery_value']:
            return [(config['discovery_key'], config['discovery_value'])]
    except Exception as e:
        logger.error(f"Failed to index AgentConfig: {str(e)}")
    return []

@kopf.on.create('', 'v1', 'namespaces')
@kopf.on.update('', 'v1', 'namespaces')
def namespace_event_handler(spec, name, namespace, logger, indexes, **kwargs):
    """Handle namespace creation and update events."""
    if not current_config:
        logger.warning("No active configuration available")
        return

    namespace_labels = kwargs['body'].get('metadata', {}).get('labels', {})
    namespace_name = kwargs['body']['metadata']['name']

    for key, value in namespace_labels.items():
        agentconfigs = indexes['agentconfigs_indexer'].get((key, value), [])
        for agentconfig_body in agentconfigs:
            agentconfig_name = agentconfig_body['metadata']['name']
            logger.debug(f"Processing namespace '{namespace_name}' for AgentConfig '{agentconfig_name}'")
            process_namespace_services(namespace_name, agentconfig_name)

def process_namespace_services(namespace_name, agentconfig_name):
    """Process services in the given namespace."""
    try:
        services = core_v1_api.list_namespaced_service(namespace_name)
        for svc in services.items:
            service_name = svc.metadata.name
            logger.info(f"Processing Service '{service_name}' in namespace '{namespace_name}'")
            process_service(namespace_name, service_name, agentconfig_name)
    except Exception as e:
        logger.error(f"Error processing services in namespace '{namespace_name}': {str(e)}")

def process_service(namespace_name, service_name, agentconfig_name):
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
    if not current_config or not current_config.get('discovery_label'):
        logger.warning(f"No valid configuration for reconciliation")
        return

    try:
        logger.info(f"Reconciling with label '{current_config['discovery_label']}'")
        namespaces = core_v1_api.list_namespace(
            label_selector=f"{current_config['discovery_key']}={current_config['discovery_value']}"
        )
        for ns in namespaces.items:
            namespace_name = ns.metadata.name
            logger.debug(f"Reconciling namespace '{namespace_name}'")
            process_namespace_services(namespace_name, name)
    except Exception as e:
        logger.error(f"Reconciliation failed: {str(e)}")
