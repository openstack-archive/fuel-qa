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

from devops.helpers.helpers import wait
from proboscis import test

from fuelweb_test.helpers import nessus
from fuelweb_test import settings as CONF
from fuelweb_test.tests import base_test_case


@test(groups=["nessus"])
class TestNessus(base_test_case.TestBasic):
    """Security tests by Nessus."""

    def enable_password_login_for_ssh_on_slaves(self, slave_names):
        for node_name in slave_names:
            with self.fuel_web.get_ssh_for_node(node_name) as remote:
                remote.execute("sed -i 's/PasswordAuthentication no/"
                               "PasswordAuthentication yes/g' "
                               "/etc/ssh/sshd_config")
                remote.execute("service ssh restart")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_5],
          groups=["ready_nessus_neutron_vlan_ha_with_5_slaves"])
    def prepare_nessus_neutron_vlan_ha_with_5_slaves(self):
        """ Deploy HA with 2 controllers for nessus.

        Scenario:
            1. Revert snapshot ready_with_5_slaves_jumbo_frames
            2. Create cluster with neutron VLAN
            3. Add 3 node with controller role
            4. Add 2 nodes with compute role
            5. Deploy the cluster
            6. Run network verification
            7. Run OSTF

        Duration 120m
        Snapshot ready_nessus_neutron_vlan_ha_with_5_slaves

        """
        self.check_run("ready_nessus_neutron_vlan_ha_with_5_slaves")
        self.env.revert_snapshot("ready_with_5_slaves")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=CONF.DEPLOYMENT_MODE_HA,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": 'vlan',
            }
        )

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute'],
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.fuel_web.verify_network(cluster_id)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("ready_nessus_neutron_vlan_ha_with_5_slaves",
                               is_make=True)

    @test(depends_on=[prepare_nessus_neutron_vlan_ha_with_5_slaves],
          groups=["nessus_cpa", "nessus_fuel_master_cpa"])
    def run_fuel_master_cpa(self):
        """Fuel master Credentialed Patch Audit.

        Scenario:
            1. Configure Nessus to run Credentialed Patch Audit
            against Fuel Master
            2. Start scan
            3. Download scan results

        Duration 100m
        Snapshot nessus_fuel_master_cpa

        """
        self.env.revert_snapshot("ready_nessus_neutron_vlan_ha_with_5_slaves")

        nessus_client = nessus.NessusClient(CONF.NESSUS_ADDRESS,
                                            CONF.NESSUS_PORT,
                                            CONF.NESSUS_USERNAME,
                                            CONF.NESSUS_PASSWORD,
                                            CONF.NESSUS_SSL_VERIFY)

        scan_start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        scan_name = "Scan CPA {0}".format(scan_start_date)

        policies_list = nessus_client.list_policy_templates()
        cpa_policy_template_id = policies_list['Credentialed Patch Audit']
        policy_id = nessus_client.add_cpa_policy(
            scan_name, CONF.ENV_NAME, cpa_policy_template_id)

        scan_id = nessus_client.create_scan(
            scan_name, CONF.ENV_NAME, self.fuel_web.admin_node_ip,
            policy_id, cpa_policy_template_id)
        scan_uuid = nessus_client.launch_scan(scan_id)
        history_id = nessus_client.list_scan_history_ids(scan_id)[scan_uuid]

        check_scan_complete = \
            lambda: (nessus_client.get_scan_status(scan_id, history_id) ==
                     'completed')
        wait(check_scan_complete, interval=10, timeout=600)

        file_id = nessus_client.export_scan(scan_id, history_id, 'html')
        nessus_client.download_scan_result(scan_id, file_id, 'html')

        self.env.make_snapshot("nessus_fuel_master_cpa")

    @test(depends_on=[prepare_nessus_neutron_vlan_ha_with_5_slaves],
          groups=["nessus_wat", "nessus_fuel_master_wat"])
    def run_fuel_master_wat(self):
        """Fuel master Advanced Web Services tests.

        Scenario:
            1. Configure Nessus to run Advanced Web Services tests
            againstFuel Master
            2. Start scan
            3. Download scan results

        Duration 30 min
        Snapshot run_fuel_master_wat

        """
        self.env.revert_snapshot("ready_nessus_neutron_vlan_ha_with_5_slaves")

        nessus_client = nessus.NessusClient(CONF.NESSUS_ADDRESS,
                                            CONF.NESSUS_PORT,
                                            CONF.NESSUS_USERNAME,
                                            CONF.NESSUS_PASSWORD,
                                            CONF.NESSUS_SSL_VERIFY)

        scan_start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        scan_name = "Scan WAT {0}".format(scan_start_date)

        policies_list = nessus_client.list_policy_templates()
        wat_policy_template_id = policies_list['Web Application Tests']
        policy_id = nessus_client.add_wat_policy(
            scan_name, CONF.ENV_NAME, wat_policy_template_id)

        scan_id = nessus_client.create_scan(
            scan_name, CONF.ENV_NAME, self.fuel_web.admin_node_ip,
            policy_id, wat_policy_template_id)

        scan_uuid = nessus_client.launch_scan(scan_id)
        history_id = nessus_client.list_scan_history_ids(scan_id)[scan_uuid]

        check_scan_complete = \
            lambda: (nessus_client.get_scan_status(scan_id, history_id) ==
                     'completed')
        wait(check_scan_complete, interval=10, timeout=600)

        file_id = nessus_client.export_scan(scan_id, history_id, 'html')
        nessus_client.download_scan_result(scan_id, file_id, 'html')

        self.env.make_snapshot("nessus_fuel_master_wat")

    @test(depends_on=[prepare_nessus_neutron_vlan_ha_with_5_slaves],
          groups=["nessus_cpa", "nessus_controller_ubuntu_cpa"])
    def run_ubuntu_controller_cpa(self):
        """Ubuntu controller Credentialed Patch Audit.

        Scenario:
            1. Configure Nessus to run Credentialed Patch Audit
            against MOS controller on Ubuntu
            2. Start scan
            3. Download scan results

        Duration 100 min
        Snapshot nessus_controller_ubuntu_cpa

        """
        self.env.revert_snapshot("ready_nessus_neutron_vlan_ha_with_5_slaves")

        self.enable_password_login_for_ssh_on_slaves(['slave-01'])

        nessus_client = nessus.NessusClient(CONF.NESSUS_ADDRESS,
                                            CONF.NESSUS_PORT,
                                            CONF.NESSUS_USERNAME,
                                            CONF.NESSUS_PASSWORD,
                                            CONF.NESSUS_SSL_VERIFY)

        scan_start_date = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())

        scan_name = "Scan CPA {0}".format(scan_start_date)

        policies_list = nessus_client.list_policy_templates()
        cpa_policy_template_id = policies_list['Credentialed Patch Audit']
        policy_id = nessus_client.add_cpa_policy(
            scan_name, CONF.ENV_NAME, cpa_policy_template_id)

        slave_address = \
            self.fuel_web.get_nailgun_node_by_name('slave-01')['ip']

        scan_id = nessus_client.create_scan(
            scan_name, CONF.ENV_NAME, slave_address,
            policy_id, cpa_policy_template_id)
        scan_uuid = nessus_client.launch_scan(scan_id)
        history_id = nessus_client.list_scan_history_ids(scan_id)[scan_uuid]

        check_scan_complete = \
            lambda: (nessus_client.get_scan_status(scan_id, history_id) ==
                     'completed')
        wait(check_scan_complete, interval=10, timeout=600)

        file_id = nessus_client.export_scan(scan_id, history_id, 'html')
        nessus_client.download_scan_result(scan_id, file_id, 'html')

        self.env.make_snapshot("nessus_controller_ubuntu_cpa")
