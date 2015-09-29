from fuelweb_test.models.environment import EnvironmentModel
from unittest import TestCase
try:
    from unittest import mock
except ImportError: # < PY33
    import mock

class DummyNode:
    def get_ip_address_by_network_name(self, __name):
        return '1.1.1.1'

EXPECTED_CDROM_KEYS = """<Wait>
<Wait>
<Wait>
<Esc>
<Wait>
vmlinuz initrd=initrd.img ks=cdrom:/ks.cfg
 ip=1.1.1.1
 netmask=255.255.255.0
 gw=10.109.25.1
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
 gw=10.109.25.1
 dns1=8.8.8.8
 hostname=nailgun.test.domain.local
 dhcp_interface=
 admin_interface=eth0
 showmenu=no
 wait_for_external_config=yes
 build_images=0
 <Enter>
"""

class TestEnvironment(TestCase):
    def setUp(self):
        pass

    @mock.patch('devops.models.Environment')
    def test_cdrom_keys(self, _mocked_devops_env):
        """Compare get cdrom keys values.

        This is used to verify that it is not broken
        """
        model = EnvironmentModel()
        node = DummyNode()
        assert EXPECTED_CDROM_KEYS == model.get_keys(node)

    @mock.patch('devops.models.Environment')
    def test_usb_keys(self, _mocked_devops_env):
        """Compare get usb keys values.

        This is used to verify that it is not broken
        """
        model = EnvironmentModel()
        node = DummyNode()
        assert EXPECTED_USB_KEYS == model.get_keys(node, iso_connect_as='usb')
