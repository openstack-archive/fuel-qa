import re

from unittest import TestCase
try:
    from unittest import mock
except ImportError:  # < PY33
    import mock

from fuelweb_test.models.environment import EnvironmentModel

EXPECTED_CDROM_KEYS = """<Wait>
<Wait>
<Wait>
<Esc>
<Wait>
vmlinuz initrd=initrd.img ks=cdrom:/ks.cfg
 ip=1.1.1.1
 netmask=255.255.255.0
 gw=1.1.1.1
 dns1=8.8.8.8
 hostname=nailgun.test.domain.local
 dhcp_interface=
 admin_interface=eth0
 showmenu=no
 wait_for_external_config=yes
 build_images=0
 <Enter>
"""

EXPECTED_USB_KEYS = """<Wait>
<F12>
2
<Esc><Enter>
<Wait>
vmlinuz initrd=initrd.img ks=hd:LABEL="Mirantis_Fuel":/ks.cfg
 repo=hd:LABEL="Mirantis_Fuel":/
 ip=1.1.1.1
 netmask=255.255.255.0
 gw=1.1.1.1
 dns1=8.8.8.8
 hostname=nailgun.test.domain.local
 dhcp_interface=
 admin_interface=eth0
 showmenu=no
 wait_for_external_config=yes
 build_images=0
 <Enter>
"""


class DummyNode:
    """This is a dummy node class for testing purposes."""
    def __init__(self):
        pass

    def get_ip_address_by_network_name(self, __name):
        return '1.1.1.1'


class TestEnvironment(TestCase):
    """Tests to check environment model."""

    def setUp(self):
        pass

    @mock.patch('devops.models.Environment')
    def test_cdrom_keys(self, _mocked_devops_env):
        """Compare get cdrom keys values.

        This is used to verify that it is not broken
        """
        model = EnvironmentModel()
        node = DummyNode()

        # NOTE(akostrikov) we are getting gateway from env.
        actual_keys = re.sub(r'gw=\d*\.\d*\.\d*\.\d*', 'gw=1.1.1.1',
                             model.get_keys(node),
                             flags=re.MULTILINE)

        self.assertEqual(EXPECTED_CDROM_KEYS, actual_keys)

    @mock.patch('devops.models.Environment')
    def test_usb_keys(self, _mocked_devops_env):
        """Compare get usb keys values.

        This is used to verify that it is not broken
        """
        model = EnvironmentModel()
        node = DummyNode()
        # NOTE(akostrikov) we are getting gateway from env.
        actual_keys = re.sub(r'gw=\d*\.\d*\.\d*\.\d*', 'gw=1.1.1.1',
                             model.get_keys(node, iso_connect_as='usb'),
                             flags=re.MULTILINE)

        self.assertEqual(EXPECTED_USB_KEYS, actual_keys)
