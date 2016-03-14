import mock
import unittest

from os_usage import clients

class FakeLoader():
    def load_from_options(
        self,
        auth_url=None,
        username=None,
        password=None,
        project_id=None
    ):
        """ Does Nothing"""
        return self

FAKE_LOADER = FakeLoader()

class TestClients(unittest.TestCase):
    """Unit tests for the client manager"""

    auth_url = 'auth_url'
    username = 'username'
    password = 'password'
    project_id = 'project_id'

    def create_manager(self):
        """Creates a ClientManager instance."""
        return clients.ClientManager(
            auth_url=self.auth_url,
            username=self.username,
            password=self.password,
            project_id=self.project_id
        )

    def test_init(self):
        """Tests the __init__ method.

        Session and client instances should be None.
        Credentials should be what was provided.
        """
        clients = self.create_manager()
        self.assertEquals(clients.auth_url, self.auth_url)
        self.assertEquals(clients.username, self.username)
        self.assertEquals(clients.password, self.password)
        self.assertEquals(clients.project_id, self.project_id)
        self.assertIsNone(clients.session)
        self.assertIsNone(clients.nova)
        self.assertIsNone(clients.glance)
        self.assertIsNone(clients.cinder)

    @mock.patch(
        'os_usage.clients.session.Session',
        return_value='session'
    )
    @mock.patch(
        'os_usage.clients.loading.get_plugin_loader',
        return_value=FAKE_LOADER
    )
    def test_get_session_new(self, mocked_loader, mocked_session):
        """Tests get_session without an existing session."""
        clients = self.create_manager()
        self.assertIsNone(clients.session)
        session = clients.get_session()
        mocked_loader.assert_called_once_with('password')
        mocked_session.assert_called_once_with(auth=FAKE_LOADER)
        self.assertEquals(clients.session, 'session')

    def test_get_session_old(self):
        """Tests get_session with an existing session"""
        clients = self.create_manager()
        clients.session = 'session'
        self.assertEquals('session', clients.get_session())

    def test_get_nova_existing(self):
        """Tests get_nova with existing nova."""
        clients = self.create_manager()
        clients.nova = 'nova'
        nova = clients.get_nova()
        self.assertEquals(nova, 'nova')

    @mock.patch(
        'os_usage.clients.novaclient.Client',
        return_value='nova'
    )
    def test_get_nova_new(self, mocked_client):
        """Tests get_nova  without existing nova."""
        clients = self.create_manager()
        self.assertIsNone(clients.nova)
        clients.session = 'session'
        version = '3'
        nova = clients.get_nova(version=version)
        mocked_client.assert_called_once_with(version, session='session')

    def test_get_glance_existing(self):
        """Tests get_glance with existing glance."""
        clients = self.create_manager()
        clients.glance = 'glance'
        glance = clients.get_glance()
        self.assertEquals(glance, 'glance')

    @mock.patch(
        'os_usage.clients.glanceclient',
        return_value='glance'
    )
    def test_get_glance_new(self, mocked_client):
        """Tests get_glance without existing glance."""
        clients = self.create_manager()
        self.assertIsNone(clients.glance)
        clients.session = 'session'
        version = '3'
        glance = clients.get_glance(version=version)
        mocked_client.assert_called_once_with(version, session='session')

    def test_get_cinder_existing(self):
        """Tests get_cinder with existing cinder."""
        clients = self.create_manager()
        clients.cinder = 'cinder'
        cinder = clients.get_cinder()
        self.assertEquals(cinder, 'cinder')

    @mock.patch(
        'os_usage.clients.cinderclient.Client',
        return_value='cinder'
    )
    def test_get_cinder_new(self, mocked_client):
        """Tests get_cinder without existing cinder."""
        clients = self.create_manager()
        self.assertIsNone(clients.cinder)
        clients.session = 'session'
        version = '3'
        cinder = clients.get_cinder(version=version)
        mocked_client.assert_called_once_with(version, session='session')
