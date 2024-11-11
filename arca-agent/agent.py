import os
import kopf
from kubernetes import client, config as kube_config
import logging
from tetrate import TetrateConnection, Organization, Tenant, Workspace
import requests

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

AGENT_CONFIG_NAME = "default"  # Default name for the AgentConfig resource
FINALIZER = 'operator.arca.io/cleanup'  # Define a proper finalizer name

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings."""
    settings.execution.max_workers = 10
    settings.persistence.finalizer = FINALIZER  # Set the finalizer
    settings.posting.enabled = True
    logger.debug(f"Operator settings configured with finalizer: {FINALIZER}")

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
    if not tetrate_config:
        logger.error("No Tetrate configuration provided")
        return False

    # Check endpoint
    if not tetrate_config.get('endpoint'):
        logger.error("Tetrate endpoint is required")
        return False

    # Check authentication methods
    has_valid_auth = False
    if tetrate_config.get('apiToken'):
        has_valid_auth = True
    elif tetrate_config.get('username') and tetrate_config.get('password'):
        has_valid_auth = True

    if not has_valid_auth:
        logger.error("Either apiToken or username/password combination is required for Tetrate authentication")
        return False

    try:
        logger.debug(f"Initializing Tetrate connection with config: {tetrate_config}")
        # Create new TetrateConnection instance
        TetrateConnection(
            endpoint=tetrate_config.get('endpoint'),
            api_token=tetrate_config.get('apiToken'),
            username=tetrate_config.get('username'),
            password=tetrate_config.get('password'),
            organization=tetrate_config.get('organization'),
            tenant=tetrate_config.get('tenant')
        )
        
        # Test the connection
        org = Organization(TetrateConnection.get_instance().organization)
        org.get()  # This will throw an error if credentials are invalid
        
        logger.info("Tetrate connection initialized and verified successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize Tetrate connection: {str(e)}")
        raise

def create_workspace(namespace_name):
    """Create a workspace in Tetrate based on the namespace name if it doesn't exist."""
    try:
        tetrate = TetrateConnection.get_instance()
        logger.debug(f"Checking workspace for namespace: {namespace_name}")
        
        # Initialize objects
        organization = Organization(tetrate.organization)
        tenant = Tenant(organization, tetrate.tenant)
        
        # Configure workspace data
        workspace_data = {
            'namespaceSelector': {
                'names': [f'{agent_config['tetrate'].get('clusterName')}/{namespace_name}']  # Match the specific namespace
            },
            'configGenerationMetadata': {
                'labels': {
                    "arca.io/managed": "true",
                    "arca.io/namespace": namespace_name
                }
            },
            'description': f'Workspace for namespace {namespace_name}',
            'displayName': f'Workspace {namespace_name}'
        }
        
        # Create workspace with custom configuration
        workspace = Workspace(tenant=tenant, name=namespace_name, workspace_data=workspace_data)
        
        try:
            # Check if workspace exists
            existing = workspace.get()
            logger.info(f"Workspace '{namespace_name}' already exists: {existing}")
            return
        except requests.exceptions.HTTPError as e:
            if e.response.status_code != 404:  # If error is not "Not Found"
                raise
            
            # Workspace doesn't exist, create it
            logger.info(f"Creating new workspace for namespace: {namespace_name}")
            response = workspace.create()
            logger.info(f"Workspace '{namespace_name}' created successfully: {response}")
            
    except ValueError as e:
        logger.warning(f"Tetrate connection not initialized: {str(e)}")
    except Exception as e:
        logger.error(f"Error handling workspace for namespace '{namespace_name}': {str(e)}")

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.resume('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, meta, status, **kwargs):
    """Handle creation and updates of AgentConfig resources."""
    if name != AGENT_CONFIG_NAME:
        logger.warning(f"Ignoring AgentConfig '{name}' as it's not the default name '{AGENT_CONFIG_NAME}'")
        return

    global agent_config
    try:
        logger.debug(f"Handling AgentConfig with spec: {spec}")
        agent_config = process_agentconfig(spec)
        initialize_tetrate_connection(agent_config['tetrate'])
        logger.info("Configuration updated for AgentConfig")
    except Exception as e:
        logger.error(f"Failed to process AgentConfig: {str(e)}")
        raise kopf.PermanentError(f"Configuration failed: {str(e)}")

@kopf.on.delete('operator.arca.io', 'v1alpha1', 'agentconfigs')
def delete_agentconfig(spec, name, **kwargs):
    """Handle deletion of AgentConfig resources."""
    if name != AGENT_CONFIG_NAME:
        return
    
    global agent_config, tetrate
    logger.info(f"Cleaning up AgentConfig: {name}")
    agent_config = None
    tetrate = None

@kopf.on.event('', 'v1', 'namespaces')
def watch_namespaces(event, name, meta, logger, **kwargs):
    """Watch for namespace events and create workspaces accordingly."""
    if not agent_config or not agent_config.get('discovery_label'):
        return
    
    try:
        # Parse discovery label
        key, value = agent_config['discovery_label'].split('=')
        
        # Get namespace labels
        namespace_labels = meta.get('labels', {})
        has_required_label = namespace_labels.get(key) == value
        
        # Handle different event types
        event_type = event['type']
        logger.debug(f"Processing namespace event: {event_type} for {name}, has_label={has_required_label}")
        
        if event_type == 'ADDED' and has_required_label:
            # New namespace with the required label
            logger.info(f"New namespace {name} created with required label")
            create_workspace(name)
            
        elif event_type == 'MODIFIED':
            # Check if label was added or removed
            try:
                old_labels = event['old']['metadata']['labels']
                had_required_label = old_labels.get(key) == value
            except (KeyError, TypeError):
                had_required_label = False
            
            if not had_required_label and has_required_label:
                # Label was added
                logger.info(f"Required label added to namespace {name}")
                create_workspace(name)
            elif had_required_label and not has_required_label:
                # Label was removed
                logger.info(f"Required label removed from namespace {name}")
                # Optionally handle workspace cleanup here
                
    except Exception as e:
        logger.error(f"Error processing namespace {name}: {str(e)}")
        raise kopf.TemporaryError(f"Failed to process namespace: {str(e)}", delay=60)

@kopf.timer('operator.arca.io', 'v1alpha1', 'agentconfigs',
            interval=300.0,
            sharp=True,
            idle=60.0,
            initial_delay=60.0)
def periodic_workspace_reconciliation(spec, name, logger, **kwargs):
    """Periodically reconcile workspaces to ensure consistency."""
    if name != AGENT_CONFIG_NAME:
        return
        
    if not agent_config or not agent_config.get('discovery_label'):
        logger.warning("No valid agent configuration or discovery label found")
        return

    try:
        key, value = agent_config['discovery_label'].split('=')
        namespaces = core_v1_api.list_namespace(label_selector=f"{key}={value}").items
        logger.info(f"Reconciliation: Found namespaces with label {agent_config['discovery_label']}: "
                   f"{[ns.metadata.name for ns in namespaces]}")
        
        for ns in namespaces:
            create_workspace(ns.metadata.name)
                
    except Exception as e:
        logger.error(f"Error during periodic reconciliation: {str(e)}")
        raise kopf.TemporaryError(f"Reconciliation failed: {str(e)}", delay=300)