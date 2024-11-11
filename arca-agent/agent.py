import os
import kopf
from kubernetes import client, config as kube_config
import logging
from tetrate import TetrateConnection, Organization, Tenant, Workspace
import time
from requests.exceptions import RequestException

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logger = logging.getLogger('arca-agent')
if not logger.handlers:
    handler = logging.StreamHandler()
    formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
logger.setLevel(log_level)

# Load the Kubernetes configuration
try:
    kube_config.load_incluster_config()
    logger.debug("Loaded in-cluster Kubernetes configuration.")
except kube_config.ConfigException:
    kube_config.load_kube_config()
    logger.debug("Loaded local Kubernetes configuration.")

# Create Kubernetes API client
core_v1_api = client.CoreV1Api()

# Global variables
tetrate = None
agent_config = None

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings."""
    settings.execution.max_workers = 10
    logger.debug("Operator settings configured with max_workers=10.")

def process_agentconfig(spec: dict) -> dict:
    """Process AgentConfig and return a structured configuration."""
    logger.debug(f"Processing AgentConfig spec: {spec}")
    config = {
        'discovery_label': spec.get('discoveryLabel'),
        'tetrate': spec.get('tetrate')
    }

    if config['discovery_label']:
        try:
            key, value = config['discovery_label'].split('=', 1)
            config.update({'discovery_key': key, 'discovery_value': value})
            logger.debug(f"Parsed discovery label: key={key}, value={value}")
        except ValueError:
            logger.error(f"Invalid discoveryLabel format: '{config['discovery_label']}'")
            raise ValueError(f"Invalid discoveryLabel format: '{config['discovery_label']}'")

    return config

def initialize_tetrate_connection(tetrate_config):
    """Initialize Tetrate connection if configuration is present."""
    global tetrate
    if tetrate_config:
        logger.debug(f"Initializing Tetrate connection with config: {tetrate_config}")
        tetrate = TetrateConnection(
            endpoint=tetrate_config.get('endpoint'),
            api_token=tetrate_config.get('apiToken'),
            username=tetrate_config.get('username'),
            password=tetrate_config.get('password'),
            organization=tetrate_config.get('organization'),
            tenant=tetrate_config.get('tenant')
        )
        logger.info("Tetrate connection initialized")

def create_workspace(namespace_name):
    """Create a workspace in Tetrate based on the namespace name with retry logic."""
    if not tetrate:
        logger.warning("Tetrate connection not initialized")
        return

    retries = 3
    for attempt in range(retries):
        try:
            logger.debug(f"Attempting to create workspace for namespace: {namespace_name}")
            organization = Organization(tetrate.organization)
            tenant = Tenant(organization, tetrate.tenant)
            workspace = Workspace(tenant=tenant, name=namespace_name)
            response = workspace.create()
            logger.info(f"Workspace '{namespace_name}' created successfully: {response}")
            break
        except RequestException as e:
            logger.error(f"Request failed on attempt {attempt + 1}/{retries} for workspace '{namespace_name}': {str(e)}")
            time.sleep(2 ** attempt)  # Exponential backoff
        except Exception as e:
            logger.error(f"Error creating workspace '{namespace_name}': {str(e)}")
            break

def delete_workspace(namespace_name):
    """Delete a workspace in Tetrate for the given namespace."""
    if not tetrate:
        logger.warning("Tetrate connection not initialized")
        return

    try:
        organization = Organization(tetrate.organization)
        tenant = Tenant(organization, tetrate.tenant)
        workspace = Workspace(tenant=tenant, name=namespace_name)
        response = workspace.delete()
        logger.info(f"Workspace '{namespace_name}' deleted successfully: {response}")
    except Exception as e:
        logger.error(f"Error deleting workspace '{namespace_name}': {str(e)}")

def select_namespaces_by_discovery_label():
    """Retrieve namespaces matching the discoveryLabel in AgentConfig."""
    if not agent_config or not agent_config.get('discovery_key') or not agent_config.get('discovery_value'):
        logger.warning("No valid discovery label configuration found")
        return []

    label_selector = f"{agent_config['discovery_key']}={agent_config['discovery_value']}"
    logger.debug(f"Selecting namespaces with label selector: {label_selector}")

    try:
        namespaces = core_v1_api.list_namespace(label_selector=label_selector)
        selected_namespaces = [ns.metadata.name for ns in namespaces.items]
        logger.info(f"Namespaces matching discovery label '{label_selector}': {selected_namespaces}")
        return selected_namespaces
    except Exception as e:
        logger.error(f"Error retrieving namespaces with label '{label_selector}': {str(e)}")
        return []

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, **kwargs):
    """Handle creation and updates of AgentConfig resources."""
    global agent_config

    try:
        logger.debug(f"Handling AgentConfig with spec: {spec}")
        agent_config = process_agentconfig(spec)
        initialize_tetrate_connection(agent_config['tetrate'])
        logger.info("Configuration updated for AgentConfig")
    except Exception as e:
        logger.error(f"Failed to process AgentConfig: {str(e)}")
        raise kopf.PermanentError(f"Configuration failed: {str(e)}")

@kopf.index('operator.arca.io', 'v1alpha1', 'agentconfigs')
def agentconfigs_indexer(body, **kwargs):
    """Index AgentConfig resources based on their discoveryLabel."""
    try:
        logger.debug(f"Indexing AgentConfig: {body}")
        config = process_agentconfig(body.get('spec', {}))
        if config.get('discovery_key') and config.get('discovery_value'):
            logger.debug(f"Indexed discovery key-value: {config['discovery_key']}={config['discovery_value']}")
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
    logger.debug(f"Handling namespace event for: {namespace_name} with labels: {namespace_labels}")

    for key, value in namespace_labels.items():
        agentconfigs = indexes['agentconfigs_indexer'].get((key, value), [])
        if agentconfigs:
            logger.debug(f"Namespace '{namespace_name}' matches AgentConfig discovery label.")
            process_namespace_services(namespace_name)
            create_workspace(namespace_name)

def process_namespace_services(namespace_name):
    """Process services in the given namespace."""
    try:
        logger.debug(f"Listing services in namespace: {namespace_name}")
        services = core_v1_api.list_namespaced_service(namespace_name)
        for svc in services.items:
            service_name = svc.metadata.name
            logger.info(f"Service '{service_name}' found in namespace '{namespace_name}'")
    except Exception as e:
        logger.error(f"Error processing services in namespace '{namespace_name}': {str(e)}")

@kopf.timer('operator.arca.io', 'v1alpha1', 'agentconfigs', interval=60, sharp=True)
def reconcile_agentconfig(spec, logger, **kwargs):
    """Periodically reconcile namespaces and services."""
    if not agent_config or not agent_config.get('discovery_label'):
        logger.warning("No valid configuration for reconciliation")
        return

    try:
        logger.info(f"Reconciling with label '{agent_config['discovery_label']}'")
        namespaces = select_namespaces_by_discovery_label()
        for namespace_name in namespaces:
            logger.debug(f"Reconciling namespace '{namespace_name}'")
            process_namespace_services(namespace_name)
            create_workspace(namespace_name)
    except Exception as e:
        logger.error(f"Reconciliation failed: {str(e)}")
