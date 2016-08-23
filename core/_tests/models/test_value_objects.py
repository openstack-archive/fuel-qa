import unittest

from mock import patch
from mock import call

from core.models.value_objects import FuelAccessParams


class TestFuelAccessParams(unittest.TestCase):
    def setUp(self):
        pass
        # self.client = CollectorClient(collector_ip=ip, endpoint=endpoint)
    """
            self._username = None
        self._password = None
        self._project = None
        self._service_address = None
        self._service_port = None
        self._keystone_address = None
        self._keystone_port = None
        self._tls_service_enabled = tls_service_enabled
        self._tls_keystone_enabled = tls_keystone_enabled
        """

    def test_simple_init(self):
        fuel_access = FuelAccessParams()

        fuel_access.username = 'root'
        self.assertEqual(fuel_access.username, 'root')

        fuel_access.password = 'password'
        self.assertEqual(fuel_access.password, 'password')

        fuel_access._project = 'tenant'
        self.assertEqual(fuel_access._project, 'tenant')

        fuel_access.service_address = '127.0.0.1'
        self.assertEqual(fuel_access.service_address, '127.0.0.1')

        fuel_access.service_port = '777'
        self.assertEqual(fuel_access.service_port, '777')

        fuel_access.keystone_address = '127.0.0.1'
        self.assertEqual(fuel_access.keystone_address, '127.0.0.1')

        fuel_access.keystone_port = '5000'
        self.assertEqual(fuel_access.keystone_port, '5000')

    def test_tls_init(self):
        fuel_access = FuelAccessParams(tls_keystone_enabled=True,
                                       tls_service_enabled=False)
        fuel_access.service_address = '127.0.0.1'
        fuel_access.service_port = '777'

        fuel_access.keystone_address = '127.0.0.1'
        fuel_access.keystone_port = '5000'

        self.assertEqual(fuel_access.service_url, 'http://127.0.0.1:777')
        self.assertEqual(fuel_access.os_auth_url, 'https://127.0.0.1:5000')

    def test_init_from_yaml_content(self):
        yaml_from_content = {
            'OS_USERNAME': 'root',
            'OS_PASSWORD': 'password',
            'OS_TENANT_NAME': 'project',
            'SERVER_ADDRESS': '127.0.0.1',
            'SERVER_PORT': '8000',
            'KEYSTONE_PORT': '5000'
        }
        fuel_access = FuelAccessParams.from_yaml_params(yaml_from_content)
        self.assertEqual(fuel_access.service_address, '127.0.0.1')
        self.assertEqual(fuel_access.os_auth_url, 'http://127.0.0.1:5000')

    def test_init_from_yaml_content_with_tls(self):
        yaml_from_content = {
            'OS_USERNAME': 'root',
            'OS_PASSWORD': 'password',
            'OS_TENANT_NAME': 'project',
            'SERVER_ADDRESS': '127.0.0.1',
            'SERVER_PORT': '8000',
            'KEYSTONE_PORT': '5000'
        }
        fuel_access = FuelAccessParams.from_yaml_params(
            yaml_from_content,
            tls_service_enabled=True,
            tls_keystone_enabled=True
        )
        self.assertEqual(fuel_access.service_address, '127.0.0.1')
        self.assertEqual(fuel_access.os_auth_url, 'https://127.0.0.1:5000')

    def test_failed_from_yaml_content_when_key_absents(self):
        yaml_from_content = {
            'OS_USERNAME': 'root',
            'OS_TENANT_NAME': 'project',
            'SERVER_ADDRESS': '127.0.0.1',
            'SERVER_PORT': '8000',
            'KEYSTONE_PORT': '5000'
        }
        with self.assertRaises(KeyError):
            FuelAccessParams.from_yaml_params(yaml_from_content)


