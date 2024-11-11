import os
import unittest
from unittest.mock import patch, MagicMock
import logging
import kopf
from kubernetes import client, config
from agent import configure, agentconfigs_indexer, namespace_event_handler, process_namespace_services, process_service, reconcile_agentconfig

class TestLoggingConfiguration(unittest.TestCase):
    @patch.dict(os.environ, {'LOG_LEVEL': 'INFO'})
    def test_logging_configuration(self):
        logger = logging.getLogger('arca-agent')
        self.assertEqual(logger.level, logging.INFO)

class TestKubernetesConfigLoading(unittest.TestCase):
    @patch('kubernetes.config.load_incluster_config')
    @patch('kubernetes.config.load_kube_config')
    def test_load_kubernetes_config_in_cluster(self, mock_load_kube_config, mock_load_incluster_config):
        mock_load_incluster_config.side_effect = None  # In-cluster config loads without exception
        config.load_incluster_config()
        mock_load_incluster_config.assert_called_once()
        mock_load_kube_config.assert_not_called()

    def test_load_kubernetes_config_local(self):
        with patch('kubernetes.config.load_incluster_config', side_effect=config.ConfigException):
            with patch('kubernetes.config.load_kube_config') as mock_load_kube_config:
                config.load_kube_config()
                mock_load_kube_config.assert_called_once()

    def test_load_kubernetes_config_local_invalid_config(self):
        with patch('kubernetes.config.load_incluster_config', side_effect=config.ConfigException):
            with patch('kubernetes.config.load_kube_config', side_effect=config.ConfigException("Invalid kube-config file. No configuration found.")) as mock_load_kube_config:
                with self.assertLogs('arca-agent', level='ERROR') as log:
                    with self.assertRaises(config.ConfigException):
                        config.load_kube_config()
                    self.assertIn("Invalid kube-config file. No configuration found.", log.output[0])

class TestKopfHandlers(unittest.TestCase):
    @patch('agent.client.CoreV1Api')
    def setUp(self, mock_core_v1_api):
        self.mock_core_v1_api = mock_core_v1_api.return_value

    def test_configure_settings(self):
        settings = kopf.OperatorSettings()
        configure(settings)
        self.assertEqual(settings.execution.max_workers, 10)

    def test_agentconfigs_indexer_valid_label(self):
        body = {
            'spec': {
                'discoveryLabel': 'key=value'
            },
            'metadata': {
                'name': 'test-agentconfig'
            }
        }
        index = agentconfigs_indexer(body)
        self.assertEqual(index, [('key', 'value')])

    def test_agentconfigs_indexer_invalid_label(self):
        body = {
            'spec': {
                'discoveryLabel': 'invalidlabel'
            },
            'metadata': {
                'name': 'test-agentconfig'
            }
        }
        with self.assertLogs('arca-agent', level='ERROR') as log:
            index = agentconfigs_indexer(body)
            self.assertEqual(index, [])
            self.assertIn("Invalid discoveryLabel format", log.output[0])

    @patch('agent.process_namespace_services')
    def test_namespace_event_handler(self, mock_process_namespace_services):
        indexes = {
            'agentconfigs_indexer': {
                ('key', 'value'): [{'metadata': {'name': 'test-agentconfig'}, 'spec': {'discoveryLabel': 'key=value'}}]
            }
        }
        body = {
            'metadata': {
                'name': 'test-namespace',
                'labels': {'key': 'value'}
            }
        }
        namespace_event_handler(spec=None, name='test-namespace', namespace='test-namespace', logger=logging.getLogger(), indexes=indexes, body=body)
        mock_process_namespace_services.assert_called_once_with('test-namespace', 'test-agentconfig')

    @patch('agent.process_service')
    def test_process_namespace_services(self, mock_process_service):
        self.mock_core_v1_api.list_namespaced_service.return_value.items = [
            MagicMock(metadata=MagicMock(name='test-service'))
        ]
        process_namespace_services('test-namespace', 'test-agentconfig')
        mock_process_service.assert_called_once_with('test-namespace', 'test-service', 'test-agentconfig')

    @patch('agent.process_service')
    def test_process_namespace_services_empty_list(self, mock_process_service):
        self.mock_core_v1_api.list_namespaced_service.return_value.items = []
        process_namespace_services('test-namespace', 'test-agentconfig')
        mock_process_service.assert_not_called()

    @patch('agent.core_v1_api.list_namespace')
    @patch('agent.process_namespace_services')
    def test_reconcile_agentconfig(self, mock_process_namespace_services, mock_list_namespace):
        mock_list_namespace.return_value.items = [MagicMock(metadata=MagicMock(name='test-namespace'))]
        spec = {'discoveryLabel': 'key=value'}
        reconcile_agentconfig(spec=spec, name='test-agentconfig', logger=logging.getLogger())
        mock_process_namespace_services.assert_called_once_with('test-namespace', 'test-agentconfig')

    def test_reconcile_agentconfig_invalid_label(self):
        spec = {'discoveryLabel': 'invalidlabel'}
        with self.assertLogs('arca-agent', level='ERROR') as log:
            reconcile_agentconfig(spec=spec, name='test-agentconfig', logger=logging.getLogger())
            self.assertIn("Invalid discoveryLabel format", log.output[0])

    def test_reconcile_agentconfig_missing_label(self):
        spec = {}
        with self.assertLogs('arca-agent', level='ERROR') as log:
            reconcile_agentconfig(spec=spec, name='test-agentconfig', logger=logging.getLogger())
            self.assertIn("missing discoveryLabel", log.output[0])

    @patch('agent.core_v1_api.list_namespace')
    @patch('agent.process_namespace_services')
    def test_reconcile_agentconfig_api_exception(self, mock_process_namespace_services, mock_list_namespace):
        mock_list_namespace.side_effect = client.rest.ApiException(status=500)
        spec = {'discoveryLabel': 'key=value'}
        with self.assertLogs('arca-agent', level='ERROR') as log:
            reconcile_agentconfig(spec=spec, name='test-agentconfig', logger=logging.getLogger())
            self.assertIn("Error listing namespaces", log.output[0])
        mock_process_namespace_services.assert_not_called()

if __name__ == '__main__':
    unittest.main()