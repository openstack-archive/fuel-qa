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

from devops.helpers.helpers import wait
from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["virt_role_baremetal", "reduced_footprint"])
class TestVirtRole(TestBasic):
    """Tests for virt role.

    Part of Reduced footprint feature.
    Creating reduced footprint environments performed by assigning new role
    named "virt" to physical server, after that user should upload VMs
    properties as node attributes. Virtual machines will be treated by Fuel
    as standard bare metal servers.
    """

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["baremetal_deploy_cluster_with_virt_node"])
    @log_snapshot_after_test
    def baremetal_deploy_cluster_with_virt_node(self):
        """Baremetal deployment of cluster with virt node

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to slave node
            3. Upload configuration for one VM
            4. Spawn VM
            5. Wait till VM become available for allocation
            6. Assign controller role to VM
            7. Deploy cluster
            8. Run network check
            9. Run OSTF
            10. Add lots VM (RAM and CPU are exhausted)
            11. Run OSTF smoke tests
            12. Reset the environment
            13. Verify that 'created' flag of the VM is reset to 'false' value
            14. Redeploy cluster
            15. Run network check
            16. Run OSTF

        Duration: 240m
        """

        self.env.revert_snapshot("ready_with_1_slaves")

        self.show_step(1)
        checkers.enable_feature_group(self.env, "advanced")

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE_HA,
            settings={
                'net_provider': 'neutron',
                'net_segment_type': settings.NEUTRON_SEGMENT['tun']
            })

        asserts.assert_true(settings.HARDWARE['slave_node_memory'] >= 1024,
                            "Wrong SLAVE_NODE_MEMORY value: {0}."
                            "Please allocate more than 1024Mb.".
                            format(settings.HARDWARE['slave_node_memory']))

        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['compute', 'virt']
            })

        self.show_step(3)
        node_id = self.fuel_web.get_nailgun_node_by_name("slave-01")['id']
        self.fuel_web.client.create_vm_nodes(
            node_id,
            [{
                "id": 1,
                "mem": 1,
                "cpu": 1
            }])

        self.show_step(4)
        self.fuel_web.spawn_vms_wait(cluster_id)

        self.show_step(5)
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 2,
             timeout=60 * 60,
             timeout_msg=("Timeout waiting 2 available nodes, "
                          "current nodes: \n{0}" + '\n'.join(
                              ['Name: {0}, status: {1}, online: {2}'.
                               format(i['name'], i['status'], i['online'])
                               for i in self.fuel_web.client.list_nodes()])))
        # TODO

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["baremetal_deploy_cluster_with_virt_node_ha"])
    @log_snapshot_after_test
    def baremetal_deploy_cluster_with_virt_node_ha(self):
        """Baremetal deployment of cluster with virt node in HA mode

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to three slave nodes
            3. Upload VM configuration for one VM to each slave node
            4. Spawn VMs
            5. Wait till VMs become available for allocation
            6. Assign controller role to VMs
            7. Deploy cluster
            8. Run network check
            9. Run OSTF
            10. Mark 'mysql' partitions to be preserved on one of controllers
            11. Reinstall the controller
            12. Verify that the reinstalled node joined the Galera cluster
                and synced its state
            13. Run network check
            14. Run OSTF
            15. Reboot one controller via virsh and wait till it come up
            16. Run OSTF
            17. Reboot one controller using "reboot" command
                and wait till it come up
            18. Run OSTF
            19. Reboot one compute using "reboot -f" command
                and wait till compute and controller come up
            20. Run OSTF
            21. Reboot one compute using "reboot" command
                and wait till compute and controller come up
            22. Run OSTF

        Duration: 360m
        """
        # TODO

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["baremetal_deploy_cluster_with_virt_node_mixed"])
    @log_snapshot_after_test
    def baremetal_deploy_cluster_with_virt_node_mixed(self):
        """Baremetal deployment of mixed HW and Virtual cluster with virt node

        Scenario:
            1. Create cluster
            2. Assign compute and virt roles to slave node
            3. Upload configuration for one VM
            4. Spawn VM
            5. Wait till VM become available for allocation
            6. Assign controller role to VM
            7. Assign controller role to 2 HW nodes
            8. Deploy cluster
            9. Run network check
            10. Run OSTF

        Duration: 180m
        """
        # TODO
