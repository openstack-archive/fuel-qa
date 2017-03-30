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

from devops.settings import DRIVER_PARAMETERS
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.helpers import utils
from fuelweb_test.helpers import os_actions
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from gates_tests.helpers import exceptions


@test(groups=["support_hugepages"])
class SupportHugepages(TestBasic):
    """SupportHugepages.

    Required environment variables:
        * KVM_USE=true
        * DRIVER_ENABLE_ACPI=true
        * NUMA_NODES=2
        * SLAVE_NODE_CPU=4
        * SLAVE_NODE_MEMORY=5120
    """
    def __init__(self):
        self.os_conn = None
        super(SupportHugepages, self).__init__()

    def boot_instance_with_hugepage(self, target_compute_name,
                                    flavor_name, flavor_ram, page_size):

        cluster_id = self.fuel_web.get_last_created_cluster()

        logger.info("Creating flavor {}, RAM: {}, PageSize: {}"
                    .format(flavor_name, flavor_ram, page_size))
        flavor = self.os_conn.nova.flavors.create(
            name=flavor_name,
            ram=flavor_ram,
            vcpus=1,
            disk=1
        )
        flavor.set_keys(metadata={"hw:mem_page_size": page_size})

        target_compute = \
            self.fuel_web.get_nailgun_node_by_name(target_compute_name)
        net_name = self.fuel_web.get_cluster_predefined_networks_name(
            cluster_id)['private_net']

        logger.info("Booting instance on compute {}"
                    .format(target_compute["fqdn"]))
        server = self.os_conn.create_server_for_migration(
            neutron=True,
            label=net_name,
            availability_zone="nova:{0}".format(target_compute['fqdn']),
            flavor_id=flavor.id)

        server = server.to_dict()
        asserts.assert_equal(
            server['OS-EXT-SRV-ATTR:host'], target_compute['fqdn'],
            "Server scheduled on a wrong host, server data: {}".format(server))

        instance_name = server['OS-EXT-SRV-ATTR:instance_name']
        cmd = "virsh dumpxml {}".format(instance_name)
        result = "".join(
            self.ssh_manager.execute(target_compute['ip'], cmd)["stdout"])
        asserts.assert_true(
            "page size='{}'".format(page_size) in result,
            "Virsh xml contain different page size: {}".format(result))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["basic_env_for_hugepages"])
    @log_snapshot_after_test
    def basic_env_for_hugepages(self):
        """Basic environment for hugepages

        Scenario:
            1. Create cluster
            2. Add 3 compute nodes and 1 controller node
            3. Check what type of HugePages do support 2M and 1GB
            4. Verify the same HP size is present in CLI
            5. Download attributes for computes and check HP size

        Snapshot: basic_env_for_hugepages

        """
        snapshot_name = 'basic_env_for_hugepages'
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready_with_5_slaves")

        if not settings.KVM_USE:
            raise exceptions.FuelQAVariableNotSet(
                'KVM_USE', 'true')

        if not DRIVER_PARAMETERS['enable_acpi']:
            raise exceptions.FuelQAVariableNotSet(
                'DRIVER_ENABLE_ACPI', 'true')

        if settings.HARDWARE['numa_nodes'] != 2:
            raise exceptions.FuelQAVariableNotSet(
                'NUMA_NODES', 2)

        if settings.HARDWARE['slave_node_cpu'] != 4:
            raise exceptions.FuelQAVariableNotSet(
                'SLAVE_NODE_CPU', 4)

        if settings.HARDWARE['slave_node_memory'] != 5120:
            raise exceptions.FuelQAVariableNotSet(
                'SLAVE_NODE_MEMORY', 5120)

        if not settings.INTERFACES_DICT['eth0'] == 'ens3':
            raise exceptions.FuelQAVariableNotSet(
                'IFACE_0', 'ens3')

        if not settings.INTERFACES_DICT['eth1'] == 'ens4':
            raise exceptions.FuelQAVariableNotSet(
                'IFACE_1', 'ens4')

        if not settings.INTERFACES_DICT['eth2'] == 'ens5':
            raise exceptions.FuelQAVariableNotSet(
                'IFACE_2', 'ens5')

        if not settings.INTERFACES_DICT['eth3'] == 'ens6':
            raise exceptions.FuelQAVariableNotSet(
                'IFACE_3', 'ens6')

        if not settings.INTERFACES_DICT['eth4'] == 'ens7':
            raise exceptions.FuelQAVariableNotSet(
                'IFACE_4', 'ens7')

        if not settings.INTERFACES_DICT['eth5'] == 'ens8':
            raise exceptions.FuelQAVariableNotSet(
                'IFACE_5', 'ens8')

        self.show_step(1)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE
            }
        )

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute'],
                'slave-02': ['compute'],
                'slave-03': ['compute'],
                'slave-04': ['compute', 'cinder'],
                'slave-05': ['controller']
            })

        self.show_step(3)
        computes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['compute'], role_status="pending_roles")
        for compute in computes:
            self.ssh_manager.execute_on_remote(
                ip=compute['ip'],
                cmd="grep \"pse\" /proc/cpuinfo",
                err_msg="{} compute doesn't support 2Mb HugePages"
                    .format(compute['fqdn']))

            self.ssh_manager.execute_on_remote(
                ip=compute['ip'],
                cmd="grep \"pdpe1gb\" /proc/cpuinfo",
                err_msg="{} compute doesn't support 1GB HugePages"
                    .format(compute['fqdn']))

        self.show_step(4)
        for compute in computes:
            self.ssh_manager.execute_on_remote(
                ip=self.ssh_manager.admin_ip,
                cmd="fuel2 node show {0} | grep hugepages | "
                    "grep 2048".format(compute['id']),
                err_msg="2Mb HugePages doesn't present in CLI for node "
                        "{0}".format(compute['fqdn']))
            self.ssh_manager.execute_on_remote(
                ip=self.ssh_manager.admin_ip,
                cmd="fuel2 node show {0} | grep hugepages | "
                    "grep 1048576".format(compute['id']),
                err_msg="1Gb HugePages doesn't present in CLI for node "
                        "{0}".format(compute['fqdn']))

        self.show_step(5)
        for compute in computes:
            config = self.fuel_web.client.get_node_attributes(compute['id'])
            asserts.assert_true(
                config['hugepages']['nova']['value']['2048'] == 0,
                "Number of 2Mb HugePages for node {} is not "
                "0".format(compute['fqdn']))
            asserts.assert_true(
                config['hugepages']['nova']['value']['1048576'] == 0,
                "Number of 1Gb HugePages for node {} is not "
                "0".format(compute['fqdn']))

        self.env.make_snapshot(snapshot_name, is_make=True)

    @test(depends_on=[basic_env_for_hugepages],
          groups=["check_hugepages_distribution_per_numa"])
    @log_snapshot_after_test
    def check_hugepages_distribution_per_numa(self):
        """Deploy environment with different HugePages allocation

        Scenario:
            1. Revert basic_env_for_hugepages snapshot
            2. Configure hugepages for three computes
            3. Deploy cluster
            4. Validate available huge pages on computes

        Snapshot: check_hugepages_distribution_per_numa
        """
        snapshot_name = "check_hugepages_distribution_per_numa"
        self.check_run(snapshot_name)

        self.show_step(1)
        self.env.revert_snapshot("basic_env_for_hugepages")

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        mixed_host = "slave-01"
        one_gb_host = "slave-02"
        two_mb_host = "slave-03"
        mixed_role_host = "slave-04"

        configs = {
            mixed_host: {"cpu_pinning": {"nova": {"value": 2}},
                         "hugepages": {"nova": {"value": {"2048": 258,
                                                          "1048576": 1}}
                                       }
                         },
            one_gb_host: {"cpu_pinning": {"nova": {"value": 2}},
                          "hugepages": {"nova": {"value": {"2048": 0,
                                                           "1048576": 2}}
                                        }
                          },
            two_mb_host: {"cpu_pinning": {"nova": {"value": 2}},
                          "hugepages": {"nova": {"value": {"2048": 540,
                                                           "1048576": 0}}
                                        }
                          },
            mixed_role_host: {"cpu_pinning": {"nova": {"value": 2}},
                              "hugepages": {"nova": {"value": {"2048": 258,
                                                               "1048576": 1}}
                                            }
                              },
        }

        for compute_name, config in configs.items():
            compute_id = \
                self.fuel_web.get_nailgun_node_by_name(compute_name)['id']
            original_config = \
                self.fuel_web.client.get_node_attributes(compute_id)
            self.fuel_web.client.upload_node_attributes(
                utils.dict_merge(original_config, config), compute_id)

        self.show_step(3)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(4)
        for compute_name, config in configs.items():
            two_mb_count = config["hugepages"]["nova"]["value"]["2048"]
            one_gb_count = config["hugepages"]["nova"]["value"]["1048576"]

            compute = self.fuel_web.get_nailgun_node_by_name(compute_name)
            cmd = ("cat /sys/devices/system/node/node{}/hugepages/"
                   "hugepages-{}kB/nr_hugepages")

            actual_two_mb_count = 0
            actual_one_gb_count = 0

            for numa_node in [0, 1]:
                actual_two_mb_count += int("".join(self.ssh_manager.execute(
                    compute['ip'], cmd.format(numa_node, "2048"))["stdout"]))

                result = "".join(self.ssh_manager.execute(
                    compute['ip'], cmd.format(numa_node, "1048576"))["stdout"])

                result = "0" if not result else result
                actual_one_gb_count += int(result)

            asserts.assert_equal(
                two_mb_count, actual_two_mb_count,
                "Actual number of allocated 2Mb pages is {}, expected {}"
                .format(actual_two_mb_count, two_mb_count))
            asserts.assert_equal(
                one_gb_count, actual_one_gb_count,
                "Actual number of allocated 1Gb pages is {}, expected {}"
                .format(actual_one_gb_count, one_gb_count))

        self.env.make_snapshot(snapshot_name, is_make=True)

    @test(depends_on=[check_hugepages_distribution_per_numa],
          groups=["check_instance_one_gb_page_size_one_gb_host"])
    @log_snapshot_after_test
    def check_instance_one_gb_page_size_one_gb_host(self):
        """Boot instance with 1 Gb page size on host with only 1 Gb HugePages

        Scenario:
            1. Revert snapshot "check_hugepages_distribution_per_numa"
            2. Boot and validate instance on compute with only 1 Gb pages
        """
        self.env.revert_snapshot("check_hugepages_distribution_per_numa")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        self.os_conn = os_actions.OpenStackActions(controller_ip)
        one_gb_host = "slave-02"

        self.boot_instance_with_hugepage(
            target_compute_name=one_gb_host,
            flavor_name="h1.huge.hpgs",
            flavor_ram=1024,
            page_size=1048576)

    @test(depends_on=[check_hugepages_distribution_per_numa],
          groups=["check_instance_two_mb_page_size_two_mb_host"])
    @log_snapshot_after_test
    def check_instance_two_mb_page_size_two_mb_host(self):
        """Boot instance with 2 Mb page size on host with only 2 Mb HugePages

        Scenario:
            1. Revert snapshot "check_hugepages_distribution_per_numa"
            2. Boot and validate instance on compute with only 2 Mb pages
        """
        self.env.revert_snapshot("check_hugepages_distribution_per_numa")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        self.os_conn = os_actions.OpenStackActions(controller_ip)
        two_mb_host = "slave-03"

        self.boot_instance_with_hugepage(
            target_compute_name=two_mb_host,
            flavor_name="h1.small.hpgs",
            flavor_ram=512,
            page_size=2048)

    @test(depends_on=[check_hugepages_distribution_per_numa],
          groups=["check_instance_one_gb_page_size_mixed_size_host"])
    @log_snapshot_after_test
    def check_instance_one_gb_page_size_mixed_size_host(self):
        """Boot instance with 1 Gb page size on host with both HugePages types

        Scenario:
            1. Revert snapshot "check_hugepages_distribution_per_numa"
            2. Boot and validate instance on compute with both pages types
        """
        self.env.revert_snapshot("check_hugepages_distribution_per_numa")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        self.os_conn = os_actions.OpenStackActions(controller_ip)
        mixed_host = "slave-01"

        self.boot_instance_with_hugepage(
            target_compute_name=mixed_host,
            flavor_name="h1.huge_mixed.hpgs",
            flavor_ram=1024,
            page_size=1048576)

    @test(depends_on=[check_hugepages_distribution_per_numa],
          groups=["check_instance_two_mb_page_size_mixed_size_host"])
    @log_snapshot_after_test
    def check_instance_two_mb_page_size_mixed_size_host(self):
        """Boot instance with 2 Mb page size on host with both HugePages types

        Scenario:
            1. Revert snapshot "check_hugepages_distribution_per_numa"
            2. Boot and validate instance on compute with both pages types
        """
        self.env.revert_snapshot("check_hugepages_distribution_per_numa")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        self.os_conn = os_actions.OpenStackActions(controller_ip)
        mixed_host = "slave-01"

        self.boot_instance_with_hugepage(
            target_compute_name=mixed_host,
            flavor_name="h1.small_mixed.hpgs",
            flavor_ram=128,
            page_size=2048)

    @test(depends_on=[check_hugepages_distribution_per_numa],
          groups=["check_hugepages_nova_scheduler"])
    @log_snapshot_after_test
    def check_instance_two_mb_page_size_mixed_role_host(self):
        """Boot instance with both HP sizes on host with Cinder+Compute role

        Scenario:
            1. Revert snapshot "check_hugepages_distribution_per_numa"
            2. Boot and validate instance on compute+mongo node with 2Mb
            3. Boot and validate instance on compute+mongo node with 1Gb
        """
        self.env.revert_snapshot("check_hugepages_distribution_per_numa")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        self.os_conn = os_actions.OpenStackActions(controller_ip)
        mixed_role_host = "slave-04"

        self.boot_instance_with_hugepage(
            target_compute_name=mixed_role_host,
            flavor_name="h1.small_mixed_roles.hpgs",
            flavor_ram=128,
            page_size=2048)

        self.boot_instance_with_hugepage(
            target_compute_name=mixed_role_host,
            flavor_name="h1.huge_mixed_roles.hpgs",
            flavor_ram=1024,
            page_size=1048576)

    @test(depends_on=[check_hugepages_distribution_per_numa],
          groups=["check_hugepages_after_reboot"])
    @log_snapshot_after_test
    def check_hugepages_after_reboot(self):
        """Boot instances with both HP sizes on compute after reboot

        Scenario:
            1. Revert snapshot "check_hugepages_distribution_per_numa"
            2. Reboot node with mixed reserved HugePages
            3. Boot and validate instance with 2Mb page size
            4. Boot and validate instance with 1Gb page size
        """
        self.env.revert_snapshot("check_hugepages_distribution_per_numa")

        cluster_id = self.fuel_web.get_last_created_cluster()
        controller_ip = self.fuel_web.get_public_vip(cluster_id)
        self.os_conn = os_actions.OpenStackActions(controller_ip)
        mixed_host = "slave-01"

        target_compute = self.fuel_web.get_devops_node_by_nailgun_node(
            self.fuel_web.get_nailgun_node_by_name(mixed_host))
        self.fuel_web.cold_restart_nodes([target_compute])

        self.fuel_web.assert_ha_services_ready(cluster_id)

        self.boot_instance_with_hugepage(
            target_compute_name=mixed_host,
            flavor_name="h1.small_mixed.hpgs",
            flavor_ram=128,
            page_size=2048)

        self.boot_instance_with_hugepage(
            target_compute_name=mixed_host,
            flavor_name="h1.huge_mixed.hpgs",
            flavor_ram=1024,
            page_size=1048576)
