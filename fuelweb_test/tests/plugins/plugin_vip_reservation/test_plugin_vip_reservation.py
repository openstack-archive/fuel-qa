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

from fuelweb_test.helpers import checkers
from fuelweb_test import logger
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.fuel_actions import FuelPluginBuilder
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from proboscis.asserts import assert_equal


@test(groups=["fuel_plugins"])
class VipReservation(TestBasic):
    """Test class for testing allocation of vip for plugin."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vip_reservation_for_plugin",
                  "vip_reservation_for_plugin_vlan",
                  "vip_reservation_for_plugin_vxlan"])
    @log_snapshot_after_test
    def vip_reservation_for_plugin(self):
        """Check vip reservation for fuel plugin.

        Scenario:
        1. Revert snapshot with 3 nodes
        2. Download and install fuel-plugin-builder
        3. Create plugin with predefined network_roles.yaml
        4. Build and copy plugin from container nailgun
        5. Install plugin to fuel
        6. Create cluster and enable plugin
        7. Deploy cluster
        8. Check vip reservation

        Duration 40m
        """
        plugin_name = 'vip_reservation_plugin'
        plugin_path = '/var'
        dir_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'tasks.yaml'
        net_role_file = 'network_roles.yaml'
        metadata_file = 'metadata.yaml'

        self.env.revert_snapshot("ready_with_3_slaves")

        with self.env.d_env.get_admin_remote() as admin_remote:
            # initiate fuel plugin builder instance
            fpb = FuelPluginBuilder(admin_remote)
            # install fuel_plugin_builder on master node
            fpb.fpb_install()
            # create plugin template on the master node
            fpb.fpb_create_plugin(plugin_name)
            # replace plugin tasks, metadata, network_roles
            fpb.fpb_replace_plugin_content(
                os.path.join(dir_path, net_role_file),
                os.path.join('/root/', plugin_name, net_role_file))
            fpb.fpb_replace_plugin_content(
                os.path.join(dir_path, tasks_file),
                os.path.join('/root/', plugin_name, tasks_file))
            fpb.fpb_replace_plugin_content(
                os.path.join(dir_path, metadata_file),
                os.path.join('/root/', plugin_name, metadata_file))
            # build plugin
            fpb.fpb_build_plugin(os.path.join('/root/', plugin_name))
            # copy plugin archive file from nailgun container
            # to the /var directory on the master node
            fpb.fpb_copy_plugin_from_container(plugin_name, plugin_path)
            # let's install plugin
            checkers.install_plugin_check_code(
                admin_remote,
                plugin=os.path.join(plugin_path, '{}.rpm'.format(plugin_name)))

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": NEUTRON_SEGMENT_TYPE
            }
        )
        # get plugins from fuel and enable our one
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('cluster is %s' % str(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']}
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            #get vips from hiera
            reserved_vip_pub = remote.execute(
                'hiera reserved_vip_pub')['stdout'][1].split('"')[3]
            reserved_vip_mng = remote.execute(
                'hiera reserved_vip_mng')['stdout'][1].split('"')[3]
        #get vips from database
        reserved_vip_pub_db = self.env.postgres_actions.run_query(
            db='nailgun', query="select ip_addr from ip_addrs where "
                                "vip_type = '\"'\"'reserved_vip_pub'\"'\"';")
        reserved_vip_mng_db = self.env.postgres_actions.run_query(
            db='nailgun', query="select ip_addr from ip_addrs where "
                                "vip_type = '\"'\"'reserved_vip_mng'\"'\"';")

        assert_equal(reserved_vip_pub, reserved_vip_pub_db,
                     "Vip public from hiera output {0} does not equal to "
                     "vip public from database {1}".format(
                         reserved_vip_pub, reserved_vip_pub_db))
        assert_equal(reserved_vip_mng, reserved_vip_mng_db,
                     "Vip management from hiera output {0} does not equal to "
                     "vip management from database {1}".format(
                         reserved_vip_mng, reserved_vip_mng_db))
