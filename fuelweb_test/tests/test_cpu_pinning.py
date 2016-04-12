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

import random

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import os_actions
from fuelweb_test.helpers import utils
from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["numa_cpu_pinning"])
class NumaCpuPinning(TestBasic):
    """NumaCpuPinning."""

    @staticmethod
    @logwrap
    def assert_entry_in_config(conf, conf_name, section, option, value):
        """Check entry of parameter with a proper value.

        :param conf: a file object
        :param conf_name: a string of full file path
        :param section: a string of section name in configuration file
        :param option: a string of option name in configuration file
        :param value: a string of value that has entry in configuration file
        :return:
        """
        current_value = conf.get(section, option)
        asserts.assert_true(value in current_value,
                            'Expected that the option "{0}" contains value '
                            '"{1}" in config file "{2}", but actually has '
                            'value "{3}": FAIL'.format(option,
                                                       value,
                                                       conf_name,
                                                       current_value))

    @staticmethod
    @logwrap
    def assert_quantity_in_config(conf, conf_name, section, option,
                                  value):
        """Check number of parameters in option section.

        :param conf: a file object
        :param conf_name: a string of full file path
        :param section: a string of section name in configuration file
        :param option: a string of option name in configuration file
        :param value: an int number of values in specific option
        :return:
        """
        current_value = conf.get(section, option)
        asserts.assert_equal(len(current_value.split(',')), value,
                             'Expected that the option "{0}" has "{1}"'
                             'values in config file {2} but actually has '
                             'value "{3}": FAIL'.format(option,
                                                        value,
                                                        conf_name,
                                                        current_value))
    @logwrap
    def create_pinned_instance(self, os_conn, cluster_id,
                               name, vcpus, hostname, meta):
        """Boot VM on specific compute with CPU pinning

        :param os_conn: an object of connection to openstack services
        :param cluster_id: an integer number of cluster id
        :param name: a string name of flavor and VM
        :param vcpus: an integer number of vcpus for flavor
        :param hostname: a string fqdn name of compute
        :param meta: a dict with metadata for aggregate
        :return:
        """
        os_conn.create_aggregate(name, metadata=meta, hosts=[hostname])

        extra_specs = {'aggregate_instance_extra_specs:pinned': 'true',
                       'hw:cpu_policy': 'dedicated'}

        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']
        flavor_id = random.randint(10, 10000)
        os_conn.create_flavor(name=name, ram=64, vcpus=vcpus, disk=1,
                              flavorid=flavor_id, extra_specs=extra_specs)

        server = os_conn.create_server_for_migration(neutron=True,
                                                     label=net_name,
                                                     flavor=flavor_id)
        os_conn.verify_instance_status(server, 'ACTIVE')
        os_conn.delete_instance(server)

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["numa_cpu_pinning",
                  "basic_env_for_numa_cpu_pinning"])
    @log_snapshot_after_test
    def basic_env_for_numa_cpu_pinning(self):
        """Basic environment for NUMA CPU pinning

        Scenario:
            1. Create cluster
            2. Add 2 nodes with compute role
            3. Add 3 nodes with controller role
            4. Verify that quantity of NUMA is equal on node and in Fuel

        Snapshot: basic_env_for_numa_cpu_pinning
        """
        snapshot_name = 'basic_env_for_numa_cpu_pinning'
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        self.show_step(1, initialize=True)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE
            }
        )
        self.show_step(2)
        self.show_step(3)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute'],
                'slave-02': ['compute'],
                'slave-03': ['controller'],
                'slave-04': ['controller'],
                'slave-05': ['controller']
            })

        self.show_step(4)

        for node in ('slave-01', 'slave-02'):
            target_node = self.fuel_web.get_nailgun_node_by_name(node)
            numas_from_fuel = len(
                target_node['meta']['numa_topology']['numa_nodes'])
            numas_on_remote = utils.get_quantity_of_numa(target_node['ip'])
            if not numas_on_remote:
                # Fuel handle topology without NUMA as 1 NUMA node
                asserts.assert_equal(numas_from_fuel, 1,
                                     "No NUMA nodes on {0} "
                                     "while Fuel shows it "
                                     "has {1}".format(
                                         target_node['ip'], numas_from_fuel))
                raise AssertionError("No NUMA nodes on {0}".format(
                                     target_node['ip']))
            else:
                asserts.assert_equal(numas_on_remote, numas_from_fuel,
                                     "{0} NUMA nodes on {1} "
                                     "while Fuel shows it "
                                     "has {2}".format(
                                         numas_on_remote, target_node['ip'],
                                         numas_from_fuel))
                logger.info("There is {0} NUMA nodes on node {1}".format(
                    numas_on_remote, target_node['ip']))
        self.env.make_snapshot(snapshot_name, is_make=True)

    @test(depends_on_groups=['basic_env_for_numa_cpu_pinning'],
          groups=["numa_cpu_pinning",
                  "cpu_pinning_on_two_compute"])
    @log_snapshot_after_test
    def cpu_pinning_on_two_compute(self):
        """Check different amount of pinned CPU

        Scenario:
            1. Revert snapshot "basic_env_for_numa_cpu_pinning"
            2. Pin maximum CPU for the nova on the first compute
            3. Pin minimun CPU for the nova on the second compute
            4. Verify setting was successfully applied
            5. Deploy cluster
            6. Check new filters are enabled in nova.conf at controller
            7. Check nova.conf contains pinned CPU at compute
            8. Run OSTF
            9. Boot VM with pinned CPU on the first compute
            10. Boot VM with pinned CPU on the second compute

        Snapshot: cpu_pinning_on_two_compute
        """
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("basic_env_for_numa_cpu_pinning")

        cluster_id = self.fuel_web.get_last_created_cluster()

        self.show_step(2)
        first_compute = self.fuel_web.get_nailgun_node_by_name('slave-01')
        first_compute_cpu = first_compute['meta']['cpu']['total']
        first_config = self.fuel_web.client.get_node_attributes(
            first_compute['id'])
        first_config['cpu_pinning']['nova']['value'] = first_compute_cpu - 1
        self.fuel_web.client.upload_node_attributes(
            first_config, first_compute['id'])

        self.show_step(3)
        second_compute = self.fuel_web.get_nailgun_node_by_name('slave-02')
        second_config = self.fuel_web.client.get_node_attributes(
            second_compute['id'])
        second_config['cpu_pinning']['nova']['value'] = 1
        self.fuel_web.client.upload_node_attributes(
            second_config, second_compute['id'])

        self.show_step(4)
        first_config = self.fuel_web.client.get_node_attributes(
            first_compute['id'])
        asserts.assert_equal(
            first_config['cpu_pinning']['nova']['value'],
            first_compute_cpu - 1,
            "CPU pinning wasn't applied on '{0}': "
            "Expected value '{1}', actual '{2}'"
            .format(first_compute['ip'], first_compute_cpu - 1,
                    first_config['cpu_pinning']['nova']['value']))

        second_config = self.fuel_web.client.get_node_attributes(
            second_compute['id'])
        asserts.assert_equal(
            second_config['cpu_pinning']['nova']['value'],
            1,
            "CPU pinning wasn't applied on '{0}': "
            "Expected value '{1}', actual '{2}'"
            .format(second_compute['ip'], 1,
                    second_config['cpu_pinning']['nova']['value']))

        self.show_step(5)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(6)
        controllers = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id,
            roles=['controller'])

        nova_conf_path = "/etc/nova/nova.conf"

        for controller in controllers:
            nova_conf = utils.get_ini_config(self.ssh_manager.open_on_remote(
                ip=controller['ip'],
                path=nova_conf_path))

            self.assert_entry_in_config(nova_conf,
                                        nova_conf_path,
                                        "DEFAULT",
                                        "scheduler_default_filters",
                                        "NUMATopologyFilter")

        self.show_step(7)

        nova_conf = utils.get_ini_config(self.ssh_manager.open_on_remote(
            ip=first_compute['ip'],
            path=nova_conf_path))
        self.assert_quantity_in_config(nova_conf,
                                       nova_conf_path,
                                       "DEFAULT",
                                       "vcpu_pin_set",
                                       first_compute_cpu - 1)

        nova_conf = utils.get_ini_config(self.ssh_manager.open_on_remote(
            ip=second_compute['ip'],
            path=nova_conf_path))
        self.assert_quantity_in_config(nova_conf,
                                       nova_conf_path,
                                       "DEFAULT",
                                       "vcpu_pin_set",
                                       1)

        self.show_step(8)
        self.fuel_web.run_ostf(cluster_id=cluster_id)

        self.show_step(9)
        os_conn = os_actions.OpenStackActions(
            self.fuel_web.get_public_vip(cluster_id))

        meta = {'pinned': 'true'}

        self.create_pinned_instance(os_conn=os_conn,
                                    cluster_id=cluster_id,
                                    name='cpu_3',
                                    vcpus=3,
                                    hostname=first_compute['fqdn'],
                                    meta=meta)
        self.show_step(10)
        self.create_pinned_instance(os_conn=os_conn,
                                    cluster_id=cluster_id,
                                    name='cpu_1',
                                    vcpus=1,
                                    hostname=second_compute['fqdn'],
                                    meta=meta)

        self.env.make_snapshot("cpu_pinning_on_two_compute")
