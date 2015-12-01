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

from devops.helpers.helpers import wait
from proboscis import SkipTest
from proboscis import test
from proboscis.asserts import assert_true, assert_equal, assert_not_equal

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers import fuel_actions
from fuelweb_test import settings
from fuelweb_test import logger
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.tests import base_test_case


@test(groups=["bvt_ubuntu_bootstrap"])
class UbuntuBootstrapBuild(base_test_case.TestBasic):
    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["prepare_default_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def build_default_bootstrap(self):
        """Verify than slaves retrieved ubuntu bootstrap instead CentOS

        Scenario:
            1. Revert snapshot ready
            2. Build and activate Ubuntu bootstrap with default settings
            3. Bootstrap slaves
            4. Verify Ubuntu bootstrap on slaves

        Duration 15m
        """
        self.env.revert_snapshot("ready")

        with self.env.d_env.get_admin_remote() as remote:
            fuel_bootstrap = fuel_actions.FuelBootstrapCliActions(remote)
            uuid, bootstrap_location = fuel_bootstrap.build_bootstrap_image()
            fuel_bootstrap.import_bootstrap_image(bootstrap_location)
            fuel_bootstrap.activate_bootstrap_image(uuid, notify_webui=True)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)

        for node in nodes:
            with self.fuel_web.get_ssh_for_node(node.name) as slave_remote:
                checkers.verify_bootstrap_on_node(slave_remote,
                                                  os_type="ubuntu",
                                                  uuid=uuid)

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["prepare_simple_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def build_simple_bootstrap(self):
        """Verify than slaves retrieved ubuntu bootstrap instead CentOS

        Scenario:
            1. Revert snapshot ready
            2. Build and activate Ubuntu bootstrap with extra package
            3. Bootstrap slaves
            4. Verify Ubuntu bootstrap on slaves

        Duration 15m
        """
        self.env.revert_snapshot("ready")

        with self.env.d_env.get_admin_remote() as remote:
            fuel_bootstrap = fuel_actions.FuelBootstrapCliActions(remote)
            bootstrap_default_params = \
                fuel_bootstrap.get_bootstrap_default_config()

            ubuntu_repo = bootstrap_default_params["ubuntu_repos"][0]["uri"]
            mos_repo = bootstrap_default_params["mos_repos"][0]["uri"]

            bootstrap_params = {
                "ubuntu-release": "trusty",
                "ubuntu-repo": "'{0} trusty'".format(ubuntu_repo),
                "mos-repo": "'{0} mos8.0'".format(mos_repo),
                "label": "UbuntuBootstrap",
                "output-dir": "/tmp",
                "package": ["ipython"]
            }

            uuid, bootstrap_location = \
                fuel_bootstrap.build_bootstrap_image(**bootstrap_params)
            fuel_bootstrap.import_bootstrap_image(bootstrap_location)
            fuel_bootstrap.activate_bootstrap_image(uuid, notify_webui=True)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)

        for node in nodes:
            with self.fuel_web.get_ssh_for_node(node.name) as slave_remote:
                checkers.verify_bootstrap_on_node(slave_remote,
                                                  os_type="ubuntu",
                                                  uuid=uuid)

                ipython_version = checkers.get_package_versions_from_node(
                    slave_remote, name="ipython", os_type="Ubuntu")
                assert_not_equal(ipython_version, "")

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_release],
          groups=["prepare_full_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def build_full_bootstrap(self):
        """Verify than slaves retrieved ubuntu bootstrap instead CentOS

        Scenario:
            1. Revert snapshot ready
            2. Build and activate Ubuntu bootstrap with extra settings
            3. Bootstrap slaves
            4. Verify Ubuntu bootstrap on slaves

        Duration 15m
        """
        self.env.revert_snapshot("ready")

        with self.env.d_env.get_admin_remote() as remote:
            fuel_bootstrap = fuel_actions.FuelBootstrapCliActions(remote)
            bootstrap_default_params = \
                fuel_bootstrap.get_bootstrap_default_config()

            ubuntu_repo = bootstrap_default_params["ubuntu_repos"][0]["uri"]
            mos_repo = bootstrap_default_params["mos_repos"][0]["uri"]

            bootstrap_script = '''\
                #!/bin/bash

                echo "testdata" > /test_bootstrap_script
                apt-get install ipython -y'''

            with tempfile.NamedTemporaryFile() as temp_file:
                temp_file.write(textwrap.dedent(bootstrap_script))
                temp_file.flush()
                remote.mkdir("/root/bin")
                remote.upload(temp_file.name, "/root/bin/bootstrap_script.sh")

            remote.mkdir("/root/inject/var/lib/testdir")
            remote.mkdir("/root/inject/var/www/testdir2")

            kernel_cmdline = ["biosdevname=0", "net.ifnames=1", "debug",
                              "ignore_loglevel", "log_buf_len=10M"]

            bootstrap_params = {
                "ubuntu-release": "trusty",
                "ubuntu-repo": "'{0} trusty'".format(ubuntu_repo),
                "mos-repo": "'{0} mos8.0'".format(mos_repo),
                # "http-proxy": "",
                # "https-proxy": "",
                # "direct-repo-addr": "",
                "script": "/root/bin/bootstrap_script.sh",
                "include-kernel-module": "core",
                "blacklist-kernel-module": "fuse",
                "label": "UbuntuBootstrap",
                "inject-files-from": "/root/include/",
                "extend-kopts": "'{0}'".format(" ".join(kernel_cmdline)),
                # "kernel-flavor": "",
                "output-dir": "/tmp",
                # "repo": [],
                "package": ["fuse", "sshfs"],
            }

            fuel_bootstrap = fuel_actions.FuelBootstrapCliActions(remote)
            uuid, bootstrap_location = \
                fuel_bootstrap.build_bootstrap_image(**bootstrap_params)
            fuel_bootstrap.import_bootstrap_image(bootstrap_location)
            fuel_bootstrap.activate_bootstrap_image(uuid, notify_webui=True)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])
        self.env.bootstrap_nodes(nodes)

        for node in nodes:
            with self.fuel_web.get_ssh_for_node(node.name) as slave_remote:
                checkers.verify_bootstrap_on_node(slave_remote,
                                                  os_type="ubuntu",
                                                  uuid=uuid)

                for package in ['ipython', 'fuse', 'sshfs']:
                    package_version = checkers.get_package_versions_from_node(
                        slave_remote, name=package, os_type="Ubuntu")
                    assert_not_equal(package_version, "",
                                     "Package {0} is not installed on slave "
                                     "{1}".format(package, node.name))

                for injected_dir in ["/var/lib/testdir", "/var/www/testdir2"]:
                    checkers.check_file_exists(slave_remote, injected_dir)

                file_content = remote.execute("cat /test_bootstrap_script")
                assert_equal("".join(file_content["stdout"]), "testdata",
                             "REPLACEME")

                actual_kernel_cmdline = \
                    "".join(remote.execute("cat /proc/cmdline")["stdout"])
                for kernel_opt in kernel_cmdline:
                    assert_true(kernel_opt in actual_kernel_cmdline,
                                "REPLACEME")

                modules_loaded = remote.execute("lsmod")
                core_mod_loaded = any(["core" in line
                                       for line in modules_loaded["stdout"]])
                logger.warning("Core module is {0}loaded, loadad modules: {1}"
                               .format("" if core_mod_loaded else "not ",
                                       "\n".join(modules_loaded)))

                fuse_blacklisted = remote.execute(
                    "grep -r fuse /etc/modprobe.d/*blacklist*")["exit_code"]
                logger.warning("{0}".format(fuse_blacklisted == 0))

    @test(depends_on_groups=["prepare_default_ubuntu_bootstrap"],
          groups=[""])
    @log_snapshot_after_test
    def create_list_import_delete_bootstrap_image(self):
        self.env.revert_snapshot("prepare_default_ubuntu_bootstrap")

        with self.env.d_env.get_admin_remote() as remote:
            fuel_bootstrap = fuel_actions.FuelBootstrapCliActions(remote)
            bootstrap_location, uuid = \
                fuel_bootstrap.build_bootstrap_image()
            fuel_bootstrap.import_bootstrap_image(bootstrap_location)

            assert_true(uuid in fuel_bootstrap.list_bootstrap_images(), "")
            assert_equal(3, fuel_bootstrap.list_bootstrap_images_uuids(), "")

            fuel_bootstrap.delete_bootstrap_image(uuid)
            assert_true(uuid not in fuel_bootstrap.list_bootstrap_images())
            assert_equal(2, fuel_bootstrap.list_bootstrap_images_uuids())

            uuid = fuel_bootstrap.list_bootstrap_images()
            assert_true("error" in fuel_bootstrap.delete_bootstrap_image(uuid))


@test(groups=["bvt_ubuntu_bootstrap"])
class UbuntuBootstrap(base_test_case.TestBasic):
    @test(depends_on_groups=['prepare_default_ubuntu_bootstrap'],
          groups=["deploy_stop_on_deploying_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def deploy_stop_on_deploying_ubuntu_bootstrap(self):
        pass

    @test(depends_on=[base_test_case.SetupEnvironment.prepare_slaves_3],
          groups=["deploy_stop_on_deploying_ubuntu_bootstrap"])
    @log_snapshot_after_test
    def deploy_stop_on_deploying_ubuntu_bootstrap(self):
        """Stop reset cluster in HA mode with 1 controller on Ubuntu Bootstrap

        Scenario:
            1. Create cluster in Ha mode with 1 controller
            2. Add 1 node with controller role
            3. Add 1 node with compute role
            4. Verify network
            5. Deploy cluster
            6. Stop deployment
            7. Verify bootstrap on slaves
            8. Add 1 node with cinder role
            9. Re-deploy cluster
            10. Verify network
            11. Run OSTF

        Duration 45m
        Snapshot: deploy_stop_on_deploying_ubuntu_bootstrap
        """

        if not self.env.revert_snapshot('prepare_default_ubuntu_bootstrap'):
            raise SkipTest()

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
                'slave-02': ['compute']
            }
        )
        # Network verification
        self.fuel_web.verify_network(cluster_id)

        # Deploy cluster and stop deployment, then verify bootstrap on slaves
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        self.fuel_web.deploy_task_wait(cluster_id=cluster_id, progress=10)
        self.fuel_web.stop_deployment_wait(cluster_id)

        self.fuel_web.wait_nodes_get_online_state(
            self.env.d_env.get_nodes(name__in=['slave-01', 'slave-02']),
            timeout=10 * 60)

        for node in self.env.d_env.get_nodes(
                name__in=['slave-01', 'slave-02', 'slave-03']):
            self.verify_bootstrap_on_node(node)

        # Network verification
        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.update_nodes(
            cluster_id,
            {
                'slave-03': ['cinder']
            }
        )

        self.fuel_web.deploy_cluster_wait(cluster_id)

        assert_equal(
            3, len(self.fuel_web.client.list_cluster_nodes(cluster_id)))

        # Run ostf
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
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Reset environment,
        # then verify bootstrap on slaves and re-deploy cluster
        self.fuel_web.stop_reset_env_wait(cluster_id)

        nodes = self.env.d_env.get_nodes(
            name__in=["slave-01", "slave-02", "slave-03"])

        self.fuel_web.wait_nodes_get_online_state(nodes, timeout=10 * 60)
        for node in nodes:
            self.verify_bootstrap_on_node(node)

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
            raise SkipTest()

        cluster_id = self.fuel_web.get_last_created_cluster()

        # Delete cluster, then verify bootstrap on slaves
        self.fuel_web.client.delete_cluster(cluster_id)

        # wait nodes go to reboot
        wait(lambda: not self.fuel_web.client.list_nodes(), timeout=10 * 60)

        # wait for nodes to appear after bootstrap
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=10 * 60)

        for node in self.env.d_env.get_nodes(
                name__in=['slave-01', 'slave-02', 'slave-03']):
            self.verify_bootstrap_on_node(node)

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
            raise SkipTest()

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

        self.fuel_web.run_network_verify(cluster_id)
        self.fuel_web.deploy_cluster_wait(cluster_id, check_services=False)

        # wait for nodes to appear after bootstrap
        wait(lambda: len(self.fuel_web.client.list_nodes()) == 3,
             timeout=10 * 60)

        self.verify_bootstrap_on_node(
            self.env.d_env.get_node(name="slave-03"))
