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


from proboscis import test
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test import logger
from fuelweb_test.helpers import utils


@test(groups=["iac_git"])
class TestIronicBase(TestBasic):
    """TestIronicBase"""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_all],
          groups=["iac_git_clone"])
    @log_snapshot_after_test
    def deploy_plugin(
            self):
        """Deploy cluster in HA mode with Ironic:

           Scenario:
               1. Create cluster
               2. Add 3 controller node
               3. Add 1 compute node
               4. Deploy cluster
               5. Verify network
               6. Run OSTF
               7. Install extension
               8. Add git repository
               9. Check if git repository added
           Snapshot: ironic_base
        """

        self.env.revert_snapshot("ready_with_5_slaves")

        data = {
            'tenant': 'iac_git_clone',
            'user': 'iac_git_clone',
            'password': 'iac_git_clone'
        }
        self.show_step(1, initialize=True)
        self.show_step(2)
        self.show_step(3)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['controller'],
                'slave-03': ['controller'],
                'slave-04': ['compute'],
                'slave-05': ['compute']
            }
        )
        self.show_step(4)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.run_ostf(cluster_id=cluster_id)
        self.show_step(7)
        logger.info('Add repository')
        self.fuel_web.add_local_centos_mirror(
            cluster_id=cluster_id,
            path='mirror.fuel-infra.org/mos-repos/centos/mos-master-centos7'
                 '/os/x86_64/', priority=1001)
        admin_ip = self.env.get_admin_node_ip()
        logger.info('Install rpm packages')
        utils.install_pkg_2(admin_ip, 'git')
        utils.install_pkg_2(admin_ip, 'fuel-nailgun-extension-iac')

        def runCommand(command, admin_ip=admin_ip, expected_string=None):
            result = self.fuel_web.ssh_manager.execute(admin_ip, command)
            logger.info('running: ' + command)
            if not expected_string:
                if result['exit_code'] == 0:
                    return True
            else:
                if expected_string in result['stdout_str']:
                    return True
            logger.error(result['stdout_str'])
            return False


        runCommand('service nailgun restart')
        runCommand('nailgun_syncdb')
        self.show_step(8)
        runCommand('fuel2 gitrepo create --env=1 --name=test \
                   --url="git@github.com:valentyn-yakovlev/demo-lcm.git" \
                   --ref=master --key="/root/.ssh/id_rsa"')
        self.show_step(9)
        assert runCommand(command='fuel2 gitrepo list',
                          expected_string='git@github.com')

        self.env.make_snapshot("iac_git_clone")
