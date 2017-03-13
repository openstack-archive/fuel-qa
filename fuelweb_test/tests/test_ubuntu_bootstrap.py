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
import tempfile
import textwrap

from devops.error import DevopsCalledProcessError
from devops.helpers.helpers import tcp_ping
from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis import SkipTest
from proboscis import test

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers import utils
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test import settings
from fuelweb_test.tests import base_test_case


@test(groups=["ubuntu_bootstrap_builder", "bvt_ubuntu_bootstrap"])
class UbuntuBootstrapBuild(base_test_case.TestBasic):
    @staticmethod
    def _get_main_repo(repos, repo_name, suite_type):
        for repo in repos:
            if repo_name not in repo["name"]:
                continue

            if suite_type == "main" and not any(["updates" in repo["suite"],
                                                 "security" in repo["suite"],
                                                 "proposed" in repo["suite"]]):
                return repo

            else:
                if suite_type in repo["suite"]:
                    return repo

        raise Exception("Can not find repo '{0}' suite '{1}' in repo list: {2}"
                        .format(repo_name, suite_type, repos))

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["build_default_bootstrap"])
    @log_snapshot_after_test
    def build_default_bootstrap(self):
        """Verify than slaves retrieved Default ubuntu bootstrap

        Scenario:
            1. Revert snapshot ready
            2. Build and activate Ubuntu bootstrap with default settings
            3. Bootstrap slaves
            4. Verify Ubuntu bootstrap on slaves

        Duration: 20m
        Snapshot: build_default_bootstrap
        """
        self.env.revert_snapshot("ready")

        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image()
        self.env.fuel_bootstrap_actions.\
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions.\
            activate_bootstrap_image(uuid)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)

        for node in nodes:
            _ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            checkers.verify_bootstrap_on_node(_ip, os_type="ubuntu", uuid=uuid)

        self.env.make_snapshot("build_default_bootstrap", is_make=True)

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["build_simple_bootstrap"])
    @log_snapshot_after_test
    def build_simple_bootstrap(self):
        """Verify than slaves retrieved Ubuntu bootstrap with extra package

        Scenario:
            1. Revert snapshot ready
            2. Build and activate Ubuntu bootstrap with extra package
            3. Bootstrap slaves
            4. Verify Ubuntu bootstrap on slaves

        Duration: 20m
        """
        self.env.revert_snapshot("ready")

        bootstrap_default_params = \
            self.env.fuel_bootstrap_actions.get_bootstrap_default_config()

        additional_repos = [
            self._get_main_repo(bootstrap_default_params["repos"],
                                "ubuntu", "main"),
            self._get_main_repo(bootstrap_default_params["repos"],
                                "ubuntu", "updates"),
            self._get_main_repo(bootstrap_default_params["repos"],
                                "mos", "main")]

        bootstrap_params = {
            "ubuntu-release": "xenial",
            "repo": ["'deb {0} {1} {2}'".format(repo['uri'],
                                                repo['suite'],
                                                repo['section'])
                     for repo in additional_repos],
            "label": "UbuntuBootstrap",
            "output-dir": "/tmp",
            "package": ["ipython"]
        }

        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image(
                **bootstrap_params)

        self.env.fuel_bootstrap_actions.\
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions.\
            activate_bootstrap_image(uuid)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)

        for node in nodes:
            n_node = self.fuel_web.get_nailgun_node_by_devops_node(node)
            checkers.verify_bootstrap_on_node(n_node['ip'],
                                              os_type="ubuntu",
                                              uuid=uuid)

            ipython_version = utils.get_package_versions_from_node(
                n_node['ip'], name="ipython", os_type="Ubuntu")
            assert_not_equal(ipython_version, "")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["build_full_bootstrap"])
    @log_snapshot_after_test
    def build_full_bootstrap(self):
        """Verify than slaves retrieved Ubuntu bootstrap with extra settings

        Scenario:
            1. Revert snapshot ready
            2. Build and activate Ubuntu bootstrap with extra settings
            3. Bootstrap slaves
            4. Verify Ubuntu bootstrap on slaves

        Duration: 20m
        """
        self.env.revert_snapshot("ready")

        with self.env.d_env.get_admin_remote() as remote:
            bootstrap_script = '''\
                #!/bin/bash

                echo "testdata" > /test_bootstrap_script
                apt-get install ipython -y
                '''

            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(textwrap.dedent(bootstrap_script))
                temp_file.flush()
                remote.mkdir("/root/bin")
                remote.upload(temp_file.name, "/root/bin/bootstrap_script.sh")

            remote.mkdir("/root/inject/var/lib/testdir")
            remote.mkdir("/root/inject/var/www/testdir2")

            kernel_cmdline = ["biosdevname=0", "net.ifnames=1", "debug",
                              "ignore_loglevel", "log_buf_len=10M"]

        bootstrap_default_params = \
            self.env.fuel_bootstrap_actions.get_bootstrap_default_config()

        additional_repos = [
            self._get_main_repo(bootstrap_default_params["repos"],
                                "ubuntu", "main"),
            self._get_main_repo(bootstrap_default_params["repos"],
                                "ubuntu", "updates"),
            self._get_main_repo(bootstrap_default_params["repos"],
                                "mos", "main")]

        bootstrap_params = {
            "ubuntu-release": "xenial",
            "repo": ["'deb {0} {1} {2}'".format(repo['uri'],
                                                repo['suite'],
                                                repo['section'])
                     for repo in additional_repos],
            "direct-repo-addr": [self.env.admin_node_ip],
            "script": "/root/bin/bootstrap_script.sh",
            "label": "UbuntuBootstrap",
            "extra-dir": ["/root/inject/"],
            "extend-kopts": "'{0}'".format(" ".join(kernel_cmdline)),
            "kernel-flavor": "linux-generic-lts-xenial",
            "output-dir": "/tmp",
            "package": ["fuse", "sshfs"],
        }

        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image(
                **bootstrap_params)
        self.env.fuel_bootstrap_actions.\
            import_bootstrap_image(bootstrap_location)
        self.env.fuel_bootstrap_actions.\
            activate_bootstrap_image(uuid)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)

        for node in nodes:
            n_node = self.fuel_web.get_nailgun_node_by_devops_node(node)
            with self.fuel_web.get_ssh_for_node(node.name) as slave_remote:
                checkers.verify_bootstrap_on_node(n_node['ip'],
                                                  os_type="ubuntu",
                                                  uuid=uuid)

                for package in ['ipython', 'fuse', 'sshfs']:
                    package_version = utils.get_package_versions_from_node(
                        n_node['ip'], name=package, os_type="Ubuntu")
                    assert_not_equal(package_version, "",
                                     "Package {0} is not installed on slave "
                                     "{1}".format(package, node.name))

                for injected_dir in ["/var/lib/testdir", "/var/www/testdir2"]:
                    checkers.check_file_exists(n_node['ip'], injected_dir)

                file_content = \
                    slave_remote.execute("cat /test_bootstrap_script")
                assert_equal("".join(file_content["stdout"]).strip(),
                             "testdata")

                actual_kernel_cmdline = "".join(
                    slave_remote.execute("cat /proc/cmdline")["stdout"])

                for kernel_opt in kernel_cmdline:
                    assert_true(kernel_opt in actual_kernel_cmdline,
                                "No {0} option in cmdline: {1}"
                                .format(kernel_opt, actual_kernel_cmdline))

    @test(depends_on_groups=["build_default_bootstrap"],
          groups=["create_list_import_delete_bootstrap_image"])
    @log_snapshot_after_test
    def create_list_import_delete_bootstrap_image(self):
        """Validate CRD operations of fuel-bootstrap utility

        Scenario:
            1. Revert snapshot build_default_bootstrap
            2. Build and Ubuntu bootstrap with default settings
            3. Validate it is available in images list
            4. Delete Ubuntu bootstrap image
            5. Validate it is not available and can not be activated
            6. Validate restriction for deleting active image

        Duration 30m
        """
        self.env.revert_snapshot("build_default_bootstrap")

        expected_bootstrap_uuids = \
            self.env.fuel_bootstrap_actions.list_bootstrap_images_uuids()

        uuid, bootstrap_location = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image()
        self.env.fuel_bootstrap_actions.\
            import_bootstrap_image(bootstrap_location)

        bootstrap_uuids = self.env.fuel_bootstrap_actions.\
            list_bootstrap_images_uuids()
        assert_true(uuid in bootstrap_uuids,
                    "Newly built bootstrap image {0} is not in list of "
                    "available images: {1}".format(uuid, bootstrap_uuids))

        assert_equal(
            len(expected_bootstrap_uuids) + 1, len(bootstrap_uuids),
            "Only {0} bootstrap images should be available; current list: "
            "\n{1}".format(bootstrap_uuids, len(expected_bootstrap_uuids) + 1))

        self.env.fuel_bootstrap_actions.delete_bootstrap_image(uuid)

        bootstrap_uuids = self.env.fuel_bootstrap_actions.\
            list_bootstrap_images_uuids()
        assert_true(uuid not in bootstrap_uuids,
                    "Bootstrap {0} was not deleted and still available: {1}"
                    .format(uuid, bootstrap_uuids))

        assert_raises(DevopsCalledProcessError,
                      self.env.fuel_bootstrap_actions.activate_bootstrap_image,
                      uuid)

        assert_equal(
            len(expected_bootstrap_uuids), len(bootstrap_uuids),
            "Only {0} bootstrap images should be available; current list: "
            "\n{1}".format(bootstrap_uuids, len(expected_bootstrap_uuids)))

        uuid = self.env.fuel_bootstrap_actions.get_active_bootstrap_uuid()
        # we need to fail in case uuid is None, otherwise the assert_raises
        # will use: uuid = None
        assert_true(uuid is not None, "No active bootstrap. Possibly centos "
                    "is active or something went wrong.")
        assert_raises(
            DevopsCalledProcessError,
            self.env.fuel_bootstrap_actions.delete_bootstrap_image,
            uuid)


@test(groups=["ubuntu_bootstrap_deploy", "bvt_ubuntu_bootstrap"])
class UbuntuBootstrap(base_test_case.TestBasic):
    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["deploy_with_two_ubuntu_bootstraps"])
    @log_snapshot_after_test
    def deploy_with_two_ubuntu_bootstraps(self):
        """Deploy cluster with two different bootstrap images

        Scenario:
            1. Boot two nodes
            2. Validate bootstrap
            3. Build another one bootstrap image
            4. Boot additional node
            5. Validate new bootstrap
            6. Create cluster in Ha mode with 1 controller, 1 compute
               and 1 cinder node
            7. Deploy cluster
            8. Verify network
            9. Run OSTF

        Duration 45m
        """
        if not self.env.revert_snapshot('ready'):
            raise SkipTest('Required snapshot not found')

        uuid = self.env.fuel_bootstrap_actions.get_active_bootstrap_uuid()

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02"])

        self.env.bootstrap_nodes(nodes)
        for node in nodes:
            checkers.verify_bootstrap_on_node(
                self.env.fuel_web.get_node_ip_by_devops_name(node.name),
                os_type="ubuntu",
                uuid=uuid)

        new_uuid, _ = \
            self.env.fuel_bootstrap_actions.build_bootstrap_image(
                activate=True)
        new_node = self.env.d_env.get_node(name="slave-03")
        self.env.bootstrap_nodes([new_node])
        checkers.verify_bootstrap_on_node(
            self.env.fuel_web.get_node_ip_by_devops_name(new_node.name),
            os_type="ubuntu",
            uuid=new_uuid)

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'tenant': 'stop_deploy',
                'user': 'stop_deploy',
                'password': 'stop_deploy',
            }
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        expected_nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        assert_equal(
            len(expected_nodes),
            len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["deploy_stop_on_deploying_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def deploy_stop_on_deploying_ubuntu_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Create cluster in Ha mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Add 1 node with cinder role
            5. Verify network
            6. Provision nodes
            7. Make a test file on every node
            8. Deploy nodes
            9. Stop deployment
            10. Verify nodes are not reset to bootstrap image
            11. Re-deploy cluster
            12. Verify network
            13. Run OSTF

        Duration 45m
        Snapshot: deploy_stop_on_deploying_ubuntu_bootstrap
        """

        if not self.env.revert_snapshot('ready_with_3_slaves'):
            raise SkipTest('Required snapshot not found')

        def check_node(ssh_manager_executor, ip):
            cmd = 'grep bootstrap /etc/hostname'
            err_msg = "Node with ip {:s} was reset to bootstrap".format(ip)
            ssh_manager_executor(ip=ip,
                                 cmd=cmd,
                                 err_msg=err_msg,
                                 assert_ec_equal=[1])
            cmd = 'grep test ~/test'
            ssh_manager_executor(ip=ip,
                                 cmd=cmd,
                                 err_msg=err_msg,
                                 assert_ec_equal=[0])

        def make_test_file(ssh_manager_executor, ip):
            cmd = 'echo test >> ~/test'
            ssh_manager_executor(ip, cmd)

        self.show_step(step=1, initialize=True)

        executor = self.ssh_manager.execute_on_remote

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings={
                'tenant': 'stop_deploy',
                'user': 'stop_deploy',
                'password': 'stop_deploy',
            }
        )
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['cinder']
            }
        )

        self.show_step(5)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(6)
        self.fuel_web.provisioning_cluster_wait(cluster_id)

        self.show_step(7)
        nodes_ips = [
            self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            for node in self.env.d_env.get_nodes(
                name__in=['slave-01', 'slave-02', 'slave-03'])]

        for _ip in nodes_ips:
            make_test_file(executor, _ip)

        self.show_step(8)
        self.fuel_web.deploy_task_wait(cluster_id=cluster_id, progress=30)

        self.show_step(9)
        self.fuel_web.stop_deployment_wait(cluster_id)

        self.show_step(10)
        for _ip in nodes_ips:
            check_node(executor, _ip)

        self.show_step(11)
        self.fuel_web.deploy_cluster_wait(cluster_id)

        assert_equal(
            len(nodes_ips),
            len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        self.show_step(12)
        self.fuel_web.verify_network(cluster_id)

        self.show_step(13)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])

        self.env.make_snapshot(
            "deploy_stop_on_deploying_ubuntu_bootstrap",
            is_make=True)

    @test(depends_on_groups=['deploy_stop_on_deploying_ubuntu_bootstrap'],
          groups=["deploy_reset_on_ready_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def reset_on_ready_ubuntu_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Reset cluster
            2. Verify bootstrap on slaves
            3. Re-deploy cluster
            4. Verify network
            5. Run OSTF

        Duration 30m
        """

        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_ubuntu_bootstrap'):
            raise SkipTest('Required snapshot not found')

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Reset environment,
        # then verify bootstrap on slaves and re-deploy cluster
        self.fuel_web.stop_reset_env_wait(cluster_id)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])

        self.fuel_web.wait_nodes_get_online_state(nodes, timeout=10 * 60)
        for node in nodes:
            nailgun_node = self.fuel_web.get_nailgun_node_by_devops_node(node)
            wait(lambda: tcp_ping(nailgun_node['ip'], 22),
                 timeout=300,
                 timeout_msg=("Node {0} is still unreachable after {1} "
                              "seconds".format(nailgun_node['name'], 300)))
            checkers.verify_bootstrap_on_node(
                nailgun_node['ip'], os_type="ubuntu")

        self.fuel_web.deploy_cluster_wait(cluster_id)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # Run ostf
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['smoke'])

    @test(depends_on_groups=['deploy_stop_on_deploying_ubuntu_bootstrap'],
          groups=["delete_on_ready_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def delete_on_ready_ubuntu_bootstrap(self):
        """Delete cluster cluster in HA mode\
        with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Delete cluster
            2. Verify bootstrap on slaves

        Duration 30m
        Snapshot: delete_on_ready_ubuntu_bootstrap
        """
        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_ubuntu_bootstrap'):
            raise SkipTest('Required snapshot not found')

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Delete cluster, then verify bootstrap on slaves
        self.fuel_web.client.delete_cluster(cluster_id)

        # wait nodes go to reboot
        wait(lambda: not self.fuel_web.client.list_nodes(), timeout=10 * 60,
             timeout_msg='Timeout while waiting nodes to become offline')

        # wait for nodes to appear after bootstrap
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=10 * 60,
             timeout_msg='Timeout while waiting nodes to become online')

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        for node in nodes:
            _ip = self.fuel_web.get_nailgun_node_by_devops_node(node)['ip']
            checkers.verify_bootstrap_on_node(_ip, os_type="ubuntu")

        self.env.make_snapshot(
            "delete_on_ready_ubuntu_bootstrap",
            is_make=True)

    @test(depends_on_groups=['deploy_stop_on_deploying_ubuntu_bootstrap'],
          groups=["delete_node_on_ready_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def delete_node_on_ready_ubuntu_bootstrap(self):
        """Delete node from cluster in HA mode\
        with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Delete node
            2. Verify bootstrap on slaves

        Duration 30m
        Snapshot: delete_on_ready_ubuntu_bootstrap
        """
        if not self.env.revert_snapshot(
                'deploy_stop_on_deploying_ubuntu_bootstrap'):
            raise SkipTest('Required snapshot not found')

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Delete cluster, then verify bootstrap on slaves
        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder']
            },
            pending_addition=False,
            pending_deletion=True
        )

        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # wait for nodes to appear after bootstrap
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=10 * 60,
             timeout_msg='Timeout while waiting nodes to become online')
        self.fuel_web.verify_network(cluster_id)

        node = self.fuel_web.get_nailgun_node_by_name("slave-03")
        checkers.verify_bootstrap_on_node(node['ip'], os_type="ubuntu")
