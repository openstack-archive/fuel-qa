#    Copyright 2014 Mirantis, Inc.
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

from proboscis.asserts import assert_equal
from proboscis import test

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_on_error
from fuelweb_test.helpers import checkers
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import CISCO_ACI_PLUGIN_PATH
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])

class cisco_aci_plugin(TestBasic):

    def check_lldp_services_on_node(self, node, services, lldp_is_on):
        logger.debug("\n==Checking services==")
        for service in services:
            cmd = 'pgrep -f '+ service
            logger.debug(cmd)
            _ip = self.fuel_web.get_nailgun_node_by_name(node)['ip']
            res_pgrep = self.env.d_env.get_ssh_to_remote(_ip).execute(cmd)
            logger.debug("\nChecking {0}".format(service))
            logger.debug(cmd)
            if lldp_is_on:
                logger.debug("Service should be enabled")
                assert_equal(0, res_pgrep['exit_code'],
                             'Failed with error {0}'.format(res_pgrep['stderr']))
                if service == "lldp":
                    assert_equal(2, len(res_pgrep['stdout']),
                                 'Failed with error {0}'.format(res_pgrep['stderr']))
                else:
                    assert_equal(1, len(res_pgrep['stdout']),
                                 'Failed with error {0}'.format(res_pgrep['stderr']))
            else:
                logger.debug("Service should be disabled")
                assert_equal(1, res_pgrep['exit_code'],
                             'Failed with error {0}'.format(res_pgrep['stderr']))
                assert_equal(0, len(res_pgrep['stdout']),
                             'Failed with error {0}'.format(res_pgrep['stderr']))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_disabled"])
    @log_snapshot_on_error
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

        Duration 35m
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
            plugin_data = attr['editable']['cisco_aci']['metadata']
            logger.debug(plugin_data)
            plugin_data['enabled'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),False)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_disabled_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_apic_ml2_lldp"])
    @log_snapshot_on_error
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
            3. Create cluster. Plugin is enabled. APIC ML2 driver is selected. lldp is enabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
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

            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = False
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['driver_type']
            plugin_data['value'] = 'ML2'
            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            plugin_data['value'] = True

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),True)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),True)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_apic_ml2_lldp_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_apic_ml2"])
    @log_snapshot_on_error
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
            3. Create cluster. Plugin is enabled. APIC ML2 driver is selected. lldp is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
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

            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = False
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['driver_type']
            plugin_data['value'] = 'ML2'
            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            plugin_data['value'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),False)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_apic_ml2_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp"])
    @log_snapshot_on_error
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

        Duration 35m
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
            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute','cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),False)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_ml2"])
    @log_snapshot_on_error
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
            3. Create cluster. Plugin is enabled. GBP is selected. APIC ML2 driver is selected. lldp is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
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
            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['driver_type']
            plugin_data['value'] = 'ML2'
            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            plugin_data['value'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),False)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_ml2_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_ml2_lldp"])
    @log_snapshot_on_error
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
            3. Create cluster. Plugin is enabled. GBP is selected. APIC ML2 driver is selected. lldp is disabled. lldp is checked.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
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
            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['driver_type']
            plugin_data['value'] = 'ML2'
            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            plugin_data['value'] = True

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),True)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),True)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_ml2_lldp_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp_lldp"])
    @log_snapshot_on_error
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
            3. Create cluster. Plugin is enabled. GBP is selected. APIC GBP driver is selected. lldp is checked.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
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
            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['driver_type']
            plugin_data['value'] = 'GBP'
            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            plugin_data['value'] = True

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),True)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),True)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_lldp_snapshot")

###########################################################################################

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_gbp_apic_gbp"])
    @log_snapshot_on_error
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
            3. Create cluster. Plugin is enabled. GBP is selected. APIC GBP driver is selected. lldp is disabled.
            4. Add 1 node with controller role
            5. Add 1 node with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin health
            9. Run OSTF

        Duration 35m
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
            plugin_data = attr['editable']['cisco_aci']['metadata']
            plugin_data['enabled'] = True
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            plugin_data['value'] = True
            plugin_data = attr['editable']['cisco_aci']['driver_type']
            plugin_data['value'] = 'GBP'
            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            plugin_data['value'] = False

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.verify_network(cluster_id)

        self.check_lldp_services_on_node("slave-01", ("lldp","neutron-driver-apic-agent","neutron-driver-apic-svc"),False)
        self.check_lldp_services_on_node("slave-02", ("lldp","neutron-driver-apic-agent"),False)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.env.make_snapshot("cisco_aci_plugin_gbp_apic_gbp_snapshot")

###########################################################################################

    @test(#depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cisco_aci_plugin_check_uc8"])
    @log_snapshot_on_error
    def deploy_cisco_aci_plugin_check_uc8(self):
        """Use Case 8
        Prerequisites: UI test has been executed
        Scenario:
            1. Check plugin settings.

        Duration 35m
        Snapshot cisco_aci_plugin_check_uc8
        """
        cluster_id = self.fuel_web.get_last_created_cluster()
        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)
        if 'cisco_aci' in attr['editable']:
            plugin_data = attr['editable']['cisco_aci']['metadata']
            assert_equal (True,plugin_data['enabled'],'Error')
            plugin_data = attr['editable']['cisco_aci']['use_gbp']
            assert_equal (True,plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['use_apic']
            assert_equal (True,plugin_data['value'],'Error')

            plugin_data = attr['editable']['cisco_aci']['driver_type']
            assert_equal ('ML2',plugin_data['value'],'Error')

            plugin_data = attr['editable']['cisco_aci']['use_lldp']
            assert_equal (False,plugin_data['value'],'Error')

            plugin_data = attr['editable']['cisco_aci']['apic_hosts']
            assert_equal ('10.0.0.0',plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['apic_username']
            assert_equal ('test_test',plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['apic_password']
            assert_equal ('1',plugin_data['value'],'Error')

            plugin_data = attr['editable']['cisco_aci']['ext_net_name']
            assert_equal ('ext_net_name',plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['ext_net_subnet']
            assert_equal ('0.0.0.0',plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['ext_net_port']
            assert_equal ('999.0.0.0',plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['ext_net_gateway']
            assert_equal ('999.0.0.0',plugin_data['value'],'Error')

            plugin_data = attr['editable']['cisco_aci']['static_config']
            assert_equal ('999.0.0.0',plugin_data['value'],'Error')
            plugin_data = attr['editable']['cisco_aci']['additional_config']
            assert_equal ('999.0.0.0',plugin_data['value'],'Error')

            plugin_data = attr['editable']['cisco_aci']['ext_net_enable']
            assert_equal (True,plugin_data['value'],'Error')
        self.env.make_snapshot("cisco_aci_plugin_check_uc8")