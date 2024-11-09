# agent.py

import os
import time
import kopf
import kubernetes
from kubernetes import client, config
import logging

# Configure logging
log_level = os.getenv('LOG_LEVEL', 'INFO').upper()
logging.basicConfig(level=log_level)
logger = logging.getLogger(__name__)

# Load the Kubernetes configuration
config.load_incluster_config()

# Create Kubernetes API clients
core_v1_api = client.CoreV1Api()

@kopf.on.startup()
def configure(settings: kopf.OperatorSettings, **_):
    settings.watching.clusterwide = True  # Set to False if you want namespace-specific

@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def handle_agentconfig(spec, **kwargs):
    discovery_label = spec.get('discoveryLabel')
    if not discovery_label:
        logger.error("discoveryLabel must be specified in AgentConfig.")
        raise kopf.PermanentError("discoveryLabel must be specified in AgentConfig.")

    # Fetch namespaces that match the discovery label
    try:
        namespaces = core_v1_api.list_namespace(label_selector=discovery_label)
        for ns in namespaces.items:
            logger.info(f"Discovered namespace: {ns.metadata.name}")
    except Exception as e:
        logger.error(f"Failed to list namespaces: {str(e)}")

def watch_services(namespace, discovery_label):
    """
    Watch for changes in services within a namespace.
    """
    while True:
        services = core_v1_api.list_namespaced_service(namespace)
        for svc in services.items:
            logger.debug(f"Service details: {svc}")
        time.sleep(60)  # Check every 60 seconds

def print_service_details(service):
    """
    Print detailed information about a Kubernetes service.
    """
    logger.info(f"Service Name: {service.metadata.name}")
    logger.info(f"Namespace: {service.metadata.namespace}")
    logger.info(f"Labels: {service.metadata.labels}")
    logger.info(f"Annotations: {service.metadata.annotations}")
    logger.info(f"Cluster IP: {service.spec.cluster_ip}")
    logger.info(f"Ports: {service.spec.ports}")
    logger.info(f"Type: {service.spec.type}")
    logger.info(f"Session Affinity: {service.spec.session_affinity}")
    if service.spec.selector:
        logger.info(f"Selector: {service.spec.selector}")
