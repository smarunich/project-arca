import os
import requests
import logging
from dataclasses import dataclass

def configure_logging():
    """Configure the logging for the script."""
    log_level = os.getenv('LOG_LEVEL', 'DEBUG').upper()
    logger = logging.getLogger('arca-agent')
    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter('%(asctime)s %(levelname)s [%(name)s] %(message)s')
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        logger.setLevel(log_level)
    return logger

logger = configure_logging()

class TetrateConnection:
    """Class to manage Tetrate connection and authentication."""
    _instance = None  # Class variable to store the singleton instance

    @classmethod
    def get_instance(cls):
        """Get the singleton instance of TetrateConnection."""
        if cls._instance is None:
            raise ValueError("TetrateConnection not initialized")
        return cls._instance

    def __init__(self, endpoint=None, api_token=None, username=None, password=None, organization=None, tenant=None):
        self.endpoint = endpoint or os.getenv('TETRATE_ENDPOINT', 'https://your-tsb-server.com')
        self.api_token = api_token or os.getenv('TETRATE_API_TOKEN')
        self.username = username or os.getenv('TETRATE_USERNAME')
        self.password = password or os.getenv('TETRATE_PASSWORD')
        self.organization = organization or os.getenv('TETRATE_ORGANIZATION', 'tetrate')
        self.tenant = tenant or os.getenv('TETRATE_TENANT', 'arca')
        
        # Set this instance as the singleton instance
        TetrateConnection._instance = self

    def get_headers(self):
        """Construct HTTP headers with appropriate authentication."""
        headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json'
        }
        if self.username and self.password:
            import base64
            credentials = base64.b64encode(f"{self.username}:{self.password}".encode()).decode()
            headers['Authorization'] = f'Basic {credentials}'
        elif self.api_token:
            headers['Authorization'] = f'Bearer {self.api_token}'
        else:
            logger.error("Authentication credentials are missing.")
            raise ValueError("Authentication credentials must be provided.")
        return headers

    def send_request(self, method, url, data=None, timeout=None):
        """Helper function to send HTTP requests and handle common exceptions."""
        timeout = timeout or int(os.getenv('REQUEST_TIMEOUT', '30'))
        response = None
        try:
            response = requests.request(
                method,
                url,
                headers=self.get_headers(),
                json=data,
                timeout=timeout,
                verify=False  # Note: SSL verification is disabled; enable it in production
            )
            response.raise_for_status()
            return response.json() if response.content else None
        except requests.exceptions.Timeout:
            logger.error(f"Request to {url} timed out.")
            raise
        except requests.exceptions.HTTPError as http_err:
            if response is not None:
                logger.error(f"HTTP error occurred: {http_err} - Response: {response.text}")
            else:
                logger.error(f"HTTP error occurred: {http_err} - No response received.")
            raise
        except requests.exceptions.RequestException as req_err:
            logger.error(f"Request exception occurred: {req_err}")
            raise
        except Exception as err:
            logger.exception(f"An unexpected error occurred: {err}")
            raise

def recursive_merge(d1, d2):
    """
    Recursively merge d2 into d1. Values in d2 will overwrite those in d1.
    """
    for key in d2:
        if key in d1 and isinstance(d1[key], dict) and isinstance(d2[key], dict):
            recursive_merge(d1[key], d2[key])
        else:
            d1[key] = d2[key]

@dataclass
class Organization:
    """Class representing a TSB Organization."""
    name: str

    def get(self):
        """Retrieve organization details from the TSB API."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.name}'
        return tetrate.send_request('GET', url)

@dataclass
class Tenant:
    """Class representing a TSB Tenant within an Organization."""
    organization: Organization
    name: str

    def get(self):
        """Retrieve tenant details from the TSB API."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.organization.name}/tenants/{self.name}'
        return tetrate.send_request('GET', url)

@dataclass
class Workspace:
    """Class representing a TSB Workspace within a Tenant."""
    tenant: Tenant
    name: str
    workspace_data: dict = None

    def __post_init__(self):
        if self.workspace_data is None:
            self.workspace_data = {
                'namespaceSelector': {'names': [f'*/{self.name}']},
                'configGenerationMetadata': {
                    'labels': {"arca.io/managed": "true"}
                }
            }

    def get(self):
        """Get workspace details."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        response = tetrate.send_request('GET', url)
        # Update the object's workspace_data with the retrieved data
        self.workspace_data = response.get('workspace', self.workspace_data)
        self.workspace_data['etag'] = response.get('etag')
        return response

    def create(self):
        """Create a new workspace in TSB."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces'
        payload = {
            'name': self.name,
            'workspace': self.workspace_data
        }
        logger.info(f"Creating workspace: {self.name}")
        response = tetrate.send_request('POST', url, payload)
        # Update the object's workspace_data with the created data
        self.workspace_data = response.get('workspace', self.workspace_data)
        self.workspace_data['etag'] = response.get('etag')
        return response

    def update(self, **kwargs):
        """Update an existing workspace in TSB."""
        tetrate = TetrateConnection.get_instance()
        # Retrieve the current workspace data
        self.get()
        # Merge the updates into the workspace data recursively
        recursive_merge(self.workspace_data, kwargs)

        # Prepare the payload
        payload = self.workspace_data
        
        url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        logger.info(f"Updating workspace: {self.name} with data: {payload}")

        # Send the PUT request with the updated payload
        updated_response = tetrate.send_request('PUT', url, payload)

        # Update the object's workspace_data with the updated data
        self.workspace_data = updated_response.get('workspace', self.workspace_data)
        self.workspace_data['etag'] = updated_response.get('etag')

        return updated_response

    def delete(self):
        """Delete the workspace."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        logger.info(f"Deleting workspace: {self.name}")
        return tetrate.send_request('DELETE', url)

def test():
    try:
        # Create organization and tenant objects
        organization = Organization(tetrate.organization)
        tenant = Tenant(organization, tetrate.tenant)

        # Get organization details
        org_details = organization.get()
        logger.info(f"Found organization: {org_details}")

        # Get tenant details
        tenant_details = tenant.get()
        logger.info(f"Found existing tenant: {tenant_details}")

        # Initialize the Workspace object
        workspace = Workspace(tenant=tenant, name='my-workspace')
        workspace.create()
        # Get workspace details
        workspace_details = workspace.get()
        logger.info(f"Workspace details: {workspace_details}")

        # Update the workspace with new properties
        update_properties = {
            'namespaceSelector': {'names': ['*/new-namespace']},
            'configGenerationMetadata': {
                'labels': {
                    'arca.io/managed': 'true',
                    'additional-label': 'value'
                }
            },
            'description': 'Updated description'
        }
        workspace.update(**update_properties)
        workspace.delete()
        logger.info(f"Workspace updated successfully: {workspace.workspace_data}")

    except Exception as e:
        logger.exception('An error occurred')
        sys.exit(1)