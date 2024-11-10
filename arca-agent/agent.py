import os
import kopf
import kubernetes
from kubernetes import client, config
import logging
import threading
import time

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# Load the Kubernetes configuration
config.load_incluster_config()

# Create Kubernetes API clients
core_v1_api = client.CoreV1Api()

# Global cache
agentconfigs = {}

def namespace_watcher():
    while True:
        try:
            # Fetch all namespaces
            namespaces = core_v1_api.list_namespace()
            for ns in namespaces.items:
                # Check each namespace against each AgentConfig's discoveryLabel
                for name, discovery_label in agentconfigs.items():
                    key, value = discovery_label.split('=')
                    logger.debug(f"Comparing labels: {ns.metadata.labels.get(key)} == {value}")
                    if ns.metadata.labels.get(key) == value:
                        # Fetch and log services from this namespace
                        services = core_v1_api.list_namespaced_service(ns.metadata.name)
                        for svc in services.items:
                            logger.info(f"Service {svc.metadata.name} in namespace {ns.metadata.name}")
        except Exception as e:
            logger.error(f"Error while watching namespaces: {str(e)}")
        time.sleep(60)  # Check every 60 seconds

# Start the namespace watcher in a separate thread
threading.Thread(target=namespace_watcher, daemon=True).start()

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, name, **kwargs):
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label:
        logger.error("discoveryLabel must be specified in AgentConfig.")
        raise kopf.PermanentError("discoveryLabel must be specified in AgentConfig.")
    agentconfigs[name] = discovery_label
    logger.info(f"AgentConfig {name} updated with discoveryLabel: {discovery_label}")

@kopf.on.delete('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig_delete(name, **kwargs):
    if name in agentconfigs:
        del agentconfigs[name]
        logger.info(f"AgentConfig {name} deleted.")
