import os
import unittest
from unittest.mock import patch, MagicMock, call
import logging
import kopf
from kubernetes import client, config
from agent import (
    configure,
    agentconfigs_indexer,
    namespace_event_handler,
    process_namespace_services,
    process_service,
    reconcile_agentconfig
)

class BaseTestCase(unittest.TestCase):
    """Base test class with common setup"""
    def setUp(self):
        self.logger = logging.getLogger('arca-agent')
        self.patcher = patch('agent.client.CoreV1Api')
        self.mock_core_v1_api = self.patcher.start().return_value

    def tearDown(self):
        self.patcher.stop()

class TestLoggingConfiguration(unittest.TestCase):
    def setUp(self):
        # Reset logging configuration before each test
        logging.getLogger('arca-agent').setLevel(logging.NOTSET)

    @patch.dict(os.environ, {'LOG_LEVEL': 'INFO'})
    def test_logging_configuration(self):
        """Test logger configuration with INFO level"""
        logger = logging.getLogger('arca-agent')
        self.assertEqual(logger.level, logging.INFO)

    @patch.dict(os.environ, {'LOG_LEVEL': 'DEBUG'})
    def test_logging_configuration_debug(self):
        """Test logger configuration with DEBUG level"""
        logger = logging.getLogger('arca-agent')
        self.assertEqual(logger.level, logging.DEBUG)

    @patch.dict(os.environ, {'LOG_LEVEL': 'INVALID'})
    def test_logging_configuration_invalid(self):
        """Test logger configuration with invalid level defaults to INFO"""
        logger = logging.getLogger('arca-agent')
        self.assertEqual(logger.level, logging.INFO)

class TestKubernetesConfigLoading(unittest.TestCase):
    def setUp(self):
        self.logger = logging.getLogger('arca-agent')

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    def test_load_kubernetes_config_in_cluster(self, mock_load_kube_config, mock_load_incluster_config):
        """Test successful in-cluster configuration loading"""
        config.load_incluster_config()
        mock_load_incluster_config.assert_called_once()
        mock_load_kube_config.assert_not_called()

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    def test_load_kubernetes_config_fallback(self, mock_load_kube_config, mock_load_incluster_config):
        """Test fallback to local configuration when in-cluster fails"""
        mock_load_incluster_config.side_effect = config.ConfigException()
        config.load_kube_config()
        mock_load_incluster_config.assert_called_once()
        mock_load_kube_config.assert_called_once()

    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    def test_load_kubernetes_config_both_fail(self, mock_load_kube_config, mock_load_incluster_config):
        """Test handling when both config loading methods fail"""
        mock_load_incluster_config.side_effect = config.ConfigException()
        mock_load_kube_config.side_effect = config.ConfigException("Invalid kube-config")
        
        with self.assertLogs('arca-agent', level='ERROR') as log:
            with self.assertRaises(config.ConfigException):
                config.load_kube_config()
            self.assertIn("Invalid kube-config", log.output[0])

class TestKopfHandlers(BaseTestCase):
    def test_configure_settings(self):
        """Test operator settings configuration"""
        settings = kopf.OperatorSettings()
        configure(settings)
        self.assertEqual(settings.execution.max_workers, 10)
        # Add assertions for other settings if they exist

    def test_agentconfigs_indexer_valid_label(self):
        """Test indexer with valid label format"""
        test_cases = [
            ('key=value', [('key', 'value')]),
            ('app=mysql', [('app', 'mysql')]),
            ('environment=prod', [('environment', 'prod')])
        ]
        
        for label, expected in test_cases:
            with self.subTest(label=label):
                body = {
                    'spec': {'discoveryLabel': label},
                    'metadata': {'name': 'test-config'}
                }
                index = agentconfigs_indexer(body)
                self.assertEqual(index, expected)

    def test_agentconfigs_indexer_invalid_labels(self):
        """Test indexer with various invalid label formats"""
        invalid_labels = [
            'invalidlabel',
            '=value',
            'key=',
            'key==value',
            'key=value=extra'
        ]
        
        for label in invalid_labels:
            with self.subTest(label=label):
                body = {
                    'spec': {'discoveryLabel': label},
                    'metadata': {'name': 'test-config'}
                }
                with self.assertLogs('arca-agent', level='ERROR') as log:
                    index = agentconfigs_indexer(body)
                    self.assertEqual(index, [])
                    self.assertIn("Invalid discoveryLabel format", log.output[0])

    @patch('agent.process_namespace_services')
    def test_namespace_event_handler_with_matching_labels(self, mock_process_namespace_services):
        """Test namespace event handler with matching labels"""
        indexes = {
            'agentconfigs_indexer': {
                ('key', 'value'): [
                    {'metadata': {'name': 'test-config-1'}, 'spec': {'discoveryLabel': 'key=value'}},
                    {'metadata': {'name': 'test-config-2'}, 'spec': {'discoveryLabel': 'key=value'}}
                ]
            }
        }
        
        body = {
            'metadata': {
                'name': 'test-namespace',
                'labels': {'key': 'value', 'other': 'label'}
            }
        }
        
        namespace_event_handler(
            spec=None,
            name='test-namespace',
            namespace='test-namespace',
            logger=self.logger,
            indexes=indexes,
            body=body
        )
        
        expected_calls = [
            call('test-namespace', 'test-config-1'),
            call('test-namespace', 'test-config-2')
        ]
        mock_process_namespace_services.assert_has_calls(expected_calls)

    @patch('agent.process_service')
    def test_process_namespace_services_with_multiple_services(self, mock_process_service):
        """Test processing multiple services in a namespace"""
        services = [
            MagicMock(metadata=MagicMock(name='service-1')),
            MagicMock(metadata=MagicMock(name='service-2')),
            MagicMock(metadata=MagicMock(name='service-3'))
        ]
        self.mock_core_v1_api.list_namespaced_service.return_value.items = services
        
        process_namespace_services('test-namespace', 'test-config')
        
        expected_calls = [
            call('test-namespace', 'service-1', 'test-config'),
            call('test-namespace', 'service-2', 'test-config'),
            call('test-namespace', 'service-3', 'test-config')
        ]
        mock_process_service.assert_has_calls(expected_calls)

    @patch('agent.core_v1_api.list_namespace')
    @patch('agent.process_namespace_services')
    def test_reconcile_agentconfig_error_handling(self, mock_process_namespace_services, mock_list_namespace):
        """Test error handling in reconcile_agentconfig"""
        error_cases = [
            (client.rest.ApiException(status=403), "Error listing namespaces: Forbidden"),
            (client.rest.ApiException(status=404), "Error listing namespaces: Not Found"),
            (Exception("Unexpected error"), "Error listing namespaces: Unexpected error")
        ]
        
        for error, expected_message in error_cases:
            with self.subTest(error=error):
                mock_list_namespace.side_effect = error
                spec = {'discoveryLabel': 'key=value'}
                
                with self.assertLogs('arca-agent', level='ERROR') as log:
                    reconcile_agentconfig(spec=spec, name='test-config', logger=self.logger)
                    self.assertIn(expected_message, log.output[0])
                mock_process_namespace_services.assert_not_called()

if __name__ == '__main__':
    unittest.main()