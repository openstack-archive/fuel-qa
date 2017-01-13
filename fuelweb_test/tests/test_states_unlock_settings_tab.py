#    Copyright 2016 Mirantis, Inc.
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

import copy

from netaddr import IPNetwork
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["unlock_settings_tab_states"])
class UnlockSettingsTabStates(TestBasic):
    """UnlockSettingsTabStates."""  # TODO documentation

    def __init__(self):
        super(UnlockSettingsTabStates, self).__init__()
        self._cluster_id = None

    @property
    def cluster_id(self):
        return self._cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        self._cluster_id = cluster_id

    def create_cluster(self):
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE)

    def update_nodes(self, nodes):
        self.fuel_web.update_nodes(self.cluster_id, nodes)

    def provision_nodes(self):
        self.fuel_web.provisioning_cluster_wait(self.cluster_id)

    def deploy_selected_nodes(self, nodes):
        logger.info(
            "Start deploying of selected nodes with ids: {}".format(nodes))
        task = self.fuel_web.client.deploy_nodes(self.cluster_id, nodes)
        self.fuel_web.assert_task_success(task)

    def deploy_cluster(self, do_not_fail=False):
        try:
            self.fuel_web.deploy_cluster_wait(self.cluster_id)
        except AssertionError:
            if do_not_fail:
                logger.info("Cluster deployment was failed due to "
                            "expected error with netconfig")
            else:
                raise

    def get_cluster_attributes(self):
        return self.fuel_web.client.get_cluster_attributes(self.cluster_id)

    def get_networks(self):
        return self.fuel_web.client.get_networks(self.cluster_id)

    def get_deployed_cluster_attributes(self):
        return self.fuel_web.client.get_deployed_cluster_attributes(
            self.cluster_id)

    def get_deployed_network_configuration(self):
        return self.fuel_web.client.get_deployed_network_configuration(
            self.cluster_id)

    def get_default_cluster_settings(self):
        return self.fuel_web.client.get_default_cluster_settings(
            self.cluster_id)

    def update_cluster_attributes(self, attributes):
        self.fuel_web.client.update_cluster_attributes(self.cluster_id,
                                                       attributes)

    def update_network_settings(self,
                                networking_parameters=None, networks=None):
        self.fuel_web.client.update_network(
            self.cluster_id, networking_parameters=networking_parameters,
            networks=networks)

    @staticmethod
    def change_settings(attrs):
        options = {'common': ['puppet_debug',
                              'resume_guests_state_on_host_boot',
                              'nova_quota'],
                   'public_network_assignment': ['assign_to_all_nodes'],
                   'neutron_advanced_configuration': ['neutron_qos']
                   }
        logger.info(
            "The following settings will be changed: {}".format(options))
        editable = attrs['editable']
        for group in options:
            for opt in options[group]:
                value = editable[group][opt]['value']
                editable[group][opt]['value'] = not value
        return attrs

    @staticmethod
    def compare_networks(old_settings, new_settings):
        logger.debug("Old setting are:{}".format(old_settings))
        logger.debug("New setting are:{}".format(new_settings))
        for setting in old_settings:
            if setting != 'networks':
                if old_settings[setting] != new_settings[setting]:
                    return False
        for net1 in old_settings['networks']:
            for net2 in new_settings['networks']:
                if net1['name'] == net2['name'] and set(net1) != set(net2):
                    return False
                else:
                    continue
        return True

    @staticmethod
    def compare_settings(old_attrs, new_attrs):
        skipped_options =\
            [
                u'service_user.password',
                u'public_ssl.cert_data',
                u'storage.bootstrap_osd_key',
                u'storage.radosgw_key',
                u'storage.admin_key',
                u'storage.fsid',
                u'storage.mon_key',
                u'workloads_collector.password',
                u'murano_settings.murano_glance_artifacts_plugin',
                u'additional_components.murano_glance_artifacts_plugin',
                u'common.debug',
                u'external_dns.dns_list',
                u'external_ntp.ntp_list',
                u'public_ssl.horizon',
                u'public_ssl.services',
                u'public_ssl.cert_source',
                u'operator_user.password',
                u'neutron_advanced_configuration.metadata'
            ]
        logger.debug("Old default cluster settings: {}".format(old_attrs))
        logger.debug("New default cluster settings: {}".format(new_attrs))
        editable_old = old_attrs['editable']
        editable_new = new_attrs['editable']
        for group in editable_old:
            for opt in editable_old[group]:
                key = '.'.join([group, opt])
                if key in skipped_options or 'metadata' in key:
                    continue
                else:
                    old_val = editable_old[group][opt]['value']
                    new_val = editable_new[group][opt]['value']
                    if old_val != new_val:
                        logger.debug(
                            "Failed key old value: {0}:{1}".format(key,
                                                                   old_val))
                        logger.debug(
                            "Failed key new value: {0}:{1}".format(key,
                                                                   new_val))
                        return False
        return True

    def change_netconfig_task(self, fail=True):
        ssh_manager = self.ssh_manager
        admin_ip = ssh_manager.admin_ip
        taskfile = "/etc/puppet/modules/osnailyfacter/modular/netconfig/" \
                   "connectivity_tests.pp"
        if fail:
            cmd = \
                "echo 'fail(\"Emulate deployment failure after " \
                "netconfig!\")' >> {}".format(taskfile)
        else:
            cmd = "sed -i '/^fail.*$/d' {}".format(taskfile)

        ssh_manager.execute_on_remote(admin_ip, cmd)

    def run_ostf(self):
        self.fuel_web.run_ostf(self.cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["partially_deployed_unlock"])
    @log_snapshot_after_test
    def partially_deployed_unlock(self):
        """Check settings tab is unlocked for partially-deployed environment

        Scenario:
            1. Revert snapshot ready_with_3_slaves
            2. Create a new env
            3. Add controller and 2 computes
            4. Provision nodes without deploy
            5. Select some nodes (not all) and deploy them
            6. Download current settings and modify some of them
            7. Upload changed settings
            8. Re-deploy cluster
            9. Run OSTF
            10. Make snapshot

        Duration 90m
        Snapshot partially_deployed_unlock
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        self.show_step(2)
        self.create_cluster()
        self.show_step(3)
        nodes_dict = {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['compute']
        }
        self.update_nodes(nodes_dict)
        self.show_step(4)
        self.provision_nodes()
        self.show_step(5)
        controller_id = \
            self.fuel_web.get_nailgun_node_by_name("slave-01")['id']
        compute_id = self.fuel_web.get_nailgun_node_by_name("slave-02")['id']
        self.deploy_selected_nodes([str(controller_id), str(compute_id)])
        self.show_step(6)
        attrs = self.get_cluster_attributes()
        new_attrs = self.change_settings(attrs)
        self.show_step(7)
        self.update_cluster_attributes(new_attrs)
        self.show_step(8)
        self.deploy_cluster()
        self.show_step(9)
        self.run_ostf()
        self.show_step(10)
        self.env.make_snapshot("partially_deployed_unlock")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["failed_deploy_unlock"])
    @log_snapshot_after_test
    def failed_deploy_unlock(self):
        """Check settings tab is unlocked for a deployed with error environment

        Scenario:
            1. Revert snapshot ready_with_3_slaves
            2. Create a new env
            3. Add controller and 2 computes
            4. Change netconfig task to fail deploy
            5. Deploy the env
            6. Download current settings and modify some of them
            7. Upload changed settings
            8. Change netconfig task to normal state
            9. Re-deploy cluster
            10. Run OSTF
            11. Make snapshot

        Duration 60m
        Snapshot failed_deploy_unlock
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")
        self.show_step(2)
        self.create_cluster()
        self.show_step(3)
        nodes_dict = {
            'slave-01': ['controller'],
            'slave-02': ['compute'],
            'slave-03': ['compute']
        }
        self.update_nodes(nodes_dict)
        self.show_step(4)
        self.change_netconfig_task()
        self.show_step(5)
        self.deploy_cluster(do_not_fail=True)
        self.show_step(6)
        attrs = self.get_cluster_attributes()
        new_attrs = self.change_settings(attrs)
        self.show_step(7)
        self.update_cluster_attributes(new_attrs)
        self.show_step(8)
        self.change_netconfig_task(fail=False)
        self.show_step(9)
        self.deploy_cluster()
        self.show_step(10)
        self.run_ostf()
        self.show_step(11)
        self.env.make_snapshot("failed_deploy_unlock")

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["unlock_settings_tab_positive"])
    @log_snapshot_after_test
    def unlock_settings_tab_positive(self):
        """Check settings and network tabs is unlocked for a positively
        deployed and redeployed cluster

        Scenario:
            1. Create cluster
            2. Download default cluster settings
            3. Create custom_config and upload it to cluster
            4. Add 3 nodes with controller role and 2 nodes with compute role
            5. Deploy the cluster
            6. Stop deployment process
            7. Get current settings
            8. Change and save them (that means settings are unlocked)
            9. Redeploy cluster via api
            10. Get cluster and network settings via api (api load deployed)
            11. Compare settings from step 8 and 10 (them must be equal)
            12. Get default settings via api (load defaults)
            13. Compare settings from step 2 and 13 (them must be equal)
            14. Redeploy cluster
            15. Stop deployment process
            16. Redeploy cluster
            17. Run OSTF

        Duration 50m
        Snapshot unlock_settings_tab_positive

        """
        self.env.revert_snapshot("ready_with_5_slaves")
        self.show_step(1)
        self.create_cluster()
        self.show_step(2)
        default_config = self.get_cluster_attributes()
        self.show_step(3)
        new_config = copy.deepcopy(default_config)
        editable = new_config['editable']
        editable['access']['email']['value'] = 'custom@localhost'
        editable[
            'neutron_advanced_configuration']['neutron_qos']['value'] = True
        editable['common']['puppet_debug']['value'] = False
        self.update_cluster_attributes(new_config)
        self.show_step(4)
        self.update_nodes(
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.show_step(5)
        self.fuel_web.deploy_cluster_wait_progress(cluster_id=self.cluster_id,
                                                   progress=10)
        self.show_step(6)
        self.fuel_web.stop_deployment_wait(self.cluster_id)
        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.nodes().slaves[:5], timeout=10 * 60)
        self.show_step(7)
        new_cluster_settings = self.get_cluster_attributes()
        self.show_step(8)
        editable = new_cluster_settings['editable']
        editable['access']['email']['value'] = 'custom2@localhost'
        editable['public_ssl']['horizon']['value'] = False
        editable['public_ssl']['services']['value'] = False
        self.update_cluster_attributes(new_cluster_settings)
        current_network_settings = self.get_networks()
        networking_parameters = \
            current_network_settings['networking_parameters']
        networking_parameters['vlan_range'] = [1015, 1030]
        networking_parameters['gre_id_range'] = [3, 65535]
        current_networks = current_network_settings['networks']
        for network in current_networks:
            if network['cidr'] is not None and network['name'] != 'public':
                cidr = IPNetwork(network['cidr'])
                cidr.prefixlen += 1
                network['cidr'] = str(cidr)
                network['ip_ranges'][0][1] = str(cidr[-2])
        self.update_network_settings(
            networking_parameters=networking_parameters,
            networks=current_networks)
        self.show_step(9)
        self.fuel_web.deploy_cluster_changes_wait(
            self.cluster_id, new_cluster_settings)
        self.show_step(10)
        deployed_settings = self.get_deployed_cluster_attributes()
        deployed_net_conf = self.get_deployed_network_configuration()
        self.show_step(11)
        assert_equal(new_cluster_settings, deployed_settings,
                     message="Cluster settings before deploy"
                             " are not equal with deployed settings")
        assert_true(self.compare_networks(
            current_network_settings, deployed_net_conf),
            message='Network settings comparing failed')
        self.show_step(12)
        default_settings = self.get_default_cluster_settings()
        self.show_step(13)
        assert_true(
            self.compare_settings(default_config, default_settings),
            message='Default settings are not equal')
        self.show_step(14)
        self.fuel_web.redeploy_cluster_changes_wait_progress(
            cluster_id=self.cluster_id, progress=30)
        self.show_step(15)
        self.fuel_web.stop_deployment_wait(self.cluster_id)
        self.show_step(16)
        self.deploy_cluster()
        self.show_step(17)
        self.run_ostf()
        self.env.make_snapshot("unlock_settings_tab_positive")
