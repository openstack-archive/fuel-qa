#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import time

from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
import netaddr
from proboscis import test
from settings import LOGS_DIR

from fuelweb_test.helpers import decorators
from fuelweb_test.helpers import nessus
from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case
from fuelweb_test.tests.test_neutron_tun_base import NeutronTunHaBase


@test(groups=["nessus"])
class TestNessus(NeutronTunHaBase):
    """Security tests by Nessus

    Environment variables:
        - SECURITY_TEST - True if you have pre-built Nessus qcow image.
          Default: False
        - NESSUS_IMAGE_PATH - path to pre-built Nessus qcow image.
          Default: /var/lib/libvirt/images/nessus.qcow2
        - NESSUS_ADDRESS - Nessus API IP address of pre-installed Nessus.
          Note: Nessus should have access to all virtual networks, all nodes
          and all ports.
          Default: None, address will be detected automatically by scanning
          admin network.
        - NESSUS_PORT - Nessus API port.
          Default: 8834
        - NESSUS_USERNAME - Username to login to Nessus.
        - NESSUS_PASSWORD - Password to login to Nessus.
        - NESSUS_SSL_VERIFY - True if you want verify Nessus SSL
          Default: False
    """

    def enable_password_login_for_ssh_on_slaves(self, slave_names):
        for node_name in slave_names:
            with self.fuel_web.get_ssh_for_node(node_name) as remote:
                remote.execute("sed -i 's/PasswordAuthentication no/"
                               "PasswordAuthentication yes/g' "
                               "/etc/ssh/sshd_config")
                remote.execute("service ssh restart")

    def find_nessus_address(self,
                            nessus_net_name='admin',
                            nessus_port=8834):
        admin_net_cidr = \
            self.env.d_env.get_network(name=nessus_net_name).ip_network

        for address in netaddr.IPNetwork(admin_net_cidr).iter_hosts():
            if tcp_ping(address.format(), nessus_port):
                return address.format()

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["deploy_neutron_tun_ha_nessus"])
    @decorators.log_snapshot_after_test
    def deploy_neutron_tun_ha_nessus(self):
        """Deploy cluster in HA mode with Neutron VXLAN for Nessus

        Scenario:
            1. Create cluster
            2. Add 3 nodes with controller role
            3. Add 2 nodes with compute role
            4. Deploy the cluster
            5. Run network verification
            6. Run OSTF

        Duration 80m
        Snapshot deploy_neutron_tun_ha_nessus
        """
        super(self.__class__, self).deploy_neutron_tun_ha_base(
            snapshot_name="deploy_neutron_tun_ha_nessus")

    @test(depends_on=[deploy_neutron_tun_ha_nessus],
          groups=["nessus_cpa", "nessus_fuel_master_cpa"])
    def nessus_fuel_master_cpa(self):
        """Fuel master Credentialed Patch Audit.

        Scenario:
            1. Configure Nessus to run Credentialed Patch Audit
            against Fuel Master
            2. Start scan
            3. Download scan results

        Duration 40m
        Snapshot nessus_fuel_master_cpa

        """
        self.env.revert_snapshot("deploy_neutron_tun_ha_nessus")

        if CONF.NESSUS_ADDRESS is None:
            CONF.NESSUS_ADDRESS = \
                self.find_nessus_address(nessus_net_name='admin',
                                         nessus_port=CONF.NESSUS_PORT)

        nessus_client = nessus.NessusClient(CONF.NESSUS_ADDRESS,
                                            CONF.NESSUS_PORT,
                                            CONF.NESSUS_USERNAME,
                                            CONF.NESSUS_PASSWORD,
                                            CONF.NESSUS_SSL_VERIFY)

        scan_start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        scan_name = "Scan CPA {0}".format(scan_start_date)

        policies_list = nessus_client.list_policy_templates()
        cpa_policy_template = filter(
            lambda template: template['title'] == 'Credentialed Patch Audit',
            policies_list)[0]

        policy_id = nessus_client.add_cpa_policy(
            scan_name, CONF.ENV_NAME, cpa_policy_template['uuid'])

        scan_id = nessus_client.create_scan(
            scan_name, CONF.ENV_NAME, self.fuel_web.admin_node_ip,
            policy_id, cpa_policy_template['uuid'])
        scan_uuid = nessus_client.launch_scan(scan_id)
        history_id = nessus_client.list_scan_history_ids(scan_id)[scan_uuid]

        check_scan_complete = \
            lambda: (nessus_client.get_scan_status(scan_id, history_id) ==
                     'completed')
        wait(check_scan_complete, interval=10, timeout=60 * 30)

        file_id = nessus_client.export_scan(scan_id, history_id, 'html')
        nessus_client.download_scan_result(scan_id, file_id,
                                           'master_cpa', 'html', LOGS_DIR)

        self.env.make_snapshot("nessus_fuel_master_cpa")

    @test(depends_on=[deploy_neutron_tun_ha_nessus],
          groups=["nessus_wat", "nessus_fuel_master_wat"])
    def nessus_fuel_master_wat(self):
        """Fuel master Advanced Web Services tests.

        Scenario:
            1. Configure Nessus to run Advanced Web Services tests
            againstFuel Master
            2. Start scan
            3. Download scan results

        Duration 40 min
        Snapshot nessus_fuel_master_wat

        """
        self.env.revert_snapshot("deploy_neutron_tun_ha_nessus")

        if CONF.NESSUS_ADDRESS is None:
            CONF.NESSUS_ADDRESS = \
                self.find_nessus_address(nessus_net_name='admin',
                                         nessus_port=CONF.NESSUS_PORT)

        nessus_client = nessus.NessusClient(CONF.NESSUS_ADDRESS,
                                            CONF.NESSUS_PORT,
                                            CONF.NESSUS_USERNAME,
                                            CONF.NESSUS_PASSWORD,
                                            CONF.NESSUS_SSL_VERIFY)

        scan_start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        scan_name = "Scan WAT {0}".format(scan_start_date)

        policies_list = nessus_client.list_policy_templates()
        wat_policy_template = filter(
            lambda template: template['title'] == 'Web Application Tests',
            policies_list)[0]

        policy_id = nessus_client.add_wat_policy(
            scan_name, CONF.ENV_NAME, wat_policy_template['uuid'])

        scan_id = nessus_client.create_scan(
            scan_name, CONF.ENV_NAME, self.fuel_web.admin_node_ip,
            policy_id, wat_policy_template['uuid'])

        scan_uuid = nessus_client.launch_scan(scan_id)
        history_id = nessus_client.list_scan_history_ids(scan_id)[scan_uuid]

        check_scan_complete = \
            lambda: (nessus_client.get_scan_status(scan_id, history_id) ==
                     'completed')
        wait(check_scan_complete, interval=10, timeout=60 * 30)

        file_id = nessus_client.export_scan(scan_id, history_id, 'html')
        nessus_client.download_scan_result(scan_id, file_id,
                                           'master_wat', 'html', LOGS_DIR)

        self.env.make_snapshot("nessus_fuel_master_wat")

    @test(depends_on=[deploy_neutron_tun_ha_nessus],
          groups=["nessus_cpa", "nessus_controller_ubuntu_cpa"])
    def nessus_controller_ubuntu_cpa(self):
        """Ubuntu controller Credentialed Patch Audit.

        Scenario:
            1. Configure Nessus to run Credentialed Patch Audit
            against MOS controller on Ubuntu
            2. Start scan
            3. Download scan results

        Duration 40 min
        Snapshot nessus_controller_ubuntu_cpa

        """
        self.env.revert_snapshot("deploy_neutron_tun_ha_nessus")

        self.enable_password_login_for_ssh_on_slaves(['slave-01'])

        if CONF.NESSUS_ADDRESS is None:
            CONF.NESSUS_ADDRESS = \
                self.find_nessus_address(nessus_net_name='admin',
                                         nessus_port=CONF.NESSUS_PORT)

        nessus_client = nessus.NessusClient(CONF.NESSUS_ADDRESS,
                                            CONF.NESSUS_PORT,
                                            CONF.NESSUS_USERNAME,
                                            CONF.NESSUS_PASSWORD,
                                            CONF.NESSUS_SSL_VERIFY)

        scan_start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        scan_name = "Scan CPA {0}".format(scan_start_date)

        policies_list = nessus_client.list_policy_templates()
        cpa_policy_template = filter(
            lambda template: template['title'] == 'Credentialed Patch Audit',
            policies_list)[0]

        policy_id = nessus_client.add_cpa_policy(
            scan_name, CONF.ENV_NAME, cpa_policy_template['uuid'])

        slave_address = \
            self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']

        scan_id = nessus_client.create_scan(
            scan_name, CONF.ENV_NAME, slave_address,
            policy_id, cpa_policy_template['uuid'])
        scan_uuid = nessus_client.launch_scan(scan_id)
        history_id = nessus_client.list_scan_history_ids(scan_id)[scan_uuid]

        check_scan_complete = \
            lambda: (nessus_client.get_scan_status(scan_id, history_id) ==
                     'completed')
        wait(check_scan_complete, interval=10, timeout=60 * 30)

        file_id = nessus_client.export_scan(scan_id, history_id, 'html')
        nessus_client.download_scan_result(scan_id, file_id,
                                           'controller_cpa', 'html', LOGS_DIR)

        self.env.make_snapshot("nessus_controller_ubuntu_cpa")
