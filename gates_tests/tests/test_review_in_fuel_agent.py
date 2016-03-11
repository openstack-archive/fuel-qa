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

import yaml

from proboscis import test

from gates_tests.helpers.utils import replace_rpm_package

from fuelweb_test import logger
from fuelweb_test.helpers import ironic_actions
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.tests.test_ironic_base import TestIronicDeploy

from fuelweb_test import settings


@test(groups=["review_fuel_agent"])
class Gate(TestIronicDeploy):
    """Using in fuel-agent CI-gates
    Update fuel-agent on master node, bootstrap from review,
    build environment images and provision one node"""

    @staticmethod
    def update_bootstrap_cli_yaml():
        ssh = SSHManager()

        admin_remote = ssh._get_remote(ssh.admin_ip)
        path = "/etc/fuel-bootstrap-cli/fuel_bootstrap_cli.yaml"
        with admin_remote.open(path, 'r') as bootstrap_yaml:
            bootstrap_yaml_raw = yaml.load(bootstrap_yaml)
            logger.debug(bootstrap_yaml_raw)
            new_repo = {'name': 'auxiliary', 'priority': '1200',
                        'section': 'main restricted', 'suite': 'auxiliary', 'type': 'deb',
                        'uri': 'http://127.0.0.1:8080/ubuntu/auxiliary/'}
            bootstrap_yaml_raw['repos'].append(new_repo)
            logger.debug(bootstrap_yaml_raw)
        with admin_remote.open(path, 'w') as bootstrap_yaml:
            yaml.dump(
                bootstrap_yaml_raw, bootstrap_yaml, default_flow_style=False)

    @staticmethod
    def rebuild_and_activate_new_bootstrap(self):
        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image()
        self.env.fuel_bootstrap_actions.\
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions.\
            activate_bootstrap_image(uuid)

    @staticmethod
    def check_package_version_injected_in_bootstraps(
            self,
            package,
            ironic=None):

        ssh = SSHManager()
        try:
            pack_path = '/var/www/nailgun/{}/'.format(package)
            ssh.upload_to_remote(
                ip=ssh.admin_ip,
                source=settings.UPDATE_FUEL_PATH.rstrip('/'),
                target=pack_path)
        except Exception as e:
            logger.error("Could not upload package {e}".format(e=e))
            raise
        # Step 1 - unpack active bootstrap
        logger.info("unpack active bootstrap")

        if ironic:
            bootstrap = "/var/www/nailgun/bootstrap/ironic/{}".format(
                self.fuel_web.get_last_created_cluster())
        else:
            bootstrap = "/var/www/nailgun/bootstraps/active_bootstrap"
        bootstrap_var = "/var/root.squashfs"

        cmd = "unsquashfs -d {} {}/root.squashfs".format(
            bootstrap_var, bootstrap)
        ssh.execute_on_remote(
            ip=ssh.admin_ip,
            cmd=cmd)

        # Step 2 - check package version
        logger.info(
            "check package {} version injected in ubuntu bootstrap".format(
                package))

        cmd = "ls {}|grep {} |grep deb |cut -f 2 -d '_'".format(
            pack_path, package)

        package_from_review = ssh.execute_on_remote(
            ip=ssh.admin_ip,
            cmd=cmd)['stdout_str']

        logger.info("package from review is {}".format(package_from_review))

        awk_pattern = "awk '{print $2}'"
        cmd = "chroot {}/ /bin/bash -c \"dpkg -s {}\"|grep Version|{}".format(
            bootstrap_var, package, awk_pattern)
        installed_package = ssh.execute_on_remote(
            ip=ssh.admin_ip,
            cmd=cmd)['stdout_str']
        logger.info("injected package is {}".format(installed_package))

        if not package_from_review == installed_package:
            logger.error(
                "{} in bootstrap doesn't equal version from review".format(
                    package))
            raise

    @test(depends_on_groups=['prepare_release'],
          groups=["review_fuel_agent_ironic_deploy"])
    @log_snapshot_after_test
    def gate_patch_fuel_agent(self):
        """ Revert snapshot, update fuel-agent, bootstrap from review
        and provision one node

    Scenario:
        1. Revert snapshot "ready"
        2. Update fuel-agent, fuel-bootstrap-cli on master node
        3. Update bootstrap
        4. Bootstrap 3 slaves
        5. Add 1 node with controller role
        6. Add 1 node with ironic role
        7. Add 1 node with compute role
        8. Deploy the cluster
        9. Verify fuel-agent version in ubuntu and ironic-bootstrap
        10. Upload image to glance
        11. Enroll Ironic nodes
        12. Boot nova instance
        13. Check Nova instance status

        Snapshot review_fuel_agent_ironic_deploy
        """
        if not settings.UPDATE_FUEL:
                raise Exception("{} variable don't exist"
                                .format(settings.UPDATE_FUEL))
        self.show_step(1, initialize=True)
        self.env.revert_snapshot("ready")

        self.show_step(2)
        replace_rpm_package('fuel-agent')
        replace_rpm_package('fuel-bootstrap-cli')

        self.show_step(3)
        self.update_bootstrap_cli_yaml()
        self.rebuild_and_activate_new_bootstrap(self)

        self.show_step(4)
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:3])

        csettings = {}
        csettings.update(
            {
                'ironic': True
            }
        )
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=csettings
        )

        self.show_step(5)
        self.show_step(6)
        self.show_step(7)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['ironic'],
                'slave-03': ['compute'],
            }
        )

        self.show_step(8)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        ironic_conn = ironic_actions.IronicActions(
            self.fuel_web.get_public_vip(cluster_id))

        self.show_step(9)
        self.check_package_version_injected_in_bootstraps("fuel-agent")

        self.check_package_version_injected_in_bootstraps("fuel-agent",
                                                          ironic=True)

        self.show_step(10)
        self.show_step(11)
        self._create_os_resources(ironic_conn)

        self.show_step(12)
        self._boot_nova_instances(ironic_conn)

        self.show_step(13)
        ironic_conn.wait_for_vms(ironic_conn)
        ironic_conn.verify_vms_connection(ironic_conn)

        self.env.make_snapshot("review_fuel_agent_ironic_deploy")
