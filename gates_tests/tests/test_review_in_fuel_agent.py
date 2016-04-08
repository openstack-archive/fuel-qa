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

from proboscis import test

from fuelweb_test import settings
from fuelweb_test.helpers.fuel_actions import BaseActions
from fuelweb_test.helpers import ironic_actions
from fuelweb_test.helpers.checkers import verify_bootstrap_on_node
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.test_ironic_base import TestIronicDeploy

from gates_tests.helpers import exceptions
from gates_tests.helpers.utils import replace_rpm_package
from gates_tests.helpers.utils import \
    check_package_version_injected_in_bootstraps


@test(groups=["review_fuel_agent"])
class Gate(TestIronicDeploy):
    """Using in fuel-agent CI-gates
    Update fuel-agent on master node, bootstrap from review,
    build environment images and provision one node"""

    def update_bootstrap_cli_yaml(self):
        path = "/etc/fuel-bootstrap-cli/fuel_bootstrap_cli.yaml"
        element = ['repos']
        new_repo = {'name': 'auxiliary', 'priority': 1200,
                    'section': 'main restricted',
                    'suite': 'auxiliary', 'type': 'deb',
                    'uri': 'http://127.0.0.1:8080/ubuntu/auxiliary/'}
        repos = BaseActions.get_value_from_remote_yaml(self, path, element)
        repos.append(new_repo)

        BaseActions.change_remote_yaml(self, path, element, repos)

    @test(depends_on_groups=['prepare_release'],
          groups=["review_fuel_agent_ironic_deploy"])
    @log_snapshot_after_test
    def gate_patch_fuel_agent(self):
        """ Revert snapshot, update fuel-agent, bootstrap from review
        and provision one node

    Scenario:
        1. Revert snapshot "ready"
        2. Update fuel-agent, fuel-bootstrap-cli on master node
        3. Update fuel_bootstrap_cli.yaml
        4. Rebuild bootstrap
        5. Bootstrap 5 slaves
        6. Verify Ubuntu bootstrap on slaves
        7. Add 1 node with controller and ceph roles
        8. Add 1 node with controller, ironic, ceph roles
        9. Add 1 node with controller, ironic, ceph roles
        10. Add 1 node with ironic role
        11. Add 1 node with compute
        12. Deploy the cluster
        13. Verify fuel-agent version in ubuntu and ironic-bootstrap
        14. Upload image to glance
        15. Enroll Ironic nodes
        16. Boot nova instance
        17. Check Nova instance status

        Snapshot review_fuel_agent_ironic_deploy
        """
        if not settings.UPDATE_FUEL:
            raise exceptions.FuelQAVariableNotSet(settings.UPDATE_FUEL, 'true')

        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        replace_rpm_package('fuel-agent')
        replace_rpm_package('fuel-bootstrap-cli')

        self.show_step(3)
        self.update_bootstrap_cli_yaml(self)

        self.show_step(4)
        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image()
        self.env.fuel_bootstrap_actions. \
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions. \
            activate_bootstrap_image(uuid)

        self.show_step(5)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:5])

        self.show_step(6)
        for node in self.env.d_env.nodes().slaves[:5]:
            _ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            verify_bootstrap_on_node(_ip, os_type="ubuntu", uuid=uuid)

        data = {
            'volumes_ceph': True,
            'images_ceph': True,
            'objects_ceph': True,
            'volumes_lvm': False,
            'tenant': 'ceph1',
            'user': 'ceph1',
            'password': 'ceph1',
            'net_provider': settings.NEUTRON,
            'net_segment_type': settings.NEUTRON_SEGMENT['vlan'],
            'ironic': True}
        nodes = {
            'slave-01': ['controller', 'ceph-osd'],
            'slave-02': ['controller', 'ironic', 'ceph-osd'],
            'slave-03': ['controller', 'ironic', 'ceph-osd'],
            'slave-04': ['ironic'],
            'slave-05': ['compute']}

        self.show_step(7)
        self.show_step(8)
        self.show_step(9)
        self.show_step(10)
        self.show_step(11)
        self.show_step(12)

        cluster_id = self._deploy_ironic_cluster(settings=data, nodes=nodes)

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id),
            user='ceph1',
            passwd='ceph1',
            tenant='ceph1')

        self.show_step(13)
        check_package_version_injected_in_bootstraps(self, "fuel-agent")

        check_package_version_injected_in_bootstraps(self, "fuel-agent",
                                                     ironic=True)

        self.show_step(14)
        self.show_step(15)
        self._create_os_resources(ironic_conn)

        self.show_step(16)
        self._boot_nova_instances(ironic_conn)

        self.show_step(17)
        ironic_conn.wait_for_vms(ironic_conn)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("review_fuel_agent_ironic_deploy")
