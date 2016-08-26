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

import json
import os

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test.helpers.utils import YamlEditor
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.helpers.fuel_actions import FuelPluginBuilder
from fuelweb_test.helpers.decorators import log_snapshot_after_test


@test(groups=["fuel_plugins", "fuel_plugin_vip_reservation"])
class VipReservation(TestBasic):
    """Test class for testing allocation of vip for plugin."""

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vip_reservation_for_plugin",
                  "vip_reservation_for_plugin_vlan",
                  "vip_reservation_for_plugin_vxlan"])
    @log_snapshot_after_test
    def vip_reservation_for_plugin(self):
        """Check vip reservation for fuel plugin

        Scenario:
        1. Revert snapshot with 3 nodes
        2. Download and install fuel-plugin-builder
        3. Create plugin with predefined network_roles.yaml
        4. Build and copy plugin to /var directory
        5. Install plugin to fuel
        6. Create cluster and enable plugin
        7. Deploy cluster
        8. Check vip reservation

        Duration 40m
        """
        plugin_name = 'vip_reservation_plugin'
        source_plugin_path = os.path.join('/root/', plugin_name)
        plugin_path = '/var'
        dir_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'tasks.yaml'
        net_role_file = 'network_roles.yaml'
        metadata_file = 'metadata.yaml'
        namespace = 'haproxy'

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")
        # initiate fuel plugin builder instance
        fpb = FuelPluginBuilder()
        # install fuel_plugin_builder on master node
        self.show_step(2)
        fpb.fpb_install()
        # create plugin template on the master node
        self.show_step(3)
        fpb.fpb_create_plugin(source_plugin_path)
        # replace plugin tasks, metadata, network_roles
        fpb.fpb_replace_plugin_content(
            os.path.join(dir_path, net_role_file),
            os.path.join(source_plugin_path, net_role_file))
        fpb.fpb_replace_plugin_content(
            os.path.join(dir_path, tasks_file),
            os.path.join(source_plugin_path, tasks_file))
        fpb.fpb_replace_plugin_content(
            os.path.join(dir_path, metadata_file),
            os.path.join(source_plugin_path, metadata_file))
        # build plugin
        self.show_step(4)
        packet_name = fpb.fpb_build_plugin(source_plugin_path)
        # copy plugin archive file from nailgun container
        # to the /var directory on the master node
        fpb.fpb_copy_plugin(os.path.join(source_plugin_path, packet_name),
                            plugin_path)
        # let's install plugin
        self.show_step(5)
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.join(plugin_path, packet_name))
        self.show_step(6)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        # get plugins from fuel and enable our one
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('Cluster is {!s}'.format(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']}
        )
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            hiera_json_out = "ruby -rhiera -rjson -e \"h = Hiera.new(); " \
                             "Hiera.logger = 'noop'; puts JSON.dump " \
                             "(h.lookup('network_metadata', " \
                             "[], {}, nil, nil))\""
            for vip in ('reserved_pub', 'reserved_mng'):
                # get vips from hiera
                vip_hiera = json.loads(
                    remote.execute(
                        hiera_json_out)['stdout'][0])["vips"][vip]["ipaddr"]
                # get vips from database
                vip_db = self.env.postgres_actions.run_query(
                    db='nailgun',
                    query="select ip_addr from ip_addrs where "
                          "vip_name = '\"'\"'{0}'\"'\"';".format(vip))
                vip_array = [vip_hiera, vip_db]
                for ip in vip_array[1:]:
                    asserts.assert_equal(
                        vip_array[0], ip,
                        "Vip from hiera output {0} does not equal "
                        "to {1}".format(vip_array[0], ip))
                vip_pcs = remote.execute(
                    'pcs resource show {0}{1}'.format(
                        'vip__', vip))['exit_code']
                asserts.assert_not_equal(0, vip_pcs,
                                         'The vip__{0} was found in '
                                         'pacemaker'.format(vip))
                vip_ns = remote.execute(
                    'ip netns exec {0} ip a | grep {1}{2}'.format(
                        namespace, 'b_', vip))['exit_code']
                asserts.assert_not_equal(0, vip_ns,
                                         'The {0} was found in {1} '
                                         'namespace'.format(vip, namespace))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vip_reservation_for_plugin_haproxy_ns",
                  "vip_reservation_for_plugin_haproxy_ns_vlan",
                  "vip_reservation_for_plugin_haproxy_ns_vxlan"])
    @log_snapshot_after_test
    def vip_reservation_for_plugin_haproxy_ns(self):
        """Check vip reservation for haproxy ns plugin

        Scenario:
        1. Revert snapshot with 3 nodes
        2. Download and install fuel-plugin-builder
        3. Create plugin with predefined network_roles.yaml
        4. Build and copy plugin to /var directory
        5. Install plugin to fuel
        6. Create cluster and enable plugin
        7. Deploy cluster
        8. Check vip reservation

        Duration 40m
        """
        plugin_name = 'vip_reservation_plugin'
        source_plugin_path = os.path.join('/root/', plugin_name)
        plugin_path = '/var'
        task_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'tasks.yaml'
        net_role_file = 'network_roles.yaml'
        metadata_file = 'metadata.yaml'
        namespace = 'haproxy'
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")

        # initiate fuel plugin builder instance
        self.show_step(2)
        fpb = FuelPluginBuilder()
        # install fuel_plugin_builder on master node
        fpb.fpb_install()
        # create plugin template on the master node
        self.show_step(3)
        fpb.fpb_create_plugin(source_plugin_path)
        # replace plugin tasks, metadata, network_roles
        fpb.fpb_replace_plugin_content(
            os.path.join(task_path, net_role_file),
            os.path.join(source_plugin_path, net_role_file))
        fpb.fpb_replace_plugin_content(
            os.path.join(task_path, tasks_file),
            os.path.join(source_plugin_path, tasks_file))
        fpb.fpb_replace_plugin_content(
            os.path.join(task_path, metadata_file),
            os.path.join(source_plugin_path, metadata_file))

        with YamlEditor(os.path.join(source_plugin_path, net_role_file),
                        ip=fpb.admin_ip) as editor:
            editor.content[0]['properties']['vip'][0]['namespace'] = namespace
            editor.content[1]['properties']['vip'][0]['namespace'] = namespace
        # build plugin
        self.show_step(4)
        packet_name = fpb.fpb_build_plugin(source_plugin_path)
        # copy plugin archive file
        # to the /var directory on the master node
        fpb.fpb_copy_plugin(os.path.join(source_plugin_path, packet_name),
                            plugin_path)
        # let's install plugin
        self.show_step(5)
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.join(plugin_path, packet_name))
        self.show_step(6)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        # get plugins from fuel and enable our one
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('Cluster is {!s}'.format(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']}
        )
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(8)
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            hiera_json_out = "ruby -rhiera -rjson -e \"h = Hiera.new(); " \
                             "Hiera.logger = 'noop'; " \
                             "puts JSON.dump(h.lookup('network_metadata', " \
                             "[], {}, nil, nil))\""
            for vip in ('reserved_pub', 'reserved_mng'):
                # get vips from hiera
                vip_hiera = json.loads(
                    remote.execute(
                        hiera_json_out)['stdout'][0])["vips"][vip]["ipaddr"]
                # get vips from database
                vip_db = self.env.postgres_actions.run_query(
                    db='nailgun',
                    query="select ip_addr from ip_addrs where "
                          "vip_name = '\"'\"'{0}'\"'\"';".format(vip))
                # get vips from corosync
                vip_crm = remote.execute(
                    'crm_resource --resource {0}{1} --get-parameter=ip'.format(
                        'vip__', vip))['stdout'][0].rstrip()
                # fet vips from namespace
                vip_ns = remote.execute(
                    'ip netns exec {0} ip -4 a show {1}{2}'.format(
                        namespace, 'b_',
                        vip))['stdout'][1].split(' ')[5].split('/')[0]
                vip_array = [vip_hiera, vip_db, vip_crm, vip_ns]
                for ip in vip_array[1:]:
                    asserts.assert_equal(
                        vip_array[0], ip,
                        "Vip from hiera output {0} does not equal "
                        "to {1}".format(vip_array[0], ip))

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["vip_reservation_for_plugin_custom_ns",
                  "vip_reservation_for_plugin_custom_ns_vlan",
                  "vip_reservation_for_plugin_custom_ns_vxlan"])
    @log_snapshot_after_test
    def vip_reservation_for_plugin_custom_ns(self):
        """Check vip reservation for custom ns plugin

        Scenario:
        1. Revert snapshot with 3 nodes
        2. Download and install fuel-plugin-builder
        3. Create plugin with predefined network_roles.yaml
        4. Build and copy plugin to /var
        5. Install plugin to fuel
        6. Create cluster and enable plugin
        7. Deploy cluster
        8. Check vip reservation

        Duration 40m
        """
        plugin_name = 'vip_reservation_plugin'
        source_plugin_path = os.path.join('/root/', plugin_name)
        plugin_path = '/var'
        task_path = os.path.dirname(os.path.abspath(__file__))
        tasks_file = 'tasks.yaml'
        net_role_file = 'network_roles.yaml'
        metadata_file = 'metadata.yaml'
        namespace = 'custom_ns'
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)
        # initiate fuel plugin builder instance
        fpb = FuelPluginBuilder()
        # install fuel_plugin_builder on master node
        fpb.fpb_install()
        # create plugin template on the master node
        self.show_step(3)
        fpb.fpb_create_plugin(source_plugin_path)
        # replace plugin tasks, metadata, network_roles
        fpb.fpb_replace_plugin_content(
            os.path.join(task_path, net_role_file),
            os.path.join(source_plugin_path, net_role_file))
        fpb.fpb_replace_plugin_content(
            os.path.join(task_path, tasks_file),
            os.path.join(source_plugin_path, tasks_file))
        fpb.fpb_replace_plugin_content(
            os.path.join(task_path, metadata_file),
            os.path.join(source_plugin_path, metadata_file))

        with YamlEditor(os.path.join(source_plugin_path, net_role_file),
                        ip=fpb.admin_ip) as editor:
            editor.content[0]['properties']['vip'][0]['namespace'] = namespace
            editor.content[1]['properties']['vip'][0]['namespace'] = namespace
        # build plugin
        self.show_step(4)
        packet_name = fpb.fpb_build_plugin(source_plugin_path)
        # copy plugin archive file
        # to the /var directory on the master node
        fpb.fpb_copy_plugin(os.path.join(source_plugin_path, packet_name),
                            plugin_path)
        self.show_step(5)
        # let's install plugin
        utils.install_plugin_check_code(
            ip=self.ssh_manager.admin_ip,
            plugin=os.path.join(plugin_path, packet_name))
        self.show_step(6)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE,
        )
        # get plugins from fuel and enable our one
        msg = "Plugin couldn't be enabled. Check plugin version. Test aborted"
        asserts.assert_true(
            self.fuel_web.check_plugin_exists(cluster_id, plugin_name),
            msg)
        options = {'metadata/enabled': True}
        self.fuel_web.update_plugin_data(cluster_id, plugin_name, options)

        logger.info('Cluster is {!s}'.format(cluster_id))

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute']}
        )
        self.show_step(7)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(8)
        with self.fuel_web.get_ssh_for_node('slave-01') as remote:
            hiera_json_out = "ruby -rhiera -rjson -e \"h = Hiera.new(); " \
                             "Hiera.logger = 'noop'; " \
                             "puts JSON.dump(h.lookup('network_metadata', " \
                             "[], {}, nil, nil))\""
            for vip in ('reserved_pub', 'reserved_mng'):
                # get vips from hiera
                vip_hiera = json.loads(
                    remote.execute(
                        hiera_json_out)['stdout'][0])["vips"][vip]["ipaddr"]
                # get vips from database
                vip_db = self.env.postgres_actions.run_query(
                    db='nailgun',
                    query="select ip_addr from ip_addrs where "
                          "vip_name = '\"'\"'{0}'\"'\"';".format(vip))
                # get vips from corosync
                vip_crm = remote.execute(
                    'crm_resource --resource {0}{1} --get-parameter=ip'.format(
                        'vip__', vip))['stdout'][0].rstrip()
                # get vips from namespace
                vip_ns = remote.execute(
                    'ip netns exec {0} ip -4 a show {1}{2}'.format(
                        namespace, 'b_',
                        vip))['stdout'][1].split(' ')[5].split('/')[0]
                vip_array = [vip_hiera, vip_db, vip_crm, vip_ns]
                for ip in vip_array[1:]:
                    asserts.assert_equal(
                        vip_array[0], ip,
                        "Vip from hiera output {0} does not equal "
                        "to {1}".format(vip_array[0], ip))
