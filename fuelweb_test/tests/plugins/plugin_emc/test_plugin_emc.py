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

from proboscis import asserts
from proboscis import test
# pylint: disable=import-error
from six.moves import configparser
# pylint: enable=import-error

from fuelweb_test.helpers import utils
from fuelweb_test.helpers.checkers import check_plugin_path_env
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["plugins"])
class EMCPlugin(TestBasic):
    """EMCPlugin."""  # TODO documentation
    def __init__(self):
        super(EMCPlugin, self).__init__()
        check_plugin_path_env(
            var_name='EMC_PLUGIN_PATH',
            plugin_path=settings.EMC_PLUGIN_PATH
        )

    @classmethod
    def check_emc_cinder_config(cls, ip, path):
        with SSHManager().open_on_remote(
            ip=ip,
            path=path
        ) as f:
            cinder_conf = configparser.ConfigParser()
            cinder_conf.readfp(f)

        asserts.assert_equal(
            cinder_conf.get('DEFAULT', 'volume_driver'),
            'cinder.volume.drivers.emc.emc_cli_iscsi.EMCCLIISCSIDriver')
        asserts.assert_equal(
            cinder_conf.get('DEFAULT', 'storage_vnx_authentication_type'),
            'global')
        asserts.assert_false(
            cinder_conf.getboolean('DEFAULT',
                                   'destroy_empty_storage_group'))
        asserts.assert_true(
            cinder_conf.getboolean('DEFAULT',
                                   'initiator_auto_registration'))
        asserts.assert_equal(
            cinder_conf.getint('DEFAULT', 'attach_detach_batch_interval'), -1)
        asserts.assert_equal(
            cinder_conf.getint('DEFAULT', 'default_timeout'), 10)
        asserts.assert_equal(
            cinder_conf.get('DEFAULT', 'naviseccli_path'),
            '/opt/Navisphere/bin/naviseccli')

        asserts.assert_true(cinder_conf.has_option('DEFAULT', 'san_ip'))
        asserts.assert_true(cinder_conf.has_option('DEFAULT',
                                                   'san_secondary_ip'))
        asserts.assert_true(cinder_conf.has_option('DEFAULT', 'san_login'))
        asserts.assert_true(cinder_conf.has_option('DEFAULT', 'san_password'))

    @classmethod
    def check_service(cls, remote, service):
        ps_output = ''.join(
            remote.execute('ps ax | grep {0} | '
                           'grep -v grep'.format(service))['stdout'])
        return service in ps_output

    @classmethod
    def check_emc_management_package(cls, ip):
        navicli = utils.get_package_versions_from_node(
            ip=ip,
            name='navicli',
            os_type=settings.OPENSTACK_RELEASE)
        naviseccli = utils.get_package_versions_from_node(
            ip=ip,
            name='naviseccli',
            os_type=settings.OPENSTACK_RELEASE)
        return bool(navicli + naviseccli)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["deploy_emc_ha"])
    @log_snapshot_after_test
    def deploy_emc_ha(self):
        """Deploy cluster in ha mode with emc plugin

        Scenario:
            1. Upload plugin to the master node
            2. Install plugin
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 2 nodes with compute role
            6. Deploy the cluster
            7. Run network verification
            8. Check plugin installation
            9. Run OSTF

        Duration 35m
        Snapshot deploy_ha_emc
        """
        self.env.revert_snapshot("ready_with_5_slaves")

        # copy plugin to the master node
        utils.upload_tarball(
            ip=self.ssh_manager.admin_ip,
            tar_path=settings.EMC_PLUGIN_PATH,
            tar_target='/var'
        )

        # install plugin
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.basename(settings.EMC_PLUGIN_PATH))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
        )

        attr = self.fuel_web.client.get_cluster_attributes(cluster_id)

        # check plugin installed and attributes have emc options

        for option in ["emc_sp_a_ip", "emc_sp_b_ip",
                       "emc_username", "emc_password", "emc_pool_name"]:
            asserts.assert_true(option in attr["editable"]["emc_vnx"],
                                "{0} is not in cluster attributes: {1}".
                                format(option,
                                       str(attr["editable"]["storage"])))

        # disable LVM-based volumes

        attr["editable"]["storage"]["volumes_lvm"]["value"] = False

        # enable EMC plugin

        emc_options = attr["editable"]["emc_vnx"]
        emc_options["metadata"]["enabled"] = True
        emc_options["emc_sp_a_ip"]["value"] = settings.EMC_SP_A_IP
        emc_options["emc_sp_b_ip"]["value"] = settings.EMC_SP_B_IP
        emc_options["emc_username"]["value"] = settings.EMC_USERNAME
        emc_options["emc_password"]["value"] = settings.EMC_PASSWORD
        emc_options["emc_pool_name"]["value"] = settings.EMC_POOL_NAME

        self.fuel_web.client.update_cluster_attributes(cluster_id, attr)

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

        # get remotes for all nodes

        controller_nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                            for node in ['slave-01', 'slave-02', 'slave-03']]
        compute_nodes = [self.fuel_web.get_nailgun_node_by_name(node)
                         for node in ['slave-04', 'slave-05']]

        controller_remotes = [self.env.d_env.get_ssh_to_remote(node['ip'])
                              for node in controller_nodes]
        compute_remotes = [self.env.d_env.get_ssh_to_remote(node['ip'])
                           for node in compute_nodes]

        # check cinder-volume settings

        for node in controller_nodes:
            self.check_emc_cinder_config(
                ip=node['ip'], path='/etc/cinder/cinder.conf')
            self.check_emc_management_package(ip=node['ip'])

        # check cinder-volume layout on controllers

        cinder_volume_ctrls = [self.check_service(controller, "cinder-volume")
                               for controller in controller_remotes]
        asserts.assert_equal(sum(cinder_volume_ctrls), 1,
                             "Cluster has more than one "
                             "cinder-volume on controllers")

        # check cinder-volume layout on computes

        cinder_volume_comps = [self.check_service(compute, "cinder-volume")
                               for compute in compute_remotes]
        # closing connections
        for remote in controller_remotes:
            remote.clear()
        for remote in compute_remotes:
            remote.clear()

        asserts.assert_equal(sum(cinder_volume_comps), 0,
                             "Cluster has active cinder-volume on compute")

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.env.make_snapshot("deploy_ha_emc")
