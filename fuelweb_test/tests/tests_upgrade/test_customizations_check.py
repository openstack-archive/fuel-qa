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

from __future__ import unicode_literals

import copy
import os

from proboscis import asserts
from proboscis import test

from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import YamlEditor
from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=['env_customizations_check'])
class EnvCustomizationsCheck(TestBasic):
    """Test suite for verification of tooling that checks customizations
    of an env prior to its upgrade.
    """

    CUSTOMIZED_FILE1 = \
        "/usr/lib/python2.7/dist-packages/neutronclient/__init__.py"
    CUSTOMIZED_FILE2 = \
        "/usr/lib/python2.7/dist-packages/neutronclient/version.py"
    CUDET_REPORT_PATH = "/tmp/cudet/info"
    CUDET_CONFIG_PATH = "/usr/share/cudet/cudet-config.yaml"
    SNAPSHOT_NAME = 'customizations_check_env'

    def add_comment_to_file_on_remote(
            self, ip, file_path, comment="customization"):
        """Add a comment to a package source file on an env node.

        This will be evaluated as a customization when performing
        the corresponding check.

        :param ip: str, IP address of an env node
        :param file_path: str, path to a file to update
        :param comment: str, comment to add to the file
        :return: None
        """
        cmd = 'echo "# {0}" >> {1}'.format(comment, file_path)
        self.ssh_manager.check_call(ip, cmd)

    def is_file_in_report(self, cluster_id, node_id, file_path):
        """Check that customized file is mentioned in report for the given node.

        :param cluster_id: int, ID of a cluster to check report for
        :param node_id: str, ID of a node to check report for
        :param file_path: str, file (full path) to check that it is referenced
                          in the report
        :return: bool
        """
        node_report_path = os.path.join(
            self.CUDET_REPORT_PATH,
            "cmds/cluster-{0}/node-{1}".format(cluster_id, node_id),
            "*packages-md5-verify*")
        report = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip, "cat {0}".format(node_report_path))

        return file_path in report.stdout_str

    def patch_cudet(self):
        """Add a workaround for LP #1625638.

        Enable cudet to use downloaded 9.1 packages db until it is officially
        published.
        """
        logger.info("Workaround until LP #1625638 is fixed: \n"
                    " - download 9.1 packages db to be used by cudet;\n"
                    " - patch cudet/main.py to avoid using online db.")

        cmd = "wget {0} -O {1}"
        centos_db_cmd = cmd.format(
            "https://jenkins-sandbox.infra.mirantis.net/job/generate-packages"
            "-database/8/artifact/9.0-centos-mu-1.sqlite",
            "/usr/share/cudet/db/versions/9.1/centos.sqlite")
        ubuntu_db_cmd = cmd.format(
            "https://jenkins-sandbox.infra.mirantis.net/job/generate-packages"
            "-database/9/artifact/9.0-ubuntu-mu-1.sqlite",
            "/usr/share/cudet/db/versions/9.1/ubuntu.sqlite")
        for cmd in (centos_db_cmd, ubuntu_db_cmd):
            self.ssh_manager.check_call(
                self.ssh_manager.admin_ip, cmd, timeout=60)

        cmd = ("sed -i '/.*def update_db.*/ a \\\\treturn False' "
               "/usr/lib/python2.7/site-packages/cudet/main.py")
        self.ssh_manager.check_call(
            self.ssh_manager.admin_ip, cmd, timeout=60)

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=['customizations_check_env'])
    @log_snapshot_after_test
    def customizations_check_env(self):
        """Create a simple cluster with cinder

        Scenario:
            1. Revert snapshot "ready_with_3_slaves"
            2. Create cluster
            3. Add 1 controller
            4. Add 1 compute node
            5. Add 1 cinder node
            6. Deploy cluster
            7. Run network check
            8. Run OSTF
            9. Install cudet tool

        Duration 60m
        Snapshot: customizations_check_env
        """
        self.check_run(self.SNAPSHOT_NAME)
        self.show_step(1)
        self.env.revert_snapshot("ready_with_3_slaves")

        self.show_step(2)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                "net_provider": 'neutron',
                "net_segment_type": settings.NEUTRON_SEGMENT_TYPE
            }
        )
        self.show_step(3)
        self.show_step(4)
        self.show_step(5)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(6)
        self.fuel_web.deploy_cluster_wait(cluster_id)
        self.show_step(7)
        self.fuel_web.verify_network(cluster_id)
        self.show_step(8)
        self.fuel_web.run_ostf(
            cluster_id=cluster_id)

        self.show_step(9)
        self.env.admin_install_pkg('python-cudet')

        # Check if LP #1625638 is fixed and patch cudet if not
        result = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip, "cudet", timeout=60)
        if "ERROR" in result.stdout_str:
            self.patch_cudet()

        self.env.make_snapshot(self.SNAPSHOT_NAME, is_make=True)

    @test(depends_on=[customizations_check_env],
          groups=['check_env_customizations'])
    @log_snapshot_after_test
    def check_env_customizations(self):
        """Check customizations of a node, of an env, of all nodes

        Scenario:
            1. Revert snapshot "customizations_check_env"
            2. Update a package source on all env nodes
            3. Check env for customizations - run cudet tool parametrizing it:
               - for all nodes
               - for all nodes of a particular env
               - for a particular node
               - for a particular node of a particular env
               For each option verify that customized file is mentioned
               in both, the command output and generated report.

        Duration 10m
        Snapshot: check_env_customizations
        """
        self.show_step(1)
        self.env.revert_snapshot(self.SNAPSHOT_NAME)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nodes:
            self.add_comment_to_file_on_remote(
                node['ip'], self.CUSTOMIZED_FILE1)

        # Cudet command options to be verified:
        # -e ENV_ID
        #       Check customizations only for the specified environment
        # -n NODE_ID
        #       Check customizations only for the specified node
        cases = {
            "cudet -e {0}".format(cluster_id): nodes,
            "cudet -n {0}".format(nodes[0]['id']): [nodes[0]],
            "cudet -e {0} -n {1}".format(cluster_id, nodes[0]['id']):
                [nodes[0]],
            "cudet": nodes,
        }

        self.show_step(3)
        for case in cases:
            logger.info("Running {0}...".format(case))
            result = self.ssh_manager.check_call(
                self.ssh_manager.admin_ip, case, timeout=60 * 5)

            asserts.assert_true(
                self.CUSTOMIZED_FILE1 in result.stdout_str,
                "Cudet doesn't report customizations in the command output")

            asserts.assert_true(
                self.ssh_manager.exists_on_remote(
                    self.ssh_manager.admin_ip,
                    self.CUDET_REPORT_PATH),
                "Cudet report is not generated")
            for node in cases[case]:
                asserts.assert_true(
                    self.is_file_in_report(
                        cluster_id, node['id'], self.CUSTOMIZED_FILE1),
                    "The {0!r} customized file is not referenced in the "
                    "corresponding node report".format(self.CUSTOMIZED_FILE1))

            logger.info("Deleting cudet report")
            self.ssh_manager.rm_rf_on_remote(
                self.ssh_manager.admin_ip, self.CUDET_REPORT_PATH)

        self.env.make_snapshot('check_env_customizations')

    @test(depends_on=[customizations_check_env],
          groups=['regenerate_report'])
    @log_snapshot_after_test
    def regenerate_report(self):
        """Check cudet report regenerating

        Scenario:
            1. Revert snapshot "customizations_check_env"
            2. Update a package source on a node
            3. Run cudet specifying the node to evaluate
            4. Verify that the report has been generated
            5. Update another package source on the node
            6. Run cudet specifying 'fake' option to only regenerate the report
            7. Verify that the second updated file is not referenced
               in the report
            8. Run cudet specifying the same node to evaluate
            9. Verify that the second updated file is referenced in the report
            10. Delete the report
            11. Run cudet specifying 'fake' option to only regenerate
                the report
            12. Verify that cudet doesn't generate report as
                no data is available

        Duration 10m
        Snapshot: regenerate_report
        """
        self.show_step(1)
        self.env.revert_snapshot(self.SNAPSHOT_NAME)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.add_comment_to_file_on_remote(
            nodes[0]['ip'], self.CUSTOMIZED_FILE1)

        self.show_step(3)
        result = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            "cudet -n {0}".format(nodes[0]['id']),
            timeout=60 * 5)

        self.show_step(4)
        asserts.assert_true(
            self.ssh_manager.exists_on_remote(
                self.ssh_manager.admin_ip,
                self.CUDET_REPORT_PATH),
            "Cudet report is not generated")

        self.show_step(5)
        self.add_comment_to_file_on_remote(
            nodes[0]['ip'], self.CUSTOMIZED_FILE2)

        # -f command option is used to only regenerate report, without
        # recollecting data from nodes
        self.show_step(6)
        self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            "cudet -n {0} -f".format(nodes[0]['id']),
            timeout=60 * 5)

        self.show_step(7)
        asserts.assert_false(
            self.is_file_in_report(
                cluster_id, nodes[0]['id'], self.CUSTOMIZED_FILE2),
            "The {0!r} customized file is referenced in the report, despite "
            "the fake run of cudet".format(self.CUSTOMIZED_FILE2))

        self.show_step(8)
        self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            "cudet -n {0}".format(nodes[0]['id']),
            timeout=60 * 5)

        self.show_step(9)
        asserts.assert_true(
            self.is_file_in_report(
                cluster_id, nodes[0]['id'], self.CUSTOMIZED_FILE2),
            "The {0!r} customized file is not referenced in the "
            "corresponding node report".format(self.CUSTOMIZED_FILE2))

        self.show_step(10)
        self.ssh_manager.rm_rf_on_remote(
            self.ssh_manager.admin_ip, self.CUDET_REPORT_PATH)

        self.show_step(11)
        self.ssh_manager.check_call(
            self.ssh_manager.admin_ip, "cudet -f", timeout=60 * 5)

        self.show_step(12)
        for node in nodes:
            node_report_dir = os.path.join(
                self.CUDET_REPORT_PATH,
                "cmds/cluster-{0}/node-{1}".format(cluster_id, node['id']))
            result = self.ssh_manager.check_call(
                self.ssh_manager.admin_ip, "ls -A {0}".format(node_report_dir))
            asserts.assert_equal(
                len(result.stdout), 0,
                "Report has been generated, although no data was collected")

        self.env.make_snapshot('regenerate_report')

    @test(depends_on=[customizations_check_env],
          groups=['filter_nodes_via_config'])
    @log_snapshot_after_test
    def filter_nodes_via_config(self):
        """Check customizations filtering nodes to check via cudet config

        Scenario:
            1. Revert snapshot "customizations_check_env"
            2. Update a package source on all env nodes
            3. Check nodes for customizations filtering them using
               cudet config file:
               - specify filtering via env ID
               - specify filtering via node ID
               - specify filtering via role name
               For each option verify that customized file is mentioned
               in both, the command output and generated report.

        Duration 10m
        Snapshot: filter_nodes_via_config
        """
        self.show_step(1)
        self.env.revert_snapshot(self.SNAPSHOT_NAME)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        for node in nodes:
            self.add_comment_to_file_on_remote(
                node['ip'], self.CUSTOMIZED_FILE1)

        cases = {
            "roles": ["cinder",
                      self.fuel_web.get_nailgun_cluster_nodes_by_roles(
                          cluster_id, ["cinder"])],
            "id": [nodes[0]['id'], [nodes[0]]],
            "cluster": [cluster_id, nodes],
        }

        self.show_step(3)
        cudet_config_dir = os.path.dirname(self.CUDET_CONFIG_PATH)
        for case in cases:
            with YamlEditor(
                    self.CUDET_CONFIG_PATH, self.ssh_manager.admin_ip) as ed:
                initial_content = copy.deepcopy(ed.content)
                ed.content['filters'][case].append(cases[case][0])

            # -c command option allows to specify the path to custom config
            # file to use instead of the default one
            logger.info("Running filtering for {0}...".format(case))
            result = self.ssh_manager.check_call(
                self.ssh_manager.admin_ip,
                "cd {0}; cudet -c {1}".format(cudet_config_dir,
                                              self.CUDET_CONFIG_PATH),
                timeout=60 * 5)

            asserts.assert_true(
                self.CUSTOMIZED_FILE1 in result.stdout_str,
                "Cudet doesn't report customizations in the command output")
            asserts.assert_true(
                self.ssh_manager.exists_on_remote(
                    self.ssh_manager.admin_ip,
                    self.CUDET_REPORT_PATH),
                "Cudet report is not generated")

            for node in cases[case][1]:
                asserts.assert_true(
                    self.is_file_in_report(
                        cluster_id, node['id'], self.CUSTOMIZED_FILE1),
                    "The {0!r} customized file is not referenced in the "
                    "corresponding node report".format(self.CUSTOMIZED_FILE1))

            logger.info("Deleted cudet report")
            self.ssh_manager.rm_rf_on_remote(
                self.ssh_manager.admin_ip, self.CUDET_REPORT_PATH)

            logger.info("Restore initial cudet config")
            with YamlEditor(
                    self.CUDET_CONFIG_PATH, self.ssh_manager.admin_ip) as ed:
                ed.content = copy.deepcopy(initial_content)

        self.env.make_snapshot('filter_nodes_via_config')

    @test(depends_on=[customizations_check_env],
          groups=['invalid_parameters_processing'])
    @log_snapshot_after_test
    def invalid_parameters_processing(self):
        """Check that cudet handles invalid parameters

        Scenario:
            1. Revert snapshot "customizations_check_env"
            2. Run cudet specifying an invalid env ID
            3. Verify that the message is returned notifying about wrong
               input and no report data is generated
            4. Run cudet specifying an invalid node ID
            5. Verify that the message is returned notifying about wrong
               input and no report data is generated
            6. Run cudet specifying an invalid custom config file
            7. Verify that the message is returned notifying about wrong
               input and no report data is generated

        Duration 10m
        Snapshot: invalid_parameters_processing
        """
        self.show_step(1)
        self.env.revert_snapshot(self.SNAPSHOT_NAME)

        self.show_step(2)
        result = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip, "cudet -e {0}".format(100))

        self.show_step(3)
        asserts.assert_true(
            "There are no nodes to check" in result.stdout_str,
            "No message is returned notifying about wrong input")
        asserts.assert_false(
            self.ssh_manager.exists_on_remote(
                self.ssh_manager.admin_ip,
                self.CUDET_REPORT_PATH),
            "Cudet report is generated")

        self.show_step(4)
        result = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip, "cudet -n {0}".format(100))

        self.show_step(5)
        asserts.assert_true(
            "There are no nodes to check" in result.stdout_str,
            "No message is returned notifying about wrong input")
        asserts.assert_false(
            self.ssh_manager.exists_on_remote(
                self.ssh_manager.admin_ip,
                self.CUDET_REPORT_PATH),
            "Cudet report is generated")

        self.show_step(6)
        result = self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            "cudet -c {0}".format("fake_config"),
            expected=[1])

        self.show_step(7)
        asserts.assert_true(
            "No such file or directory" in result.stderr_str,
            "No message is returned notifying about wrong input")
        asserts.assert_false(
            self.ssh_manager.exists_on_remote(
                self.ssh_manager.admin_ip,
                self.CUDET_REPORT_PATH),
            "Cudet report is generated")

        self.env.make_snapshot('invalid_parameters_processing')

    @test(depends_on=[customizations_check_env],
          groups=['check_offline_node_customizations'])
    @log_snapshot_after_test
    def check_offline_node_customizations(self):
        """Check that cudet handles attempt to check customizations
        of an offline node

          Scenario:
            1. Revert snapshot "customizations_check_env"
            2. Update a package source on a node
            3. Shutdown the node
            4. Run cudet specifying the node to evaluate
            5. Verify that no customization data is in the generated report

        Duration 10m
        Snapshot: check_offline_node_customizations
        """
        self.show_step(1)
        self.env.revert_snapshot(self.SNAPSHOT_NAME)

        self.show_step(2)
        cluster_id = self.fuel_web.get_last_created_cluster()
        node = self.fuel_web.client.list_cluster_nodes(cluster_id)[0]
        self.add_comment_to_file_on_remote(node['ip'], self.CUSTOMIZED_FILE1)

        self.show_step(3)
        devops_node = self.fuel_web.get_devops_node_by_nailgun_node(node)
        self.fuel_web.warm_shutdown_nodes([devops_node])

        self.show_step(4)
        self.ssh_manager.check_call(
            self.ssh_manager.admin_ip,
            "cudet -n {0}".format(node['id']),
            timeout=60 * 5)
        asserts.assert_false(
            self.is_file_in_report(
                cluster_id, node['id'], self.CUSTOMIZED_FILE1),
            "The data have been collected, although the node is offline")

        self.env.make_snapshot('check_offline_node_customizations')
