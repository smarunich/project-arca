import pytest
import kopf
from unittest.mock import Mock, patch
from kubernetes import client
from agent import (
    process_agentconfig,
    initialize_tetrate_connection,
    workspace_manager,
    handle_agentconfig,
    watch_namespaces
)

# Test data
TEST_NAMESPACE = "test-namespace"
TEST_LABEL = "test-label=true"

@pytest.fixture
def mock_k8s_api():
    """Mock Kubernetes API client."""
    with patch('kubernetes.client.CoreV1Api') as mock:
        yield mock

@pytest.fixture
def mock_tetrate():
    """Mock Tetrate connection."""
    with patch('tetrate.TetrateConnection') as mock:
        yield mock

class TestAgentConfig:
    def test_process_agentconfig_valid(self):
        """Test processing valid AgentConfig."""
        spec = {
            'discoveryLabel': 'app=test',
            'tetrate': {
                'endpoint': 'https://test.example.com',
                'apiToken': 'test-token'
            }
        }
        config = process_agentconfig(spec)
        assert config['discovery_label'] == 'app=test'
        assert config['discovery_key'] == 'app'
        assert config['discovery_value'] == 'test'

    def test_process_agentconfig_invalid_label(self):
        """Test processing AgentConfig with invalid label."""
        spec = {
            'discoveryLabel': 'invalid-label',
            'tetrate': {}
        }
        with pytest.raises(ValueError):
            process_agentconfig(spec)

class TestTetrateConnection:
    def test_initialize_tetrate_connection_valid(self, mock_tetrate):
        """Test initializing Tetrate connection with valid config."""
        config = {
            'endpoint': 'https://test.example.com',
            'apiToken': 'test-token'
        }
        result = initialize_tetrate_connection(config)
        assert result is True
        mock_tetrate.assert_called_once()

    def test_initialize_tetrate_connection_invalid(self):
        """Test initializing Tetrate connection with invalid config."""
        config = {
            'endpoint': 'https://test.example.com'
            # Missing authentication
        }
        result = initialize_tetrate_connection(config)
        assert result is False

class TestNamespaceHandling:
    @patch('agent.workspace_manager')
    def test_watch_namespaces_new(self, mock_workspace_manager):
        """Test namespace watch for new namespace."""
        event = {
            'type': 'ADDED',
            'object': {
                'metadata': {
                    'name': TEST_NAMESPACE,
                    'labels': {'test-label': 'true'}
                }
            }
        }
        
        # Mock global agent_config
        with patch('agent.agent_config', {'discovery_label': TEST_LABEL}):
            watch_namespaces(
                event=event,
                name=TEST_NAMESPACE,
                meta={'labels': {'test-label': 'true'}},
                logger=Mock()
            )
            
        mock_workspace_manager.assert_called_once_with(TEST_NAMESPACE)

    @patch('agent.workspace_manager')
    def test_watch_namespaces_modified(self, mock_workspace_manager):
        """Test namespace watch for modified namespace."""
        event = {
            'type': 'MODIFIED',
            'object': {
                'metadata': {
                    'name': TEST_NAMESPACE,
                    'labels': {'test-label': 'true'}
                }
            },
            'old': {
                'metadata': {
                    'labels': {}
                }
            }
        }
        
        # Mock global agent_config
        with patch('agent.agent_config', {'discovery_label': TEST_LABEL}):
            watch_namespaces(
                event=event,
                name=TEST_NAMESPACE,
                meta={'labels': {'test-label': 'true'}},
                logger=Mock()
            )
            
        mock_workspace_manager.assert_called_once_with(TEST_NAMESPACE)

class TestWorkspaceManager:
    @patch('agent.TetrateConnection')
    @patch('agent.Organization')
    @patch('agent.Tenant')
    @patch('agent.Workspace')
    @patch('agent.WorkspaceSetting')
    def test_workspace_manager(
        self, mock_workspace_setting, mock_workspace, mock_tenant,
        mock_organization, mock_tetrate
    ):
        """Test workspace manager functionality."""
        # Mock global agent_config
        with patch('agent.agent_config', {
            'tetrate': {
                'clusterName': 'test-cluster'
            }
        }):
            workspace_manager(TEST_NAMESPACE)
            
        mock_workspace.assert_called_once()
        mock_workspace_setting.assert_called_once() 