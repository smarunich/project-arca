import os
import sys
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

# TSB Environment Variables
TSB_ENDPOINT = os.getenv('TSB_ENDPOINT', 'https://your-tsb-server.com')

# TSB Authentication Variables
TSB_API_TOKEN = os.getenv('TSB_API_TOKEN')
TSB_USERNAME = os.getenv('TSB_USERNAME')
TSB_PASSWORD = os.getenv('TSB_PASSWORD')

ORGANIZATION_NAME = os.getenv('TSB_ORGANIZATION', 'tetrate')
TENANT_NAME = os.getenv('TSB_TENANT', 'arca')

def get_headers():
    """Construct HTTP headers with appropriate authentication."""
    headers = {
        'Content-Type': 'application/json',
        'Accept': 'application/json'
    }
    if TSB_API_TOKEN:
        headers['Authorization'] = f'Bearer {TSB_API_TOKEN}'
    elif TSB_USERNAME and TSB_PASSWORD:
        import base64
        credentials = base64.b64encode(f"{TSB_USERNAME}:{TSB_PASSWORD}".encode()).decode()
        headers['Authorization'] = f'Basic {credentials}'
    else:
        logger.error("Authentication credentials are missing.")
        raise ValueError("Authentication credentials must be provided.")
    return headers

def send_request(method, url, headers, data=None, timeout=None):
    """
    Helper function to send HTTP requests and handle common exceptions.
    """
    timeout = timeout or int(os.getenv('REQUEST_TIMEOUT', '30'))
    response = None
    try:
        response = requests.request(
            method,
            url,
            headers=headers,
            json=data,
            timeout=timeout,
            verify=False
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

@dataclass
class Organization:
    """Class representing a TSB Organization."""
    name: str

    def get(self):
        """Retrieve organization details from the TSB API."""
        url = f'{TSB_ENDPOINT}/v2/organizations/{self.name}'
        return send_request('GET', url, get_headers())

@dataclass
class Tenant:
    """Class representing a TSB Tenant within an Organization."""
    organization: Organization
    name: str

    def get(self):
        """Retrieve tenant details from the TSB API."""
        url = f'{TSB_ENDPOINT}/v2/organizations/{self.organization.name}/tenants/{self.name}'
        return send_request('GET', url, get_headers())

@dataclass
class Workspace:
    """Class representing a TSB Workspace within a Tenant."""
    tenant: Tenant
    name: str
    namespace_selector: dict = None
    display_name: str = None

    def __post_init__(self):
        if self.namespace_selector is None:
            self.namespace_selector = {'names': ['*/default']}
        if self.display_name is None:
            self.display_name = self.name

    def get(self):
        """Get workspace details."""
        url = f'{TSB_ENDPOINT}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        return send_request('GET', url, get_headers())

    def create(self):
        """Create a new workspace in TSB."""
        url = f'{TSB_ENDPOINT}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces'
        headers = get_headers()
        payload = {
            'name': self.name,
            'displayName': self.display_name,
            'namespaceSelector': self.namespace_selector
        }
        logger.info(f"Creating workspace: {self.name}")
        return send_request('POST', url, headers, payload)

    def update(self, etag):
        """Update an existing workspace in TSB."""
        if not etag:
            logger.error("ETag is required for updating the workspace.")
            raise ValueError("ETag must be provided to update the workspace.")

        url = f'{TSB_ENDPOINT}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        headers = get_headers()
        headers['If-Match'] = etag

        payload = {
            'name': self.name,
            'displayName': self.display_name,
            'namespaceSelector': self.namespace_selector
        }

        logger.info(f"Updating workspace: {self.name}")
        return send_request('PUT', url, headers, payload)

    def delete(self):
        """Delete the workspace."""
        url = f'{TSB_ENDPOINT}/v2/organizations/{self.tenant.organization.name}/tenants/{self.tenant.name}/workspaces/{self.name}'
        logger.info(f"Deleting workspace: {self.name}")
        return send_request('DELETE', url, get_headers())

def main():
    try:
        # Create organization and tenant objects
        organization = Organization(ORGANIZATION_NAME)
        tenant = Tenant(organization, TENANT_NAME)

        # Get organization details
        org_details = organization.get()
        logger.info(f"Found organization: {org_details}")

        # Get tenant details
        try:
            tenant_details = tenant.get()
            logger.info(f"Found existing tenant: {tenant_details}")
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                logger.error(f"Tenant {tenant.name} not found")
            else:
                raise

        # Example usage of the Workspace class (uncomment if needed)
        workspace = Workspace(tenant=tenant, name='my-workspace')
        workspace_details = workspace.get()
        logger.info(f"Workspace details: {workspace_details}")

    except Exception as e:
        logger.exception('An error occurred')
        sys.exit(1)

if __name__ == '__main__':
    main()
