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
import os
import re

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import CISCO_ACI_PLUGIN_PATH
from fuelweb_test.settings import CISCO_ACI_APIC_HOSTS
from fuelweb_test.settings import CISCO_ACI_APIC_USERNAME
from fuelweb_test.settings import CISCO_ACI_APIC_PASSWORD
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic

# Environment-specific settings
# Let's keep them here in order not to overload settings.py
CISCO_ACI_APIC_STATIC_CONFIG = "apic_switch:101/node-1.test.domain.local," \
                               "node-2.test.domain.local=1/10"

CISCO_ACI_SHARED_CON_NAME = 'ehnet_shared_alex'
CISCO_ACI_APIC_EXT_NET = 'alex_ext_net'
CISCO_ACI_APIC_SYS_ID = 'openstack1'
CISCO_ACI_EXT_EPG = 'ext_epg_alex'
CISCO_ACI_ADD_CONFIG = 'ml2_cisco_apic/apic_vpc_pairs=101:102,103:104'

basic_ml2_conf_settings = ["type_drivers = local,flat,vlan,gre,vxlan",
                           "tenant_network_types = vlan",
                           "network_vlan_ranges =physnet2:1000:1030",
                           "enable_security_group = True",
                           "firewall_driver=neutron.agent.linux."
                           "iptables_firewall."
                           "OVSHybridIptablesFirewallDriver",
                           "integration_bridge=br-int",
                           "bridge_mappings=physnet2:br-prv",
                           "enable_tunneling=False",
                           "polling_interval=2",
                           "l2_population=False",
                           "arp_responder=False"]

basic_neutron_conf_settings = ["admin_tenant_name = admin",
                               "admin_user = admin",
                               "admin_password = admin"]

apic_ml2_conf_cisco_settings = []
apic_ml2_conf_cisco_settings.append("apic_system_id=" +
                                    CISCO_ACI_APIC_SYS_ID)
apic_ml2_conf_cisco_settings.append("apic_hosts = " +
                                    CISCO_ACI_APIC_HOSTS)
apic_ml2_conf_cisco_settings.append("apic_username = " +
                                    CISCO_ACI_APIC_USERNAME)
apic_ml2_conf_cisco_settings.append("apic_password = " +
                                    CISCO_ACI_APIC_PASSWORD)
apic_ml2_conf_cisco_settings.append("apic_name_mapping = use_name")
apic_ml2_conf_cisco_settings.append("shared_context_name=" +
                                    CISCO_ACI_SHARED_CON_NAME)
apic_ml2_conf_cisco_settings.append("external_epg=" + CISCO_ACI_EXT_EPG)
apic_ml2_conf_cisco_settings.append("[apic_external_network:" +
                                    CISCO_ACI_APIC_EXT_NET + "]")

apic_stat_ml2_conf_cisco_settings = []
apic_stat_ml2_conf_cisco_settings.append("[apic_external_network:" +
                                         CISCO_ACI_APIC_EXT_NET + "]")
apic_stat_ml2_conf_cisco_settings.append("node-1.test.domain.local,"
                                         "node-2.test.domain.local=1/10")

gbp_neutron_conf_settings = ["servicechain_drivers=simplechain_driver",
                             "default_quota = -1",
                             "quota_network = -1",
                             "quota_subnet = -1",
                             "quota_port = -1",
                             "quota_security_group = -1",
                             "quota_security_group_rule = -1",
                             "quota_router = -1",
                             "quota_floatingip = -1"]

gbp_heat_conf_settings = ["plugin_dirs=/usr/lib/python2.7/site-packages/"
                          "gbpautomation/heat"]

neutr_path = "/etc/neutron/plugins/ml2/ml2_conf.ini"
ml2_conf_cisco_path = "/etc/neutron/plugins/ml2/ml2_conf_cisco.ini"

ls_command = 'ls -la /usr/local/bin | grep "neutron-rootwrap -> ' \
             '/usr/bin/neutron-rootwrap" | grep "lrwxrwxrwx  1 root root"'


@test(groups=["plugins"])
class CiscoAciPlugin(TestBasic):

    def check_lldp_services_on_node(self, node, services, lldp_is_on):
        """ Checks that services on node are disabled or enabled depending on
            lldp_is_on param
        """
        logger.debug("==Checking services==")
        for service in services:
            cmd = 'pgrep -f ' + service
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            res_pgrep = self.env.d_env.get_ssh_to_remote(_ip).execute(cmd)
            logger.debug("\nChecking {0}".format(service))
            if lldp_is_on:
                logger.debug("Service should be enabled")
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0}'.format
                             (res_pgrep['stderr']))
                if service == "lldp":
                    assert_equal(2, len(res_pgrep['stdout']),
                                 'Failed with error {0}'.format
                                 (res_pgrep['stderr']))
                else:
                    assert_equal(1, len(res_pgrep['stdout']),
                                 'Failed with error {0}'.format
                                 (res_pgrep['stderr']))
            else:
                logger.debug("Service should be disabled")
                assert_equal(1, res_pgrep['exit_code'],
                             'Failed with error {0}'.format
                             (res_pgrep['stderr']))
                assert_equal(0, len(res_pgrep['stdout']),
                             'Failed with error {0}'.format
                             (res_pgrep['stderr']))

    def check_by_ssh(self, node, cmds):
        """Checks that all commands in list cmds return
           at least something
        """
        for cmd in cmds:
            logger.debug(cmd)
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            res = self.env.d_env.get_ssh_to_remote(_ip).execute(cmd)
            assert_equal(1, len(res['stdout']),
                         '{0} command failed with result: {1}'.format
                         (cmd, res['stdout']))

    def check_errors_by_ssh(self, node, cmds):
        """Checks that all commands in list cmds return nothing
        """
        for cmd in cmds:
            logger.debug(cmd)
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            res = self.env.d_env.get_ssh_to_remote(_ip).execute(cmd)
            assert_equal(0, len(res['stdout']),
                         '{0} command failed with result: {1}'.format
                         (cmd, res['stdout']))

    def get_config_from_node(self, node, path):
        """Returns result of cat command for specified path
        """
        cmd = 'cat ' + path
        _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
        result = self.env.d_env.get_ssh_to_remote(_ip).execute(cmd)
        return result['stdout']

    def check_settings_in_config(self, config_instance, settings):
        """Returns True if EVERY item from 'settings'-param is present in
        config_instance (no matter what line exactly)
        Returns list of mismatch fragments it there is even one.
        If 'settings' item starts from '^'(no spaces!), only position
        at start of lines counts for this item ('^' trimmed)
        Commented input lines (by '#') will be ignored
        Need 'import re'

        """
    # Prepare checklist for every item of 'settings'-param
        settings_presence_checklist = [False for i in range(len(settings))]

    # Iterate every line from config_instance
        for line in config_instance:

        # Ignore commented lines
            if re.match(r'^\s*#', line):
                continue

        # Search every setting in current line and mark
        # its presence in checklist
            for number, fragment in enumerate(settings):

            # Check if fragment is simple or with regexp
                if fragment[0] == '^':
                # Case with regex ^ in start of fragment
                    if line.find(fragment[1:]) == 0:
                    # Trimmed fragment starts from 0 position of line
                        settings_presence_checklist[number] = True

                else:

                # Case with simple fragment
                    if line.find(fragment) > -1:
                        settings_presence_checklist[number] = True

        if False in settings_presence_checklist:
            result = []
            for number, fragment in enumerate(settings):
                if not settings_presence_checklist[number]:
                    result.append(fragment)
            assert_equal(True, result,
                         'Cannot find these settings: \n {0}'.format
                        (result))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_disabled"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_disabled(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -DISABLED Cisco ACI plugin.

        Use Case 0 Disabled plugin

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 7m
        Snapshot cisco_aci_plugin_disabled_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC0',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']['metadata']
            pl_data['enabled'] = False

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp",
                                         "neutron-driver-apic-agent",
                                         "neutron-driver-apic-svc"),
                                         False)
        self.check_lldp_services_on_node("slave-02", ("lldp",
                                         "neutron-driver-apic-agent"),
                                         False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_disabled_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_apic_ml2_lldp"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_apic_ml2_lldp(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC ML2 driver,
           -lldp is enabled.

       Use Case 1 (1) Generic APIC ML2 driver with lldp

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               APIC ML2 driver is selected. lldp is enabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 7m
        Snapshot cisco_aci_plugin_apic_ml2_lldp_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC1',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = False
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'ML2'
            pl_data['use_lldp']['value'] = True

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")

        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "cisco_apic_l3,neutron."
                                       "services.metering."
                                       "metering_plugin.MeteringPlugin"])
        self.check_settings_in_config(ml2_conf_cont, basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_conf_comp, basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      apic_ml2_conf_cisco_settings)
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      apic_ml2_conf_cisco_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = ["dpkg -l | grep 'apic '",
                    "dpkg -l | grep apicapi"]
        commands.append(ls_command)
        self.check_by_ssh("slave-01", commands)
        self.check_by_ssh("slave-02", commands)
        cmd_err = ["cat /var/log/neutron/server.log"
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        self.check_lldp_services_on_node("slave-01", ("lldp",
                                         "neutron-cisco-apic-host-agent",
                                         "neutron-cisco-apic-service-agent"),
                                         True)
        self.check_lldp_services_on_node("slave-02", ("lldp",
                                         "neutron-cisco-apic-host-agent"),
                                         True)
        # Should be run only on correct Cisco env
        #self.fuel_web.run_ostf(
        #    cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_apic_ml2_lldp_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_apic_ml2"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_apic_ml2(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC ML2 driver,
           -static configuration.

       Use Case 2 (1) Generic APIC ML2 driver with static config

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               APIC ML2 driver is selected. lldp is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 58m
        Snapshot cisco_aci_plugin_apic_ml2_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC2',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = False
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'ML2'
            pl_data['use_lldp']['value'] = False

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()
            pl_data['static_config']['value'] = CISCO_ACI_APIC_STATIC_CONFIG

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME
        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")
        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "cisco_apic_l3,neutron.services"
                                       ".metering.metering_plugin."
                                       "MeteringPlugin"])
        self.check_settings_in_config(ml2_conf_cont, basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_conf_comp, basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      apic_stat_ml2_conf_cisco_settings)
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      apic_stat_ml2_conf_cisco_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = []
        commands.append(ls_command)
        self.check_by_ssh("slave-02", commands)
        # Should be clarified
        #commands.append("dpkg -l | grep apicapi")
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        # Should be clarified
        #self.check_lldp_services_on_node("slave-01", ("lldp",
        #                                 "neutron-cisco-apic-host-agent",
        #                                 "neutron-cisco-apic-service-agent"),
        #                                 False)
        self.check_lldp_services_on_node("slave-02", ("lldp",
                                         "neutron-cisco-apic-host-agent"),
                                         False)
        # Should be run only on correct Cisco env
        #self.fuel_web.run_ostf(
        #    cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_apic_ml2_snapshot")
##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with GBP.

        Use Case 3 (2a) GBP module and Mapping driver

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled. GBP is checked.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 9m
        Snapshot cisco_aci_plugin_gbp_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC3',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = False

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        heat_conf = self.get_config_from_node("slave-01",
                                              "/etc/heat/heat.conf")
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")
        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "neutron.services.l3_router."
                                       "l3_router_plugin.L3RouterPlugin,"
                                       "gbpservice.neutron.services."
                                       "grouppolicy.plugin."
                                       "GroupPolicyPlugin,gbpservice."
                                       "neutron.services.servicechain."
                                       "servicechain_plugin."
                                       "ServiceChainPlugin,neutron."
                                       "services.metering.metering_plugin"
                                       ".MeteringPlugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["core_plugin = neutron"
                                       ".plugins.ml2.plugin.Ml2Plugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["policy_drivers="
                                       "implicit_policy,resource_mapping"])
        self.check_settings_in_config(neutron_conf,
                                      gbp_neutron_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch"])
        self.check_settings_in_config(ml2_conf_comp,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch"])
        self.check_settings_in_config(heat_conf,
                                      gbp_heat_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = [ls_command]
        self.check_by_ssh("slave-02", commands)
        commands.append("dpkg -l | grep 'group-based-policy '")
        commands.append("dpkg -l | grep python-group-based-policy-client")
        commands.append("dpkg -l | grep group-based-policy-ui")
        commands.append("dpkg -l | grep group-based-policy-automation")
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        self.check_lldp_services_on_node("slave-01", ("lldp",
                                         "neutron-cisco-apic-host-agent",
                                         "neutron-cisco-apic-service-agent"),
                                         False)
        self.check_lldp_services_on_node("slave-02", ("lldp",
                                         "neutron-cisco-apic-host-agent"),
                                         False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_ml2"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_ml2(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC ML2 driver and GBP,
           -static configuration.

       Use Case 4 (2b) GBP module and APIC ML2 driver with static config

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC ML2 driver is selected. lldp is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 56m
        Snapshot cisco_aci_plugin_gbp_apic_ml2_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC4',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'ML2'
            pl_data['use_lldp']['value'] = False

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()
            pl_data['static_config']['value'] = CISCO_ACI_APIC_STATIC_CONFIG

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        heat_conf = self.get_config_from_node("slave-01",
                                              "/etc/heat/heat.conf")
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")
        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "cisco_apic_l3,gbpservice.neutron"
                                       ".services.grouppolicy.plugin."
                                       "GroupPolicyPlugin,gbpservice."
                                       "neutron.services.servicechain."
                                       "servicechain_plugin."
                                       "ServiceChainPlugin,"
                                       "neutron.services.metering."
                                       "metering_plugin.MeteringPlugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["policy_drivers="
                                       "implicit_policy,resource_mapping"])
        self.check_settings_in_config(neutron_conf,
                                      gbp_neutron_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_conf_comp, basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      apic_stat_ml2_conf_cisco_settings)
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      apic_stat_ml2_conf_cisco_settings)
        self.check_settings_in_config(heat_conf,
                                      gbp_heat_conf_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = ["dpkg -l | grep neutron-ml2-driver-apic"]
        commands.append(ls_command)
        self.check_by_ssh("slave-02", commands)
        commands.append("dpkg -l | grep apicapi")
        commands.append("dpkg -l | grep 'group-based-policy '")
        commands.append("dpkg -l | grep python-group-based-policy-client")
        commands.append("dpkg -l | grep group-based-policy-ui")
        commands.append("dpkg -l | grep group-based-policy-automation")
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        # Should be clarified
        #self.check_lldp_services_on_node("slave-01", ("lldp",
        #                                 "neutron-cisco-apic-host-agent",
        #                                 "neutron-cisco-apic-service-agent"),
        #                                 False)
        #self.check_lldp_services_on_node("slave-02", ("lldp",
        #                                 "neutron-cisco-apic-host-agent"),
        #                                 False)

        # Should be run only on correct Cisco env
        #self.fuel_web.run_ostf(
        #    cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_ml2_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_ml2_lldp"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_ml2_lldp(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC ML2 driver and GBP,
           -lldp is enabled.

       Use Case 5 (2b+lldp) GBP module and APIC ML2 driver with lldp

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC ML2 driver is selected. lldp is disabled.
               lldp is checked.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h
        Snapshot cisco_aci_plugin_gbp_apic_ml2_lldp_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC5',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'ML2'
            pl_data['use_lldp']['value'] = True

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        heat_conf = self.get_config_from_node("slave-01",
                                              "/etc/heat/heat.conf")
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")

        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "cisco_apic_l3,gbpservice.neutron"
                                       ".services.grouppolicy.plugin."
                                       "GroupPolicyPlugin,gbpservice."
                                       "neutron.services.servicechain."
                                       "servicechain_plugin."
                                       "ServiceChainPlugin,"
                                       "neutron.services.metering."
                                       "metering_plugin.MeteringPlugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["policy_drivers="
                                       "implicit_policy,resource_mapping"])
        self.check_settings_in_config(neutron_conf,
                                      gbp_neutron_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_conf_comp,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,cisco_apic_ml2"])
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      apic_ml2_conf_cisco_settings)
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      apic_ml2_conf_cisco_settings)
        self.check_settings_in_config(heat_conf,
                                      gbp_heat_conf_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = ["dpkg -l | grep neutron-ml2-driver-apic"]
        commands.append(ls_command)
        self.check_by_ssh("slave-02", commands)
        commands.append("dpkg -l | grep 'apic '")
        commands.append("dpkg -l | grep apicapi")
        commands.append("dpkg -l | grep 'group-based-policy '")
        commands.append("dpkg -l | grep python-group-based-policy-client")
        commands.append("dpkg -l | grep group-based-policy-ui")
        commands.append("dpkg -l | grep group-based-policy-automation")
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        # Should be clarified
        #self.check_lldp_services_on_node("slave-01", ("lldp",
        #                                 "neutron-cisco-apic-host-agent",
        #                                 "neutron-cisco-apic-service-agent"),
        #                                 True)
        #self.check_lldp_services_on_node("slave-02", ("lldp",
        #                                 "neutron-cisco-apic-host-agent"),
        #                                 True)

        # Should be run only on correct Cisco env
        #self.fuel_web.run_ostf(
        #    cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_ml2_lldp_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp_lldp"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_gbp_lldp(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC GBP driver and GBP,
           -lldp is enabled.

       Use Case 6 (3+lldp) GBP module and APIC GBP driver with lldp

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC GBP driver is selected. lldp is checked.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 16m
        Snapshot cisco_aci_plugin_gbp_apic_gbp_lldp_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")
        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC6',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'GBP'
            pl_data['use_lldp']['value'] = True

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        heat_conf = self.get_config_from_node("slave-01",
                                              "/etc/heat/heat.conf")
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")

        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "neutron.services.l3_router."
                                       "l3_router_plugin.L3RouterPlugin,"
                                       "gbpservice.neutron.services."
                                       "grouppolicy.plugin."
                                       "GroupPolicyPlugin,gbpservice."
                                       "neutron.services.servicechain."
                                       "servicechain_plugin."
                                       "ServiceChainPlugin,neutron."
                                       "services.metering.metering_plugin"
                                       ".MeteringPlugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["core_plugin = neutron"
                                       ".plugins.ml2.plugin.Ml2Plugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["policy_drivers="
                                       "implicit_policy,apic"])
        self.check_settings_in_config(neutron_conf,
                                      gbp_neutron_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,apic_gbp"])
        self.check_settings_in_config(ml2_conf_comp,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,apic_gbp"])
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      apic_ml2_conf_cisco_settings)
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      apic_ml2_conf_cisco_settings)
        self.check_settings_in_config(heat_conf,
                                      gbp_heat_conf_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = ["dpkg -l | grep neutron-ml2-driver-apic"]
        commands.append(ls_command)
        self.check_by_ssh("slave-02", commands)
        commands.append("dpkg -l | grep 'apic '")
        commands.append("dpkg -l | grep apicapi")
        commands.append("dpkg -l | grep 'group-based-policy '")
        commands.append("dpkg -l | grep python-group-based-policy-client")
        commands.append("dpkg -l | grep group-based-policy-ui")
        commands.append("dpkg -l | grep group-based-policy-automation")
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        # Should be clarified
        #self.check_lldp_services_on_node("slave-01", ("lldp",
        #                                 "neutron-cisco-apic-host-agent",
        #                                 "neutron-cisco-apic-service-agent"),
        #                                 True)
        #self.check_lldp_services_on_node("slave-02", ("lldp",
        #                                 "neutron-cisco-apic-host-agent"),
        #                                 True)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_lldp_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_gbp(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC GBP driver and GBP,
           -static configuration.

       Use Case 7 (3) GBP module and APIC GBP driver with static configuration

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC GBP driver is selected. lldp is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 2m
        Snapshot cisco_aci_plugin_gbp_apic_gbp_snapshot

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC7',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'GBP'
            pl_data['use_lldp']['value'] = False

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()
            pl_data['static_config']['value'] = CISCO_ACI_APIC_STATIC_CONFIG

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        heat_conf = self.get_config_from_node("slave-01",
                                              "/etc/heat/heat.conf")
        sudoers_conf_cont = self.get_config_from_node("slave-01",
                                                      "/etc/sudoers")
        sudoers_conf_comp = self.get_config_from_node("slave-02",
                                                      "/etc/sudoers")

        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "neutron.services.l3_router."
                                       "l3_router_plugin.L3RouterPlugin,"
                                       "gbpservice.neutron.services."
                                       "grouppolicy.plugin."
                                       "GroupPolicyPlugin,gbpservice."
                                       "neutron.services.servicechain."
                                       "servicechain_plugin."
                                       "ServiceChainPlugin,neutron."
                                       "services.metering.metering_plugin"
                                       ".MeteringPlugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["core_plugin = neutron"
                                       ".plugins.ml2.plugin.Ml2Plugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["policy_drivers="
                                       "implicit_policy,apic"])
        self.check_settings_in_config(neutron_conf,
                                      gbp_neutron_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,apic_gbp"])
        self.check_settings_in_config(ml2_conf_comp, basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,apic_gbp"])
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      apic_stat_ml2_conf_cisco_settings)
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      apic_stat_ml2_conf_cisco_settings)
        self.check_settings_in_config(heat_conf,
                                      gbp_heat_conf_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)
        self.check_settings_in_config(sudoers_conf_cont,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])
        self.check_settings_in_config(sudoers_conf_comp,
                                      ["neutron ALL=(ALL) NOPASSWD: ALL"])

        commands = []
        commands.append(ls_command)
        self.check_by_ssh("slave-02", commands)
        commands.append("dpkg -l | grep apicapi")
        commands.append("dpkg -l | grep 'group-based-policy '")
        commands.append("dpkg -l | grep python-group-based-policy-client")
        commands.append("dpkg -l | grep group-based-policy-ui")
        commands.append("dpkg -l | grep group-based-policy-automation")
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        self.check_lldp_services_on_node("slave-01", ("lldp",
                                         "neutron-cisco-apic-host-agent",
                                         "neutron-cisco-apic-service-agent"),
                                         False)
        self.check_lldp_services_on_node("slave-02", ("lldp",
                                         "neutron-cisco-apic-host-agent"),
                                         False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_snapshot")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp_uc8"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_gbp_uc8(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC GBP driver and GBP,
           -static configuration,
           -external network parameters are specified.

       Use Case 8 (3) GBP module and APIC GBP driver with static configuration
                      and external network parameters

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC GBP driver is selected. lldp is disabled.
               External network parameters are specified.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 56m
        Snapshot cisco_aci_plugin_gbp_apic_gbp_uc8

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC8',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'GBP'
            pl_data['use_lldp']['value'] = False

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_data['ext_net_name']['value'] = "My_ext"
            pl_data['ext_net_subnet']['value'] = "172.16.0.0/24"
            pl_data['ext_net_port']['value'] = "1/34"
            #pl_data['ext_net_switch']['value'] = "203"
            pl_data['ext_net_gateway']['value'] = "172.16.0.1"
            pl_data['ext_net_enable']['value'] = True

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()
            pl_data['static_config']['value'] = CISCO_ACI_APIC_STATIC_CONFIG

            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        ml2_conf_cont = self.get_config_from_node("slave-01", neutr_path)
        ml2_conf_comp = self.get_config_from_node("slave-02", neutr_path)
        ml2_cisco_conf_cont = self.get_config_from_node("slave-01",
                                                        ml2_conf_cisco_path)
        ml2_cisco_conf_comp = self.get_config_from_node("slave-02",
                                                        ml2_conf_cisco_path)
        neutron_conf = self.get_config_from_node("slave-01",
                                                 "/etc/neutron/neutron.conf")
        heat_conf = self.get_config_from_node("slave-01",
                                              "/etc/heat/heat.conf")

        self.check_settings_in_config(neutron_conf,
                                      ["service_plugins ="
                                       "neutron.services.l3_router."
                                       "l3_router_plugin.L3RouterPlugin,"
                                       "gbpservice.neutron.services."
                                       "grouppolicy.plugin."
                                       "GroupPolicyPlugin,gbpservice."
                                       "neutron.services.servicechain."
                                       "servicechain_plugin."
                                       "ServiceChainPlugin,neutron."
                                       "services.metering.metering_plugin"
                                       ".MeteringPlugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["core_plugin = neutron"
                                       ".plugins.ml2.plugin.Ml2Plugin"])
        self.check_settings_in_config(neutron_conf,
                                      ["policy_drivers="
                                       "implicit_policy,apic"])
        self.check_settings_in_config(neutron_conf,
                                      gbp_neutron_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_cont,
                                      ["mechanism_drivers ="
                                       "openvswitch,apic_gbp"])
        self.check_settings_in_config(ml2_conf_comp,
                                      basic_ml2_conf_settings)
        self.check_settings_in_config(ml2_conf_comp,
                                      ["mechanism_drivers ="
                                       "openvswitch,apic_gbp"])
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      ["[apic_external_network:My_ext]"])
        self.check_settings_in_config(ml2_cisco_conf_cont,
                                      ["node-1.test.domain"
                                       ".local,node-2.test.domain"
                                       ".local=1/10"])
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      ["[apic_external_network:My_ext]"])
        self.check_settings_in_config(ml2_cisco_conf_comp,
                                      ["node-1.test.domain"
                                       ".local,node-2.test.domain"
                                       ".local=1/10"])
        self.check_settings_in_config(heat_conf,
                                      gbp_heat_conf_settings)
        self.check_settings_in_config(neutron_conf,
                                      basic_neutron_conf_settings)

        commands = ["dpkg -l | grep apic",
                    "dpkg -l | grep apicapi",
                    "dpkg -l | grep 'group-based-policy '",
                    "dpkg -l | grep python-group-based-policy-client",
                    "dpkg -l | grep group-based-policy-ui",
                    "dpkg -l | grep group-based-policy-automation"]
        self.check_by_ssh("slave-01", commands)
        cmd_err = ["cat /var/log/neutron/server.log "
                   "| grep ApicSessionNotLoggedIn"]
        self.check_errors_by_ssh("slave-01", cmd_err)

        self.check_lldp_services_on_node("slave-01", ("lldp",
                                         "neutron-cisco-apic-host-agent",
                                         "neutron-cisco-apic-service-agent"),
                                         False)
        self.check_lldp_services_on_node("slave-02", ("lldp",
                                         "neutron-cisco-apic-host-agent"),
                                         False)
        # Should be run on correct Cisco enc
        #self.fuel_web.run_ostf(
        #    cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_uc8")

##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp_lldp_l3c"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_gbp_lldp_l3c(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC GBP driver and GBP,
           -static configuration,
           -disable Pre-existing shared l3context option.

       Use Case 9 GBP module and APIC GBP driver with lldp
                  and disabled Pre-existing shared l3context

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC GBP driver is selected. lldp is enabled.
               Pre-existing shared l3context is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 4m
        Snapshot cisco_aci_plugin_gbp_apic_gbp_lldp_l3c_snpsht

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC9',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'GBP'
            pl_data['use_lldp']['value'] = True

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()
            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_external_network']['value'] = CISCO_ACI_APIC_EXT_NET
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['use_pre_existing_l3context']['value'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        cmd_err = []
        # We need to doublecheck this
        #cmd_err.append("cat /etc/neutron/plugins/ml2/ml2_conf.ini | "
        #               "grep shared_context_name=ehnet_shared")
        #self.check_errors_by_ssh("slave-02", cmd_err)
        cmd_err.append("cat /var/log/neutron/server.log "
                       "| grep ApicSessionNotLoggedIn")
        self.check_errors_by_ssh("slave-01", cmd_err)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_lldp_l3c_snpsht")
##############################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp_lldp_pre_net"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_gbp_apic_gbp_lldp_pre_net(self):
        """Deploy cluster:
           -ha mode,
           -neutron VLAN network configuration,
           -enabled Cisco ACI plugin with APIC GBP driver and GBP,
           -static configuration,
           -disable "Use pre-existing external network" option.

       Use Case 10 GBP module and APIC GBP driver with static configuration
                  and disabled "Use pre-existing external network" option

        Prerequisites: FUEL with 2 slaves
        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster. Plugin is enabled.
               GBP is selected. APIC GBP driver is selected. lldp is disabled.
               "Use pre-existing external network" option is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 1h 12m
        Snapshot cisco_aci_plugin_gbp_apic_gbp_lldp_pre_net_snpsht

        """

        self.env.revert_snapshot("ready_with_3_slaves")

        # copy plugin to the master node

        checkers.upload_tarball(
            self.env.d_env.get_admin_remote(),
            CISCO_ACI_PLUGIN_PATH, '/var')

        # install plugin

        checkers.install_plugin_check_code(
            self.env.d_env.get_admin_remote(),
            plugin=os.path.basename(CISCO_ACI_PLUGIN_PATH))

        segment_type = 'vlan'
        cluster_id = self.fuel_web.create_cluster(
            name='UC10',
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": segment_type,
            }
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            pl_data['metadata']['enabled'] = True
            pl_data['use_gbp']['value'] = True
            pl_data['use_apic']['value'] = True
            pl_data['driver_type']['value'] = 'GBP'
            pl_data['use_lldp']['value'] = True

            pl_data['apic_hosts']['value'] = CISCO_ACI_APIC_HOSTS
            pl_data['apic_username']['value'] = CISCO_ACI_APIC_USERNAME
            pl_data['apic_password']['value'] = CISCO_ACI_APIC_PASSWORD

            pl_ntp = attr['editable']['external_ntp']['ntp_list']
            pl_ntp['value'] = self.env.get_admin_node_ip()
            pl_data['additional_config']['value'] = CISCO_ACI_ADD_CONFIG
            pl_data['apic_system_id']['value'] = CISCO_ACI_APIC_SYS_ID
            pl_data['external_epg']['value'] = CISCO_ACI_EXT_EPG
            pl_data['shared_context_name']['value'] = CISCO_ACI_SHARED_CON_NAME
            pl_data['pre_existing_external_network_on']['value'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        cmd_err = ["cat /etc/neutron/plugins/ml2/ml2_conf_cisco.ini |"
                   "grep apic_external_network:My_ext"]
        self.check_errors_by_ssh("slave-02", cmd_err)
        cmd_err.append("cat /var/log/neutron/server.log "
                       "| grep ApicSessionNotLoggedIn")
        self.check_errors_by_ssh("slave-01", cmd_err)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_pre_net_snpsht")

##############################################################################

    @test(groups=["cisco_aci_plugin_check_ui"])
    @log_snapshot_after_test
    def deploy_cisco_aci_plugin_check_ui(self):
        """Use Case 11
        Prerequisites: UI test has been executed
        Scenario:
            1. Check plugin settings.

        Duration 1h35m
        Snapshot cisco_aci_plugin_check_ui

        """

        cluster_id = self.fuel_web.get_last_created_cluster()
        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            pl_data = attr['editable']['cisco_aci']
            plugin_data = pl_data['metadata']
            assert_equal(True, plugin_data['enabled'], 'Error')
            plugin_data = pl_data['use_gbp']
            assert_equal(True, plugin_data['value'], 'Error')
            plugin_data = pl_data['use_apic']
            assert_equal(True, plugin_data['value'], 'Error')

            plugin_data = pl_data['driver_type']
            assert_equal('ML2', plugin_data['value'], 'Error')

            plugin_data = pl_data['use_lldp']
            assert_equal(False, plugin_data['value'], 'Error')

            plugin_data = pl_data['apic_hosts']
            assert_equal('10.0.0.0', plugin_data['value'], 'Error')
            plugin_data = pl_data['apic_username']
            assert_equal('test_test', plugin_data['value'], 'Error')
            plugin_data = pl_data['apic_password']
            assert_equal('1', plugin_data['value'], 'Error')

            plugin_data = pl_data['ext_net_name']
            assert_equal('ext_net_name', plugin_data['value'], 'Error')
            plugin_data = pl_data['ext_net_subnet']
            assert_equal('0.0.0.0', plugin_data['value'], 'Error')
            plugin_data = pl_data['ext_net_port']
            assert_equal('999.0.0.0', plugin_data['value'], 'Error')
            plugin_data = pl_data['ext_net_gateway']
            assert_equal('999.0.0.0', plugin_data['value'], 'Error')

            plugin_data = pl_data['static_config']
            assert_equal('999.0.0.0', plugin_data['value'], 'Error')
            plugin_data = pl_data['additional_config']
            assert_equal('999.0.0.0', plugin_data['value'], 'Error')

            plugin_data = pl_data['ext_net_enable']
            assert_equal(True, plugin_data['value'], 'Error')
        self.env.make_snapshot("cisco_aci_plugin_check_ui")
