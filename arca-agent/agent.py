# agent.py

import kopf
import kubernetes.client as k8s_client
from kubernetes import config, client

# Load the Kubernetes configuration
config.load_incluster_config()

# Create Kubernetes API clients
api_client = k8s_client.ApiClient()
core_v1_api = k8s_client.CoreV1Api(api_client)
apps_v1_api = k8s_client.AppsV1Api(api_client)

# Handler for AgentConfig creation
@kopf.on.create('operator.arca.io', 'v1alpha1', 'agentconfigs')
def create_agentconfig(spec, name, namespace, **kwargs):
    agent_setting = spec.get('agentSetting', 'default-value')
    kopf.info(
        {'agentconfig': name},
        reason="AgentConfigCreated",
        message=f"AgentConfig '{name}' created with setting '{agent_setting}'."
    )
    # Implement your logic here (e.g., deploy agent components)
    create_agent_deployment(name, namespace, agent_setting)

# Handler for AgentConfig updates
@kopf.on.update('operator.arca.io', 'v1alpha1', 'agentconfigs')
def update_agentconfig(spec, name, namespace, **kwargs):
    agent_setting = spec.get('agentSetting', 'default-value')
    kopf.info(
        {'agentconfig': name},
        reason="AgentConfigUpdated",
        message=f"AgentConfig '{name}' updated with setting '{agent_setting}'."
    )
    # Implement your logic here (e.g., update agent components)
    update_agent_deployment(name, namespace, agent_setting)

# Function to create a Deployment for the agent
def create_agent_deployment(name, namespace, agent_setting):
    deployment = k8s_client.V1Deployment(
        metadata=k8s_client.V1ObjectMeta(
            name=f"{name}-deployment",
            namespace=namespace,
            labels={"app": name}
        ),
        spec=k8s_client.V1DeploymentSpec(
            replicas=1,
            selector=k8s_client.V1LabelSelector(
                match_labels={"app": name}
            ),
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(
                    labels={"app": name}
                ),
                spec=k8s_client.V1PodSpec(
                    containers=[
                        k8s_client.V1Container(
                            name=f"{name}-container",
                            image="nginx",  # Replace with your agent image
                            env=[
                                k8s_client.V1EnvVar(
                                    name="AGENT_SETTING",
                                    value=agent_setting
                                )
                            ]
                        )
                    ]
                )
            )
        )
    )
    apps_v1_api.create_namespaced_deployment(namespace=namespace, body=deployment)

# Function to update the Deployment for the agent
def update_agent_deployment(name, namespace, agent_setting):
    deployment_name = f"{name}-deployment"
    try:
        deployment = apps_v1_api.read_namespaced_deployment(name=deployment_name, namespace=namespace)
        # Update the environment variable in the container
        deployment.spec.template.spec.containers[0].env[0].value = agent_setting
        apps_v1_api.patch_namespaced_deployment(
            name=deployment_name,
            namespace=namespace,
            body=deployment
        )
    except k8s_client.exceptions.ApiException as e:
        if e.status == 404:
            # Deployment not found, create it
            create_agent_deployment(name, namespace, agent_setting)
        else:
            raise
