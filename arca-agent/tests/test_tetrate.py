import pytest
import responses
from unittest.mock import Mock, patch
from tetrate import (
    TetrateConnection, Organization, Tenant, Workspace, WorkspaceSetting,
    recursive_merge
)

# Test data
TEST_ENDPOINT = "https://test-tsb.example.com"
TEST_TOKEN = "test-token"
TEST_ORG = "test-org"
TEST_TENANT = "test-tenant"
TEST_WORKSPACE = "test-workspace"

@pytest.fixture
def tetrate_connection():
    """Create a TetrateConnection instance for testing."""
    conn = TetrateConnection(
        endpoint=TEST_ENDPOINT,
        api_token=TEST_TOKEN,
        organization=TEST_ORG,
        tenant=TEST_TENANT
    )
    return conn

@pytest.fixture
def organization(tetrate_connection):
    """Create an Organization instance for testing."""
    return Organization(name=TEST_ORG)

@pytest.fixture
def tenant(organization):
    """Create a Tenant instance for testing."""
    return Tenant(organization=organization, name=TEST_TENANT)

@pytest.fixture
def workspace(tenant):
    """Create a Workspace instance for testing."""
    return Workspace(tenant=tenant, name=TEST_WORKSPACE)

class TestTetrateConnection:
    def test_singleton_pattern(self):
        """Test that TetrateConnection maintains singleton pattern."""
        conn1 = TetrateConnection(endpoint=TEST_ENDPOINT, api_token=TEST_TOKEN)
        conn2 = TetrateConnection.get_instance()
        assert conn1 is conn2

    def test_headers_with_token(self):
        """Test header generation with API token."""
        conn = TetrateConnection(endpoint=TEST_ENDPOINT, api_token=TEST_TOKEN)
        headers = conn.get_headers()
        assert headers['Authorization'] == f'Bearer {TEST_TOKEN}'

    def test_headers_with_basic_auth(self):
        """Test header generation with username/password."""
        conn = TetrateConnection(
            endpoint=TEST_ENDPOINT,
            username="test-user",
            password="test-pass"
        )
        headers = conn.get_headers()
        assert 'Basic' in headers['Authorization']

    @responses.activate
    def test_send_request(self, tetrate_connection):
        """Test send_request method."""
        test_url = f"{TEST_ENDPOINT}/test"
        test_response = {"status": "success"}
        
        responses.add(
            responses.GET,
            test_url,
            json=test_response,
            status=200
        )
        
        response = tetrate_connection.send_request('GET', test_url)
        assert response == test_response

class TestRecursiveMerge:
    def test_merge_simple_dicts(self):
        """Test merging of simple dictionaries."""
        d1 = {'a': 1, 'b': 2}
        d2 = {'b': 3, 'c': 4}
        recursive_merge(d1, d2)
        assert d1 == {'a': 1, 'b': 3, 'c': 4}

    def test_merge_namespace_selector(self):
        """Test merging of namespace selectors."""
        d1 = {'namespaceSelector': {'names': ['ns1', 'ns2']}}
        d2 = {'namespaceSelector': {'names': ['ns2', 'ns3']}}
        recursive_merge(d1, d2)
        assert d1['namespaceSelector']['names'] == ['ns1', 'ns2', 'ns3']

class TestWorkspace:
    @responses.activate
    def test_create_workspace(self, workspace):
        """Test workspace creation."""
        url = f"{TEST_ENDPOINT}/v2/organizations/{TEST_ORG}/tenants/{TEST_TENANT}/workspaces"
        test_response = {
            "name": TEST_WORKSPACE,
            "workspace": workspace.workspace_data
        }
        
        responses.add(
            responses.POST,
            url,
            json=test_response,
            status=200
        )
        
        response = workspace.create()
        assert response == test_response

    @responses.activate
    def test_update_workspace(self, workspace):
        """Test workspace update."""
        url = f"{TEST_ENDPOINT}/v2/organizations/{TEST_ORG}/tenants/{TEST_TENANT}/workspaces/{TEST_WORKSPACE}"
        test_response = {
            "name": TEST_WORKSPACE,
            "workspace": workspace.workspace_data
        }
        
        responses.add(
            responses.PUT,
            url,
            json=test_response,
            status=200
        )
        
        response = workspace.update(description="Updated workspace")
        assert response == test_response

class TestWorkspaceSetting:
    @responses.activate
    def test_create_workspace_setting(self, workspace):
        """Test workspace setting creation."""
        setting = WorkspaceSetting(workspace=workspace, name="default")
        url = f"{TEST_ENDPOINT}/v2/organizations/{TEST_ORG}/tenants/{TEST_TENANT}/workspaces/{TEST_WORKSPACE}/settings"
        
        test_response = {
            "name": "default",
            "settings": {"test": "data"}
        }
        
        responses.add(
            responses.POST,
            url,
            json=test_response,
            status=200
        )
        
        response = setting.create_or_update({"test": "data"})
        assert response == test_response 