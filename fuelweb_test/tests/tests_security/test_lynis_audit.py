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
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import install_lynis_master
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["tests_security_compliance"])
class TestsSecurityCompliance(TestBasic):
    @test(depends_on=[SetupEnvironment.setup_master],
          groups=["master_node_compliance"])
    @log_snapshot_after_test
    def master_node_compliance(self):
        """ Install and run lynis on master node

        Scenario:
            1. Revert snapshot empty
            2. Install Lynis package
            3. Run lynis custom test
            4. Analyse lynis results

        Duration: 5 min
        Snapshot: master_node_compliance
        """

        self.show_step(1)
        self.env.revert_snapshot('empty')
        self.show_step(2)
        ip_master = self.ssh_manager.admin_ip
        install_lynis_master(master_node_ip=ip_master)
        cmd = 'lynis -c -Q --tests-category "custom"'
        self.ssh_manager.execute_on_remote(ip_master, cmd)
        cmd =\
            'awk -F\']\' \'/Mirantis\S+\sResult/ {print $2}\' ' \
            '/var/log/lynis.log'
        lynis_failed_tests = [
            test for test in self.ssh_manager.execute_on_remote(
                ip_master, cmd)['stdout']]
        logger.debug(lynis_failed_tests)
        self.show_step(4)
        # Check that lynis test haven't failed tests
        assert_equal(len(lynis_failed_tests), 0,
                     message="Some lynis tests was failed."
                             " Please check lynis logs for that")

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["slave_nodes_compliance"])
    @log_snapshot_after_test
    def slave_nodes_compliance(self):
        """ Install and run lynis on slave nodes

        Scenario:
        1. Revert snapshot ready_with_3_slaves
        2. Create cluster with 3 nodes: controller, compute, cinder
        3  Install lynis package on slaves
        4. Run lynis custom test
        5. Analyze lynis results

        Duration: 30 min
        """

        self.show_step(1)
        self.env.revert_snapshot('ready_with_3_slaves')
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
        )
        self.show_step(2)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(3)
        cmd =\
            'echo 172.18.162.63 perestroika-repo-tst.infra.mirantis.net' \
            ' >> /etc/hosts'
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            self.ssh_manager.execute_on_remote(node['ip'], cmd)
        cmd =\
            'sudo add-apt-repository "http://perestroika-repo-tst.' \
            'infra.mirantis.net/mos-packaging/ubuntu/"'
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            self.ssh_manager.execute_on_remote(node['ip'], cmd)
        cmd = 'apt-get install lynis'
        for node in self.fuel_web.client.list_cluster_nodes(cluster_id):
            self.ssh_manager.execute_on_remote(node['ip'], cmd)
        #  check that lynis version is correct and installed from perestroika
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.show_step(4)
        cmd = 'lynis -c -Q --tests-category "custom"'
        for node in nodes:
            self.ssh_manager.execute_on_remote(node['ip'], cmd)
        self.show_step(5)
        cmd = \
            'awk -F\']\' \'/Mirantis\S+\sResult/ {print $2}\' ' \
            '/var/log/lynis.log'

        for node in nodes:
            lynis_failed_tests = [
                test for test in self.ssh_manager.execute_on_remote(
                    node['ip'], cmd)['stdout']]
            logger.debug(lynis_failed_tests)
            self.show_step(4)
        #  Check that lynis test haven't failed tests
            assert_equal(len(lynis_failed_tests),
                         0,
                         message="Some lynis tests was failed for node {}."
                                 "Please check lynis logs".format(node['ip']))
