import os
import kopf
from kubernetes import client, config as kube_config
import logging

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logger = logging.getLogger('arca-manager')
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
manager_config = None

MANAGER_CONFIG_NAME = "default"
FINALIZER = 'operator.arca.io/manager-cleanup'

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    """Configure operator settings."""
    settings.execution.max_workers = 10
    settings.persistence.finalizer = FINALIZER
    settings.posting.enabled = True
    logger.debug(f"Operator settings configured with finalizer: {FINALIZER}")

def process_managerconfig(spec: dict) -> dict:
    """Process ManagerConfig and return a structured configuration."""
    logger.debug(f"Processing ManagerConfig spec: {spec}")
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

def create_namespace(name: str, labels: dict = None, annotations: dict = None):
    """Create a namespace with given name and metadata."""
    try:
        namespace = client.V1Namespace(
            metadata=client.V1ObjectMeta(
                name=name,
                labels=labels or {},
                annotations=annotations or {}
            )
        )
        
        try:
            core_v1_api.read_namespace(name)
            logger.info(f"Namespace {name} already exists")
            # Update labels and annotations if needed
            core_v1_api.patch_namespace(name, {
                "metadata": {
                    "labels": labels or {},
                    "annotations": annotations or {}
                }
            })
        except client.exceptions.ApiException as e:
            if e.status == 404:
                core_v1_api.create_namespace(namespace)
                logger.info(f"Created namespace: {name}")
            else:
                raise
                
        # Create application gateway for the namespace
        create_application_gateway(name)
                
    except Exception as e:
        logger.error(f"Error managing namespace {name}: {str(e)}")
        raise

def create_application_gateway(namespace_name: str):
    """Create an application gateway for the namespace."""
    try:
        # Create Gateway custom resource
        api = client.CustomObjectsApi()
        gateway = {
            "apiVersion": "install.tetrate.io/v1alpha1",
            "kind": "Gateway",
            "metadata": {
                "name": f"{namespace_name}-gateway",
                "namespace": namespace_name,
                "labels": {
                    "arca.io/managed": "true",
                    "arca.io/namespace": namespace_name
                }
            },
            "spec": {
                "type": "UNIFIED",
                "kubeSpec": {
                    "service": {
                        "type": "LoadBalancer",
                        "annotations": {
                            "traffic.istio.io/nodeSelector": '{"kubernetes.io/os": "linux"}'
                        }
                    }
                }
            }
        }
        
        try:
            # Try to get existing gateway
            api.get_namespaced_custom_object(
                group="install.tetrate.io",
                version="v1alpha1",
                namespace=namespace_name,
                plural="gateways",
                name=f"{namespace_name}-gateway"
            )
            logger.info(f"Gateway already exists in namespace {namespace_name}")
            
            # Update existing gateway
            api.patch_namespaced_custom_object(
                group="install.tetrate.io",
                version="v1alpha1",
                namespace=namespace_name,
                plural="gateways",
                name=f"{namespace_name}-gateway",
                body=gateway
            )
            logger.info(f"Updated gateway in namespace {namespace_name}")
            
        except client.exceptions.ApiException as e:
            if e.status == 404:
                # Create new gateway
                api.create_namespaced_custom_object(
                    group="install.tetrate.io",
                    version="v1alpha1",
                    namespace=namespace_name,
                    plural="gateways",
                    body=gateway
                )
                logger.info(f"Created gateway in namespace {namespace_name}")
            else:
                raise
                
    except Exception as e:
        logger.error(f"Error managing gateway for namespace {namespace_name}: {str(e)}")
        raise

@kopf.on.create('operator.arca.io', 'v1alpha1', 'managerconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'managerconfigs')
@kopf.on.resume('operator.arca.io', 'v1alpha1', 'managerconfigs')
def handle_managerconfig(spec, name, meta, status, **kwargs):
    """Handle creation and updates of ManagerConfig resources."""
    if name != MANAGER_CONFIG_NAME:
        logger.warning(f"Ignoring ManagerConfig '{name}' as it's not the default name '{MANAGER_CONFIG_NAME}'")
        return

    global manager_config
    try:
        logger.debug(f"Handling ManagerConfig with spec: {spec}")
        manager_config = process_managerconfig(spec)
        logger.info("Configuration updated for ManagerConfig")
    except Exception as e:
        logger.error(f"Failed to process ManagerConfig: {str(e)}")
        raise kopf.PermanentError(f"Configuration failed: {str(e)}")

@kopf.on.event('xcp.tetrate.io', 'v2', 'workspaces')
def watch_workspaces(event, name, meta, spec, status, **kwargs):
    """Watch for Workspace events and create local namespaces."""
    if not manager_config or not manager_config.get('discovery_label'):
        return
    
    try:
        # Check if workspace is managed by us
        workspace_labels = meta.get('labels', {})
        annotations = meta.get('annotations', {})
        
        if workspace_labels.get('arca.io/managed') != 'true':
            return
            
        namespace_name = workspace_labels.get('arca.io/namespace')
        if not namespace_name:
            logger.warning(f"Workspace {name} is missing arca.io/namespace label")
            return
            
        event_type = event['type']
        logger.debug(f"Processing workspace event: {event_type} for {name}, namespace={namespace_name}")
        
        if event_type in ['ADDED', 'MODIFIED']:
            # Create or update namespace
            labels = {
                'arca.io/managed': 'true',
                'arca.io/workspace': name
            }
            
            annotations = {
                'arca.io/workspace-fqn': annotations.get('tsb.tetrate.io/fqn', ''),
                'arca.io/config-mode': annotations.get('tsb.tetrate.io/config-mode', '')
            }
            
            create_namespace(namespace_name, labels, annotations)
            
    except Exception as e:
        logger.error(f"Error processing workspace {name}: {str(e)}")
        raise kopf.TemporaryError(f"Failed to process workspace: {str(e)}", delay=60)

@kopf.timer('operator.arca.io', 'v1alpha1', 'managerconfigs',
            interval=300.0,
            sharp=True,
            idle=60.0,
            initial_delay=60.0)
def periodic_namespace_reconciliation(spec, name, logger, **kwargs):
    """Periodically reconcile namespaces to ensure consistency."""
    if name != MANAGER_CONFIG_NAME:
        return
        
    if not manager_config or not manager_config.get('discovery_label'):
        logger.warning("No valid manager configuration or discovery label found")
        return

    try:
        # List all workspaces
        api = client.CustomObjectsApi()
        workspaces = api.list_namespaced_custom_object(
            group="xcp.tetrate.io",
            version="v2",
            namespace="tsb",
            plural="workspaces"
        )
        
        for workspace in workspaces.get('items', []):
            workspace_labels = workspace.get('metadata', {}).get('labels', {})
            if workspace_labels.get('arca.io/managed') == 'true':
                namespace_name = workspace_labels.get('arca.io/namespace')
                if namespace_name:
                    create_namespace(
                        namespace_name,
                        {'arca.io/managed': 'true', 'arca.io/workspace': workspace['metadata']['name']},
                        {'arca.io/workspace-fqn': workspace.get('metadata', {}).get('annotations', {}).get('tsb.tetrate.io/fqn', '')}
                    )
                
    except Exception as e:
        logger.error(f"Error during periodic reconciliation: {str(e)}")
        raise kopf.TemporaryError(f"Reconciliation failed: {str(e)}", delay=300) 