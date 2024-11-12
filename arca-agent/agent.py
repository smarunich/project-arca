import os
import kopf
from kubernetes import client, config as kube_config
import logging
from tetrate import TetrateConnection, Organization, Tenant, Workspace, WorkspaceSetting, GatewayGroup, Gateway

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

# Service annotation constants
EXPOSE_ANNOTATION = 'arca.io/expose'
DOMAIN_ANNOTATION = 'arca.io/domain'
PATH_ANNOTATION = 'arca.io/path'

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
        'service_fabric': spec.get('serviceFabric'),
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

    if not config['service_fabric']:
        logger.warning("serviceFabric not specified in config")
        config['service_fabric'] = config.get('tetrate', {}).get('clusterName', '*')

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

def workspace_manager(namespace_name):
    """Create or update a workspace and its settings in Tetrate."""
    try:
        tetrate = TetrateConnection.get_instance()
        logger.debug(f"Checking workspace for namespace: {namespace_name}")
        
        # Initialize objects
        organization = Organization(tetrate.organization)
        tenant = Tenant(organization, tetrate.tenant)
        
        # Configure desired workspace data with both clusterName and serviceFabric
        desired_workspace_data = {
            'namespaceSelector': {
                'names': [
                    f'{agent_config["tetrate"].get("clusterName", "*")}/{namespace_name}',
                    f'{agent_config.get("service_fabric", "*")}/{namespace_name}'
                ]
            },
            'configGenerationMetadata': {
                'labels': {
                    "arca.io/managed": "true",
                    "arca.io/namespace": namespace_name,
                    "arca.io/cluster": agent_config["tetrate"].get("clusterName", ""),
                    "arca.io/service-fabric": agent_config.get("service_fabric", "")
                }
            },
            'description': f'Workspace for namespace {namespace_name}',
            'displayName': f'Workspace {namespace_name}'
        }
        
        # Create workspace instance and create/update it
        workspace = Workspace(tenant=tenant, name=namespace_name)
        workspace_response = workspace.create_or_update(desired_workspace_data)
        logger.info(f"Workspace '{namespace_name}' created/updated successfully")
        
        # Create or update workspace settings
        workspace_setting = WorkspaceSetting(workspace=workspace, name='default')
        
        # Configure east-west gateway settings
        workspace_settings = {
            'defaultEastWestGatewaySettings': [{
                'workloadSelector': {
                    'labels': {
                        'app': 'arca-eastwest-gateway'
                    },
                    'namespace': 'arca-system'
                },
                'exposedServices': [
                    {
                        'serviceLabels': {
                            'arca.io/managed': 'true'
                        }
                    }
                ]
            }],
            'defaultSecuritySetting': {
                'authenticationSettings': {
                    'trafficMode': 'REQUIRED'
                }
            }
        }
        
        try:
            # Create or update the workspace settings
            settings_response = workspace_setting.create_or_update(workspace_settings)
            logger.info(f"Workspace settings for '{namespace_name}' created/updated successfully")
            
            # Create or update gateway group
            gateway_group = GatewayGroup(workspace=workspace, name=f"{namespace_name}-gateways")
            
            # Configure gateway group with serviceFabric
            gateway_group_config = {
                'displayName': f'Gateway Group for {namespace_name}',
                'configMode': 'BRIDGED',
                'namespaceSelector': {
                    'names': [
                        f'{agent_config.get("service_fabric", "*")}/{namespace_name}'
                    ]
                },
                'configGenerationMetadata': {
                    'labels': {
                        'arca.io/managed': 'true',
                        'arca.io/namespace': namespace_name,
                        'arca.io/cluster': agent_config["tetrate"].get("clusterName", ""),
                        'arca.io/service-fabric': agent_config.get("service_fabric", "")
                    }
                }
            }
            
            # Create or update the gateway group
            gateway_response = gateway_group.create_or_update(gateway_group_config)
            logger.info(f"Gateway group for '{namespace_name}' created/updated successfully")
            
        except Exception as e:
            logger.error(f"Error creating/updating workspace resources for '{namespace_name}': {str(e)}")
            raise
            
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
            workspace_manager(name)
            
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
                workspace_manager(name)
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
            workspace_manager(ns.metadata.name)
                
    except Exception as e:
        logger.error(f"Error during periodic reconciliation: {str(e)}")
        raise kopf.TemporaryError(f"Reconciliation failed: {str(e)}", delay=300)

def handle_service_exposure(service, namespace_name, workspace):
    """Handle service exposure through gateway."""
    try:
        annotations = service.metadata.annotations or {}
        
        # Check if service should be exposed
        if annotations.get(EXPOSE_ANNOTATION) != 'true':
            return
            
        # Get domain and path from annotations
        domain = annotations.get(DOMAIN_ANNOTATION)
        path = annotations.get(PATH_ANNOTATION, '/')
        
        if not domain:
            logger.warning(f"Service {service.metadata.name} missing domain annotation")
            return
            
        # Get or create gateway group
        gateway_group = GatewayGroup(
            workspace=workspace,
            name=f"{namespace_name}-gateways"
        )
        
        # Configure gateway group
        gateway_group_config = {
            'displayName': f'Gateway Group for {namespace_name}',
            'configMode': 'BRIDGED',
            'namespaceSelector': {
                'names': [
                    f'{agent_config.get("service_fabric", "*")}/{namespace_name}'
                ]
            },
            'configGenerationMetadata': {
                'labels': {
                    'arca.io/managed': 'true',
                    'arca.io/namespace': namespace_name
                }
            }
        }
        
        gateway_group.create_or_update(gateway_group_config)
        
        # Create or update gateway
        gateway = Gateway(
            group=gateway_group,
            name=f"{service.metadata.name}-gateway"
        )
        
        # Configure gateway
        gateway_config = {
            'workloadSelector': {
                'namespace': namespace_name,
                'labels': {
                    'app': f"{namespace_name}-gateway"
                }
            },
            'http': [
                {
                    'name': service.metadata.name,
                    'port': 80,
                    'hostname': domain,
                    'routing': {
                        'rules': [
                            {
                                'route': {
                                    'serviceDestination': {
                                        'host': f"{namespace_name}/{service.metadata.name}.{namespace_name}.svc.cluster.local",
                                        'port': service.spec.ports[0].port
                                    }
                                },
                                'match': [
                                    {
                                        'uri': {
                                            'prefix': path
                                        }
                                    }
                                ]
                            }
                        ]
                    }
                }
            ],
            'configGenerationMetadata': {
                'labels': {
                    'arca.io/managed': 'true',
                    'arca.io/service': service.metadata.name
                }
            }
        }
        
        gateway.create_or_update(gateway_config)
        logger.info(f"Gateway created/updated for service {service.metadata.name} in namespace {namespace_name}")
        
        # Update service status
        patch = {
            'metadata': {
                'annotations': {
                    'arca.io/status': 'exposed',
                    'arca.io/gateway': f"{service.metadata.name}-gateway",
                    'arca.io/url': f"http://{domain}{path}"
                }
            }
        }
        core_v1_api.patch_namespaced_service(
            name=service.metadata.name,
            namespace=namespace_name,
            body=patch
        )
        
    except Exception as e:
        logger.error(f"Error handling service exposure for {service.metadata.name}: {str(e)}")
        # Update service status with error
        patch = {
            'metadata': {
                'annotations': {
                    'arca.io/status': 'error',
                    'arca.io/error': str(e)
                }
            }
        }
        core_v1_api.patch_namespaced_service(
            name=service.metadata.name,
            namespace=namespace_name,
            body=patch
        )

@kopf.on.event('', 'v1', 'services')
def watch_services(event, name, meta, namespace, spec, **kwargs):
    """Watch for service events and handle gateway exposure."""
    if not agent_config or not agent_config.get('discovery_label'):
        return
        
    try:
        # First check if namespace has required label before processing service
        namespace_obj = core_v1_api.read_namespace(namespace)
        key, value = agent_config['discovery_label'].split('=')
        
        # Skip if namespace doesn't have the required label
        if namespace_obj.metadata.labels.get(key) != value:
            logger.debug(f"Skipping service {name} in namespace {namespace} - namespace doesn't have required label")
            return
            
        # Get service details
        service = core_v1_api.read_namespaced_service(name, namespace)
        
        try:
            # Get Tetrate connection
            tetrate = TetrateConnection.get_instance()
            
            # Get workspace for namespace
            organization = Organization(tetrate.organization)
            tenant = Tenant(organization, tetrate.tenant)
            workspace = Workspace(tenant=tenant, name=namespace)
            
            # Handle service exposure
            handle_service_exposure(service, namespace, workspace)
            
        except ValueError as e:
            logger.debug(f"Tetrate connection not initialized yet, skipping service {name}")
            return
        
    except client.exceptions.ApiException as e:
        if e.status == 404:
            logger.debug(f"Service {name} or namespace {namespace} not found")
            return
        logger.error(f"API error processing service {name} in namespace {namespace}: {str(e)}")
    except Exception as e:
        logger.error(f"Error processing service {name} in namespace {namespace}: {str(e)}")