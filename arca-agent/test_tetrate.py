import os
import unittest
from unittest.mock import patch, MagicMock
from tetrate import TSBConnection, Organization, Tenant, Workspace, recursive_merge

class TestTSBConnection(unittest.TestCase):
    @patch.dict(os.environ, {'TSB_API_TOKEN': 'test_token', 'TSB_ENDPOINT': 'https://mock-tsb-server.com'})
    def setUp(self):
        self.connection = TSBConnection()

    def test_get_headers_with_token(self):
        headers = self.connection.get_headers()
        self.assertIn('Authorization', headers)
        self.assertEqual(headers['Authorization'], 'Bearer test_token')

    @patch('requests.request')
    def test_send_request_success(self, mock_request):
        mock_response = MagicMock()
        mock_response.json.return_value = {'result': 'success'}
        mock_response.content = True
        mock_response.raise_for_status = MagicMock()
        mock_request.return_value = mock_response

        response = self.connection.send_request('GET', 'https://mock-tsb-server.com/test')
        self.assertEqual(response, {'result': 'success'})

class TestOrganization(unittest.TestCase):
    @patch('tetrate.TSBConnection.send_request')
    def test_get_organization(self, mock_send_request):
        mock_send_request.return_value = {'name': 'tetrate'}
        org = Organization(name='tetrate')
        result = org.get()
        self.assertEqual(result, {'name': 'tetrate'})

class TestTenant(unittest.TestCase):
    @patch('tetrate.TSBConnection.send_request')
    def test_get_tenant(self, mock_send_request):
        mock_send_request.return_value = {'name': 'arca'}
        org = Organization(name='tetrate')
        tenant = Tenant(organization=org, name='arca')
        result = tenant.get()
        self.assertEqual(result, {'name': 'arca'})

class TestWorkspace(unittest.TestCase):
    @patch('tetrate.TSBConnection.send_request')
    def setUp(self, mock_send_request):
        org = Organization(name='tetrate')
        tenant = Tenant(organization=org, name='arca')
        self.workspace = Workspace(tenant=tenant, name='test-workspace')

    @patch('tetrate.TSBConnection.send_request')
    def test_create_workspace(self, mock_send_request):
        mock_send_request.return_value = {'workspace': {'name': 'test-workspace'}, 'etag': '12345'}
        response = self.workspace.create()
        self.assertIn('workspace', response)
        self.assertEqual(response['workspace']['name'], 'test-workspace')

    @patch('tetrate.TSBConnection.send_request')
    def test_update_workspace(self, mock_send_request):
        mock_send_request.return_value = {'workspace': {'name': 'test-workspace', 'description': 'updated'}, 'etag': '12345'}
        update_properties = {'description': 'updated'}
        response = self.workspace.update(**update_properties)
        self.assertIn('workspace', response)
        self.assertEqual(response['workspace']['description'], 'updated')

    @patch('tetrate.TSBConnection.send_request')
    def test_delete_workspace(self, mock_send_request):
        mock_send_request.return_value = None
        response = self.workspace.delete()
        self.assertIsNone(response)

class TestRecursiveMerge(unittest.TestCase):
    def test_recursive_merge(self):
        d1 = {'a': 1, 'b': {'c': 2}}
        d2 = {'b': {'c': 3, 'd': 4}, 'e': 5}
        recursive_merge(d1, d2)
        self.assertEqual(d1, {'a': 1, 'b': {'c': 3, 'd': 4}, 'e': 5})

if __name__ == '__main__':
    unittest.main()
