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

from fuelweb_test.helpers.checkers import verify_bootstrap_on_node
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import ironic_actions
from fuelweb_test import settings
from fuelweb_test.tests.test_ironic_base import TestIronicDeploy
from gates_tests.helpers import exceptions
from gates_tests.helpers.utils import (
    check_package_version_injected_in_bootstraps)
from gates_tests.helpers.utils import replace_rpm_package
from gates_tests.helpers.utils import update_bootstrap_cli_yaml


@test(groups=["review_fuel_agent"])
class Gate(TestIronicDeploy):
    """Using in fuel-agent CI-gates.

    Update fuel-agent on master node, bootstrap from review,
    build environment images and provision one node.
    """
    @test(depends_on_groups=['prepare_release'],
          groups=["review_fuel_agent_ironic_deploy"])
    @log_snapshot_after_test
    def gate_patch_fuel_agent(self):
        """Revert snapshot, update fuel-agent, bootstrap from review
        and provision one node.

        Scenario:
            1. Revert snapshot "ready"
            2. Update fuel-agent, fuel-bootstrap-cli on master node
            3. Update fuel_bootstrap_cli.yaml
            4. Rebuild bootstrap
            5. Verify fuel-agent version in ubuntu bootstrap image
            6. Bootstrap 5 slaves
            7. Verify Ubuntu bootstrap on slaves
            8. Add 1 node with controller
            9. Add 1 node ironic role
            10. Deploy the cluster
            11. Verify fuel-agent version in ironic-bootstrap
            12. Upload image to glance
            13. Enroll Ironic nodes
            14. Boot nova instance
            15. Check Nova instance status

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
        update_bootstrap_cli_yaml()

        self.show_step(4)
        if settings.UPDATE_FUEL:
            self.env.admin_actions.upload_packages(
                local_packages_dir=settings.UPDATE_FUEL_PATH,
                centos_repo_path=None,
                ubuntu_repo_path=settings.LOCAL_MIRROR_UBUNTU,
                clean_target=True)
        uuid, bootstrap_location = (
            self.env.fuel_bootstrap_actions.build_bootstrap_image())
        (self.env.fuel_bootstrap_actions.
            import_bootstrap_image(bootstrap_location))
        (self.env.fuel_bootstrap_actions.
            activate_bootstrap_image(uuid))

        self.show_step(5)
        check_package_version_injected_in_bootstraps("fuel-agent")

        self.show_step(6)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:2])

        self.show_step(7)
        for node in self.env.d_env.nodes().slaves[:2]:
            _ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            verify_bootstrap_on_node(_ip, os_type="ubuntu", uuid=uuid)

        data = {
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
            "ironic": True}

        nodes = {
            'slave-01': ['controller'],
            'slave-02': ['ironic']}

        self.show_step(8)
        self.show_step(9)
        self.show_step(10)

        cluster_id = self._deploy_ironic_cluster(settings=data, nodes=nodes)

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(11)
        check_package_version_injected_in_bootstraps("fuel-agent",
                                                     cluster_id=cluster_id,
                                                     ironic=True)

        self.show_step(12)
        self.show_step(13)
        self._create_os_resources(ironic_conn)
        self.show_step(14)
        self._boot_nova_instances(ironic_conn)

        self.show_step(15)
        ironic_conn.wait_for_vms(ironic_conn)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("review_fuel_agent_ironic_deploy")
