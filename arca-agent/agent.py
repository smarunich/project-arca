import os
import kopf
import kubernetes
from kubernetes import client, config, watch
import logging
import threading
import time
import traceback

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
formatter = logging.Formatter('%(asctime)s %(levelname)s [%(threadName)s] %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(log_level)

# Load the Kubernetes configuration
try:
    config.load_incluster_config()
except config.ConfigException:
    # For local testing outside the cluster
    config.load_kube_config()

# Create Kubernetes API clients
core_v1_api = client.CoreV1Api()

# Global cache and lock
agentconfigs = {}
agentconfigs_lock = threading.Lock()

def namespace_watcher():
    while True:
        try:
            # Use a Kubernetes watch to monitor namespace events
            w = watch.Watch()
            stream = w.stream(core_v1_api.list_namespace)
            for event in stream:
                ns = event['object']
                event_type = event['type']
                namespace_name = ns.metadata.name
                namespace_labels = ns.metadata.labels or {}

                logger.debug(f"Received event {event_type} for namespace {namespace_name}")

                with agentconfigs_lock:
                    for name, discovery_label in agentconfigs.items():
                        try:
                            key, value = discovery_label.split('=', 1)
                        except ValueError:
                            logger.error(f"Invalid discoveryLabel format in AgentConfig {name}: {discovery_label}")
                            continue

                        # Check if the namespace matches the discoveryLabel
                        if namespace_labels.get(key) == value:
                            if event_type in ['ADDED', 'MODIFIED']:
                                logger.info(f"Namespace '{namespace_name}' matches AgentConfig '{name}'")
                                # Process services in this namespace
                                process_namespace_services(namespace_name)
                            elif event_type == 'DELETED':
                                logger.info(f"Namespace '{namespace_name}' deleted")
                                # Handle namespace deletion if necessary
        except Exception as e:
            logger.error(f"Error while watching namespaces: {str(e)}")
            logger.debug(traceback.format_exc())
            time.sleep(5)  # Wait before retrying

def process_namespace_services(namespace_name):
    try:
        services = core_v1_api.list_namespaced_service(namespace_name)
        for svc in services.items:
            logger.info(f"Service '{svc.metadata.name}' in namespace '{namespace_name}'")
            # Implement any additional processing required for the services
    except Exception as e:
        logger.error(f"Error processing services in namespace '{namespace_name}': {str(e)}")
        logger.debug(traceback.format_exc())

# Start the namespace watcher in a separate thread
threading.Thread(target=namespace_watcher, name='NamespaceWatcher', daemon=True).start()

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, **kwargs):
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label:
        logger.error("discoveryLabel must be specified in AgentConfig.")
        raise kopf.PermanentError("discoveryLabel must be specified in AgentConfig.")

    with agentconfigs_lock:
        agentconfigs[name] = discovery_label

    logger.info(f"AgentConfig '{name}' created or updated with discoveryLabel: '{discovery_label}'")

@kopf.on.delete('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig_delete(name, **kwargs):
    with agentconfigs_lock:
        if name in agentconfigs:
            del agentconfigs[name]
            logger.info(f"AgentConfig '{name}' deleted from cache.")

    # Implement any additional cleanup if necessary
