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
    Special handling for namespaceSelector.names to combine lists.
    """
    for key in d2:
        # Special handling for namespaceSelector.names
        if key == 'namespaceSelector' and isinstance(d1.get(key), dict) and isinstance(d2[key], dict):
            if 'names' not in d1[key]:
                d1[key]['names'] = []
            if 'names' in d2[key]:
                # Get existing and new names
                existing_names = d1[key]['names']
                new_names = d2[key]['names']
                
                # Combine lists while preserving both existing and new entries
                all_names = existing_names.copy()  # Start with existing names
                for name in new_names:
                    if name not in all_names:  # Only add if not already present
                        all_names.append(name)
                
                # Update the names list
                d1[key]['names'] = all_names
                
                # Handle other namespaceSelector fields
                for subkey in d2[key]:
                    if subkey != 'names':
                        d1[key][subkey] = d2[key][subkey]
        # Regular recursive merge for other keys
        elif isinstance(d1.get(key), dict) and isinstance(d2[key], dict):
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
                'namespaceSelector': {'names': []},
                'configGenerationMetadata': {
                    'labels': {"arca.io/managed": "true"}
                }
            }

    def get(self):
        """Get workspace details."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        try:
            response = tetrate.send_request('GET', url)
            self.workspace_data = response
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def create_or_update(self, desired_data: dict):
        """Create or update workspace with given data."""
        tetrate = TetrateConnection.get_instance()
        base_url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces'
        
        try:
            # Try to get existing workspace
            existing = self.get()
            
            if existing:
                # Get the etag from existing workspace
                etag = existing.get('etag')
                
                # Merge existing with desired data
                merged_data = existing.copy()
                recursive_merge(merged_data, desired_data)
                
                # Preserve the etag
                if etag:
                    merged_data['etag'] = etag
                
                logger.debug(f"Updating workspace with merged data: {merged_data}")
                
                # Update existing workspace
                url = f"{base_url}/{self.name}"
                logger.info(f"Updating workspace: {self.name}")
                response = tetrate.send_request('PUT', url, merged_data)
                self.workspace_data = response
                return response
            else:
                # Create new workspace
                logger.info(f"Creating new workspace: {self.name}")
                payload = {
                    'name': self.name,
                    'workspace': desired_data
                }
                logger.debug(f"Create payload: {payload}")
                response = tetrate.send_request('POST', base_url, payload)
                self.workspace_data = response
                return response
                
        except Exception as e:
            logger.error(f"Error managing workspace {self.name}: {str(e)}")
            raise

    def delete(self):
        """Delete the workspace."""
        tetrate = TetrateConnection.get_instance()
        url = f'{tetrate.endpoint}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        logger.info(f"Deleting workspace: {self.name}")
        return tetrate.send_request('DELETE', url)

@dataclass
class WorkspaceSetting:
    """Class representing a TSB WorkspaceSetting within a Workspace."""
    workspace: Workspace
    name: str
    setting_data: dict = None
    max_retries: int = 3
    
    def __post_init__(self):
        if self.setting_data is None:
            self.setting_data = {}

    def get(self):
        """Get workspace setting details."""
        tetrate = TetrateConnection.get_instance()
        url = (f'{tetrate.endpoint}/v2/organizations/{self.workspace.tenant.organization.name}/'
               f'tenants/{self.workspace.tenant.name}/workspaces/{self.workspace.name}/settings/{self.name}')
        try:
            response = tetrate.send_request('GET', url)
            self.setting_data = response
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def create_or_update(self, desired_settings: dict, retry_count=0):
        """Create or update workspace setting with given settings."""
        if retry_count >= self.max_retries:
            raise Exception(f"Max retries ({self.max_retries}) exceeded while trying to update workspace settings")
            
        tetrate = TetrateConnection.get_instance()
        base_url = (f'{tetrate.endpoint}/v2/organizations/{self.workspace.tenant.organization.name}/'
                   f'tenants/{self.workspace.tenant.name}/workspaces/{self.workspace.name}/settings')
        
        try:
            # Try to get existing settings
            existing = self.get()
            
            if existing:
                # Get the etag from existing settings
                etag = existing.get('etag')
                
                # Merge existing with desired settings
                merged_settings = existing.copy()  # Copy the entire response
                if 'settings' in merged_settings:
                    recursive_merge(merged_settings, desired_settings)
                else:
                    merged_settings = desired_settings
                
                # Preserve the etag
                if etag:
                    merged_settings['etag'] = etag
                
                logger.debug(f"Updating with merged settings: {merged_settings}")
                
                # Update existing settings
                url = f"{base_url}/{self.name}"
                logger.info(f"Updating workspace setting: {self.name}")
                logger.debug(f"Update payload: {merged_settings}")
                response = tetrate.send_request('PUT', url, merged_settings)
                self.setting_data = response
                return response
            else:
                # Create new settings
                logger.info(f"Creating new workspace setting: {self.name}")
                logger.debug(f"Update payload: {desired_settings}")
                payload = {
                    'name': self.name,
                    'settings': desired_settings
                }
                logger.debug(f"Create payload: {payload}")
                response = tetrate.send_request('POST', base_url, payload)
                self.setting_data = response
                return response
                
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 500 and "the resource has already been modified" in str(e.response.text):
                # Resource was modified, retry with fresh data
                logger.warning(f"Concurrent modification detected, retrying ({retry_count + 1}/{self.max_retries})")
                return self.create_or_update(desired_settings, retry_count + 1)
            raise

    def delete(self):
        """Delete the workspace setting."""
        tetrate = TetrateConnection.get_instance()
        url = (f'{tetrate.endpoint}/v2/organizations/{self.workspace.tenant.organization.name}/'
               f'tenants/{self.workspace.tenant.name}/workspaces/{self.workspace.name}/settings/{self.name}')
        logger.info(f"Deleting workspace setting: {self.name}")
        return tetrate.send_request('DELETE', url)

@dataclass
class GatewayGroup:
    """Class representing a TSB Gateway Group within a Workspace."""
    workspace: Workspace
    name: str
    group_data: dict = None

    def __post_init__(self):
        if self.group_data is None:
            self.group_data = {
                'configMode': 'BRIDGED',
                'namespaceSelector': {
                    'names': []
                },
                'configGenerationMetadata': {
                    'labels': {
                        'arca.io/managed': 'true'
                    }
                }
            }

    def get(self):
        """Get gateway group details."""
        tetrate = TetrateConnection.get_instance()
        url = (f'{tetrate.endpoint}/v2/organizations/{self.workspace.tenant.organization.name}/'
               f'tenants/{self.workspace.tenant.name}/workspaces/{self.workspace.name}/gatewaygroups/{self.name}')
        try:
            response = tetrate.send_request('GET', url)
            self.group_data = response.get('group', {})
            return response
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                return None
            raise

    def create_or_update(self, desired_data: dict):
        """Create or update gateway group with given data."""
        tetrate = TetrateConnection.get_instance()
        base_url = (f'{tetrate.endpoint}/v2/organizations/{self.workspace.tenant.organization.name}/'
                   f'tenants/{self.workspace.tenant.name}/workspaces/{self.workspace.name}/gatewaygroups')
        
        try:
            # Try to get existing group
            existing = self.get()
            
            if existing:
                # Get the etag from existing group
                etag = existing.get('etag')
                
                # Merge existing with desired data
                merged_data = existing.copy()
                recursive_merge(merged_data, desired_data)
                
                # Preserve the etag
                if etag:
                    merged_data['etag'] = etag
                
                logger.debug(f"Updating gateway group with merged data: {merged_data}")
                
                # Update existing group
                url = f"{base_url}/{self.name}"
                logger.info(f"Updating gateway group: {self.name}")
                response = tetrate.send_request('PUT', url, merged_data)
                self.group_data = response.get('group', {})
                return response
            else:
                # Create new gateway group
                logger.info(f"Creating new gateway group: {self.name}")
                payload = {
                    'name': self.name,
                    'group': desired_data
                }
                logger.debug(f"Create payload: {payload}")
                response = tetrate.send_request('POST', base_url, payload)
                self.group_data = response.get('group', {})
                return response
                
        except Exception as e:
            logger.error(f"Error managing gateway group {self.name}: {str(e)}")
            raise

    def delete(self):
        """Delete the gateway group."""
        tetrate = TetrateConnection.get_instance()
        url = (f'{tetrate.endpoint}/v2/organizations/{self.workspace.tenant.organization.name}/'
               f'tenants/{self.workspace.tenant.name}/workspaces/{self.workspace.name}/gatewaygroups/{self.name}')
        logger.info(f"Deleting gateway group: {self.name}")
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