from copy import deepcopy
import unittest

from core.models.value_objects import FuelAccessParams

EXAMPLE_YAML_DICT = {
    'OS_USERNAME': 'root',
    'OS_TENANT_NAME': 'project',
    'OS_PASSWORD': 'password',
    'SERVER_ADDRESS': '127.0.0.1',
    'SERVER_PORT': '8000',
    'KEYSTONE_PORT': '5000'
}

EXPECTED_OPENRC_CONTENT = 'export OS_USERNAME="root"\n' \
    'export OS_PASSWORD="root"\n' \
    'export OS_TENANT_NAME="project"\n' \
    'export SERVICE_URL="https://127.0.0.1:8000"\n' \
    'export OS_AUTH_URL="https://127.0.0.1:5000"\n'


class TestFuelAccessParams(unittest.TestCase):
    def test_simple_init(self):
        fuel_access = FuelAccessParams()

        fuel_access.username = 'root'
        self.assertEqual(fuel_access.username, 'root')

        fuel_access.password = 'password'
        self.assertEqual(fuel_access.password, 'password')

        fuel_access.project = 'tenant'
        self.assertEqual(fuel_access.project, 'tenant')

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
        fuel_access = FuelAccessParams.from_yaml_params(EXAMPLE_YAML_DICT)
        self.assertEqual(fuel_access.service_address, '127.0.0.1')
        self.assertEqual(fuel_access.os_auth_url, 'http://127.0.0.1:5000')

    def test_init_from_yaml_content_with_tls(self):
        fuel_access = FuelAccessParams.from_yaml_params(
            EXAMPLE_YAML_DICT,
            tls_service_enabled=True,
            tls_keystone_enabled=True
        )
        self.assertEqual(fuel_access.service_address, '127.0.0.1')
        self.assertEqual(fuel_access.os_auth_url, 'https://127.0.0.1:5000')
        self.assertEqual(fuel_access.service_url, 'https://127.0.0.1:8000')

    def test_failed_from_yaml_content_when_key_absents(self):
        yaml_from_content = deepcopy(EXAMPLE_YAML_DICT)
        yaml_from_content.pop('OS_PASSWORD', None)
        with self.assertRaises(KeyError):
            FuelAccessParams.from_yaml_params(yaml_from_content)

    def test_export_to_openrc(self):
        openrc_content = FuelAccessParams.from_yaml_params(
            EXAMPLE_YAML_DICT,
            tls_service_enabled=True,
            tls_keystone_enabled=True
        ).to_openrc_content()
        self.assertEqual(EXPECTED_OPENRC_CONTENT, openrc_content)
