import os
import kopf
from kubernetes import client, config as kube_config
import logging
from tetrate import TetrateConnection, Organization, Tenant, Workspace

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
    settings.persistence.finalizer = None  # Disable status reporting
    logger.debug("Operator settings configured with max_workers=10 and status reporting disabled.")

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
    """Create a workspace in Tetrate based on the namespace name."""
    if not tetrate:
        logger.warning("Tetrate connection not initialized")
        return

    try:
        logger.debug(f"Creating workspace for namespace: {namespace_name}")
        # Create organization and tenant objects
        organization = Organization(tetrate.organization)
        tenant = Tenant(organization, tetrate.tenant)

        # Initialize the Workspace object
        workspace = Workspace(tenant=tenant, name=namespace_name)
        response = workspace.create()
        logger.info(f"Workspace '{namespace_name}' created successfully: {response}")
    except Exception as e:
        logger.error(f"Error creating workspace '{namespace_name}': {str(e)}")

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, **kwargs):
    """Handle creation and updates of AgentConfig resources."""
    global agent_config

    try:
        logger.debug(f"Handling AgentConfig with spec: {spec}")
        agent_config = process_agentconfig(spec)
        initialize_tetrate_connection(agent_config['tetrate'])
        list_namespaces_and_print_services(agent_config['discovery_label'])
        logger.info("Configuration updated for AgentConfig")
    except Exception as e:
        logger.error(f"Failed to process AgentConfig: {str(e)}")
        raise kopf.PermanentError(f"Configuration failed: {str(e)}")

@kopf.on.create('', 'v1', 'namespaces')
@kopf.on.update('', 'v1', 'namespaces')
@kopf.on.resume('', 'v1', 'namespaces')

def list_namespaces_and_print_services(discovery_label):
    """List namespaces using the discovery label and print services."""
    try:
        key, value = discovery_label.split('=')
        namespaces = core_v1_api.list_namespace(label_selector=f"{key}={value}").items
        logger.info(f"Namespaces with label {discovery_label}: {[ns.metadata.name for ns in namespaces]}")
        
        for ns in namespaces:
            services = core_v1_api.list_namespaced_service(ns.metadata.name).items
            logger.info(f"Services in namespace {ns.metadata.name}: {[svc.metadata.name for svc in services]}")
    except Exception as e:
        logger.error(f"Error listing namespaces or services: {str(e)}")