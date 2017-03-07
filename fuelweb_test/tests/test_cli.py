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

from devops.helpers.helpers import wait
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from fuelweb_test.helpers.checkers import check_cluster_presence
from fuelweb_test.helpers.checkers import check_cobbler_node_exists
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import generate_floating_ranges
from fuelweb_test.settings import DEPLOYMENT_MODE
from fuelweb_test.settings import SSL_CN
from fuelweb_test.settings import PATH_TO_PEM
from fuelweb_test.settings import NEUTRON_SEGMENT_TYPE
from fuelweb_test.settings import NEUTRON_SEGMENT
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic
from fuelweb_test.tests import test_cli_base
from fuelweb_test import logger


@test(groups=["command_line_minimal"])
class CommandLineMinimal(TestBasic):
    """CommandLineMinimal."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.setup_with_custom_manifests],
          groups=["hiera_deploy"])
    @log_snapshot_after_test
    def hiera_deploy(self):
        """Deploy cluster with controller node only

        Scenario:
            1. Start installation of master
            2. Enter "fuelmenu"
            3. Upload custom manifests
            4. Kill "fuelmenu" pid
            5. Deploy hiera manifest

        Duration 20m
        """
        self.env.revert_snapshot("empty_custom_manifests")

        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[:1])

        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=DEPLOYMENT_MODE
        )
        self.fuel_web.update_nodes(
            cluster_id,
            {'slave-01': ['controller']}
        )
        admin_ip = self.ssh_manager.admin_ip
        node_id = self.fuel_web.get_nailgun_node_by_devops_node(
            self.env.d_env.nodes().slaves[0])['id']
        cmd = 'fuel node --node {0} --provision --env {1}'.format(node_id,
                                                                  cluster_id)
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        self.fuel_web.provisioning_cluster_wait(cluster_id)
        cmd = 'fuel node --node {0} --end hiera --env {1}'.format(node_id,
                                                                  cluster_id)
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        cmd = 'fuel task | grep deployment | awk \'{print $9}\''
        wait(lambda: int(
            self.ssh_manager.execute_on_remote(
                admin_ip, cmd)['stdout'][0].rstrip()) == 100, timeout=120,
             timeout_msg='hiera manifest was not applied')
        cmd = 'ssh -q node-{0} "hiera role"'.format(node_id)
        role = self.ssh_manager.execute_on_remote(
            admin_ip, cmd)['stdout'][0].rstrip()
        assert_equal(role, 'primary-controller', "node with deployed hiera "
                                                 "was not found")


@test(groups=["command_line"])
class CommandLineTest(test_cli_base.CommandLine):
    """CommandLine."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_3],
          groups=["cli_selected_nodes_deploy"])
    @log_snapshot_after_test
    def cli_selected_nodes_deploy(self):
        """Create and deploy environment using Fuel CLI and check CN name
           is equal to the public name passed via UI (user-owned cert)

        Scenario:
            1. Create environment using fuel-qa
            2. Create a cluster using Fuel CLI
            3. Add floating ranges for public network
            4. Allow public network assignment for all nodes
            5. Get cluster settings
            6. Provision a controller node using Fuel CLI
            7. Provision two compute+cinder nodes using Fuel CLI
            8. Deploy the controller node using Fuel CLI
            9. Deploy the compute+cinder nodes using Fuel CLI
            10. Compare network settings after compute deployment task
            11. Verify network
            12. Check that all services work by 'https'
            13. Check that all services have domain name
            14. Find 'CN' value at the output:
                CN value is equal to the value specified
                at certificate provided via Fuel UI
            15. Find keypair data at the output:
                Keypair data is equal to the value specified
                at certificate provided via Fuel UI
            16. Compare floating ranges
            17. Get deployment-info
            18. Get cluster settings after deployment task
            19. Compare cluster settings after deploy and before deploy
            20. Run OSTF


        Duration 50m
        """
        self.env.revert_snapshot("ready_with_3_slaves")
        node_ids = sorted([node['id'] for node in
                           self.fuel_web.client.list_nodes()])
        release_id = self.fuel_web.get_releases_list_for_os(
            release_name=OPENSTACK_RELEASE)[0]
        admin_ip = self.ssh_manager.admin_ip
        # Create an environment
        self.show_step(1)
        if NEUTRON_SEGMENT_TYPE:
            nst = '--nst={0}'.format(NEUTRON_SEGMENT_TYPE)
        else:
            nst = ''
        self.show_step(2)
        cmd = ('fuel env create --name={0} --release={1} {2} --json'.format(
            self.__class__.__name__, release_id, nst))
        env_result =\
            self.ssh_manager.execute_on_remote(admin_ip, cmd,
                                               jsonify=True)['stdout_json']
        cluster_id = env_result['id']
        self.show_step(3)
        # Update network parameters
        self.update_cli_network_configuration(cluster_id)
        # Change floating ranges
        current_floating_range = self.get_floating_ranges(cluster_id)
        logger.info("Current floating ranges: {0}".format(
            current_floating_range))
        first_floating_address = current_floating_range[0][0]
        logger.info("First floating address: {0}".format(
            first_floating_address))
        last_floating_address = current_floating_range[0][1]
        logger.info("Last floating address: {0}".format(last_floating_address))
        new_floating_range = generate_floating_ranges(first_floating_address,
                                                      last_floating_address,
                                                      10)
        logger.info("New floating range: {0}".format(new_floating_range))
        self.change_floating_ranges(cluster_id, new_floating_range)
        # Update SSL configuration
        self.update_ssl_configuration(cluster_id)

        # Allow public network assignment for all nodes
        # Get cluster settings before deploy
        self.show_step(4)
        self.show_step(5)
        cluster_settings = self.download_settings(cluster_id)
        cluster_settings['editable']['public_network_assignment'][
            'assign_to_all_nodes']['value'] = True
        self.upload_settings(cluster_id, cluster_settings)
        self.show_step(6)
        # Add and provision a controller node
        logger.info("Add to the cluster \
        and start provisioning a controller node [{0}]".format(node_ids[0]))
        cmd = ('fuel --env-id={0} node set --node {1}\
         --role=controller'.format(cluster_id, node_ids[0]))
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        self.update_node_interfaces(node_ids[0])
        cmd = ('fuel --env-id={0} node --provision --node={1} --json'.format(
            cluster_id, node_ids[0]))
        task = self.ssh_manager.execute_on_remote(admin_ip,
                                                  cmd,
                                                  jsonify=True)['stdout_json']
        self.assert_cli_task_success(task, timeout=30 * 60)
        self.show_step(7)
        # Add and provision 2 compute+cinder
        logger.info("Add to the cluster and start provisioning two "
                    "compute+cinder nodes [{0},{1}]".format(node_ids[1],
                                                            node_ids[2]))
        cmd = ('fuel --env-id={0} node set --node {1},{2} \
        --role=compute,cinder'.format(cluster_id, node_ids[1], node_ids[2]))
        self.ssh_manager.execute_on_remote(admin_ip, cmd)
        for node_id in (node_ids[1], node_ids[2]):
            self.update_node_interfaces(node_id)
        cmd = ('fuel --env-id={0} node --provision \
        --node={1},{2} --json'.format(cluster_id, node_ids[1], node_ids[2]))
        task = self.ssh_manager.execute_on_remote(admin_ip,
                                                  cmd,
                                                  jsonify=True)['stdout_json']
        self.assert_cli_task_success(task, timeout=10 * 60)
        self.show_step(8)
        # Deploy the controller node
        cmd = ('fuel --env-id={0} node --deploy --node {1} --json'.format(
            cluster_id, node_ids[0]))
        task = self.ssh_manager.execute_on_remote(admin_ip,
                                                  cmd,
                                                  jsonify=True)['stdout_json']
        self.assert_cli_task_success(task, timeout=60 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)

        self.show_step(9)
        # Deploy the compute nodes
        cmd = ('fuel --env-id={0} node --deploy --node {1},{2} --json'.format(
            cluster_id, node_ids[1], node_ids[2]))
        task = self.ssh_manager.execute_on_remote(admin_ip,
                                                  cmd,
                                                  jsonify=True)['stdout_json']

        self.wait_cli_task_status(task=task, status='running')
        # Fuel 9.1 is async, so we should wait for real task start
        network_settings = self.get_networks(cluster_id)

        self.assert_cli_task_success(task, timeout=30 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)
        # Verify networks
        self.show_step(10)
        network_configuration = self.get_net_config_cli()
        assert_equal(network_settings,
                     network_configuration,
                     message='Network settings are not equal before'
                             ' and after deploy')
        self.show_step(11)
        self.fuel_web.verify_network(cluster_id)
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            cluster_id, ['controller'])
        # Get controller ip address
        controller_node = controller_nodes[0]['ip']
        # Get endpoint list
        endpoint_list = self.get_endpoints(controller_node)
        logger.info(endpoint_list)
        # Check protocol and domain names for endpoints
        self.show_step(12)
        self.show_step(13)
        for endpoint in endpoint_list:
            logger.debug(("Endpoint {0} use protocol {1}\
            and have domain name {2}".format(endpoint['service_name'],
                                             endpoint['protocol'],
                                             endpoint['domain'])))
            assert_equal(endpoint['protocol'], "https",
                         message=("Endpoint {0} don't use https.".format(
                             endpoint['service_name'])))
            assert_equal(endpoint['domain'], SSL_CN, message=(
                "{0} domain name not equal {1}.".format(
                    endpoint['service_name'], SSL_CN)))
        self.show_step(14)
        current_ssl_cn = self.get_current_ssl_cn(controller_node)
        logger.info(("CN before cluster deploy {0} \
        and after deploy {1}".format(SSL_CN, current_ssl_cn)))
        assert_equal(SSL_CN, current_ssl_cn, message="SSL CNs are not equal")
        self.show_step(15)
        with open(PATH_TO_PEM) as pem_file:
            old_ssl_keypair = pem_file.read().strip()
            current_ssl_keypair = self.get_current_ssl_keypair(controller_node)
            logger.info(
                "SSL keypair before cluster deploy:\n"
                "{0}\n"
                "and after deploy:\n"
                "{1}".format(old_ssl_keypair, current_ssl_keypair)
            )
            assert_equal(old_ssl_keypair, current_ssl_keypair,
                         message="SSL keypairs are not equal")
        self.show_step(16)
        actual_floating_ranges = self.hiera_floating_ranges(controller_node)
        logger.info("Current floating ranges: {0}".format(
            actual_floating_ranges))
        assert_equal(actual_floating_ranges, new_floating_range,
                     message="Floating ranges are not equal")
        # Get deployment task id
        task_id = self.get_first_task_id_by_name(cluster_id, 'deployment')
        self.show_step(17)
        # Get deployment info
        self.get_deployment_info_cli(task_id)
        self.show_step(18)
        # Get cluster settings after deploy
        cluster_config = self.get_cluster_config_cli(task_id)
        self.show_step(19)
        # Compare cluster settings
        assert_equal(cluster_settings,
                     cluster_config,
                     message='Cluster settings are not equal before'
                             ' and after deploy')
        self.show_step(20)
        # Run OSTF
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])
        self.env.make_snapshot("cli_selected_nodes_deploy", is_make=True)

    @test(depends_on_groups=['cli_selected_nodes_deploy'],
          groups=["cli_node_deletion_check"])
    @log_snapshot_after_test
    def cli_node_deletion_check(self):
        """Destroy node and remove it from Nailgun using Fuel CLI

        Scenario:
            1. Revert snapshot 'cli_selected_nodes_deploy'
            2. Check 'slave-03' is present
            3. Destroy 'slave-03'
            4. Wait until 'slave-03' become offline
            5. Delete offline 'slave-03' from db
            6. Check presence of 'slave-03'

        Duration 30m

        """
        self.env.revert_snapshot("cli_selected_nodes_deploy")

        node = self.env.d_env.nodes().slaves[2]
        node_id = self.fuel_web.get_nailgun_node_by_devops_node(node)['id']

        assert_true(check_cobbler_node_exists(self.ssh_manager.admin_ip,
                                              node_id),
                    "node-{0} is not found".format(node_id))
        node.destroy()
        self.fuel_web.wait_node_is_offline(node, timeout=60 * 6)

        admin_ip = self.ssh_manager.admin_ip
        cmd = 'fuel node --node-id {0} --delete-from-db'.format(node_id)
        res = self.ssh_manager.execute_on_remote(admin_ip, cmd)
        assert_true(
            res['exit_code'] == 0,
            "Offline node-{0} was not"
            "deleted from database".format(node_id))

        cmd = "fuel node | awk '{{print $1}}' | grep -w '{0}'".format(node_id)

        wait(
            lambda: not self.ssh_manager.execute_on_remote(
                admin_ip,
                cmd,
                raise_on_assert=False)['exit_code'] == 0, timeout=60 * 4,
            timeout_msg='After deletion node-{0} is found in fuel list'
                        ''.format(node_id))

        is_cobbler_node_exists = check_cobbler_node_exists(
            self.ssh_manager.admin_ip, node_id)

        assert_false(is_cobbler_node_exists,
                     "After deletion node-{0} is found in cobbler list".
                     format(node_id))
        cmd = "fuel env | tail -n 1 | awk {'print $1'}"
        cluster_id = self.ssh_manager.execute_on_remote(
            admin_ip, cmd)['stdout_str']

        self.fuel_web.verify_network(cluster_id)

        self.fuel_web.run_ostf(
            cluster_id=cluster_id, test_sets=['ha', 'smoke', 'sanity'])

    @test(depends_on_groups=['cli_selected_nodes_deploy'],
          groups=["cli_cluster_deletion"])
    @log_snapshot_after_test
    def cli_cluster_deletion(self):
        """Delete a cluster using Fuel CLI

        Scenario:
            1. Revert snapshot 'cli_selected_nodes_deploy'
            2. Delete cluster via cli
            3. Check cluster absence in the list

        Duration 25m

        """
        self.env.revert_snapshot("cli_selected_nodes_deploy")

        cluster_id = self.fuel_web.get_last_created_cluster()

        nodes = self.fuel_web.client.list_cluster_nodes(cluster_id)
        online_nodes = [node for node in nodes if node['online']]
        if nodes != online_nodes:
            logger.error(
                'Some slaves do not become online after revert!!'
                ' Expected {0} Actual {1}'.format(nodes, online_nodes))

        self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd='fuel --env {0} env delete --force'.format(cluster_id)
        )

        wait(lambda:
             self.ssh_manager.execute_on_remote(
                 ip=self.ssh_manager.admin_ip,
                 cmd="fuel env |  awk '{print $1}' |  tail -n 1 | "
                     "grep '^.$'",
                 raise_on_assert=False)['exit_code'] == 1, timeout=60 * 10,
             timeout_msg='cluster {0} was not deleted'.format(cluster_id))

        assert_false(
            check_cluster_presence(cluster_id, self.env.postgres_actions),
            "cluster {0} is found".format(cluster_id))

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["cli_selected_nodes_deploy_huge"])
    @log_snapshot_after_test
    def cli_selected_nodes_deploy_huge(self):
        """Create and deploy huge environment using Fuel CLI

        Scenario:
            1. Revert snapshot "ready_with_9_slaves"
            2. Create a cluster
            3. Set replication factor 2
            4. Set ceph usage for images, cinder for volumes
            5. Get cluster settings before deploy
            6. Provision a controller node using Fuel CLI
            7. Provision one compute node using Fuel CLI
            8. Provision one cinder node using Fuel CLI
            9. Provision two ceph-osd nodes using Fuel CLI
            10. Provision one base-os node using Fuel CLI
            11. Leave 2 nodes in discover state
            12. Deploy the ceph-osd and controller nodes using Fuel CLI
            13. Deploy the compute node using Fuel CLI
            14. Deploy the cinder node using Fuel CLI
            15. Deploy the base-os node using Fuel CLI
            16. Check that nodes in discover state stay in it
            17. Get deployment-info
            18. Get cluster settings after deployment task
            19. Compare cluster settings after deploy and before deploy
            20. Run OSTF

        Duration 60m
        """
        self.show_step(1)
        self.env.revert_snapshot("ready_with_9_slaves")
        data = {
            'volumes_ceph': False,
            'images_ceph': True,
            'volumes_lvm': True,
            'objects_ceph': True,
            'osd_pool_size': '2',
            'net_provider': 'neutron',
            'net_segment_type': NEUTRON_SEGMENT['vlan'],
            'assign_to_all_nodes': True,
            'tenant': 'huge_cli',
            'user': 'huge_cli',
            'password': 'huge_cli'
        }
        self.show_step(2)
        self.show_step(3)
        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            settings=data
        )

        # Get nodes ids
        node_ids = [node['id'] for node in self.fuel_web.client.list_nodes()]
        admin_ip = self.ssh_manager.admin_ip
        self.show_step(5)
        cluster_settings = self.download_settings(cluster_id)
        # Add and provision a controller node node_ids[0]
        self.show_step(6, 'on node {0}'.format(node_ids[0]))

        cmd = (
            'fuel --env-id={0} node set --node {1} --role=controller'
            ''.format(cluster_id, node_ids[0]))
        self.ssh_manager.check_call(admin_ip, cmd)
        self.update_node_interfaces(node_ids[0])
        cmd = (
            'fuel --env-id={0} node --provision --node={1} --json'
            ''.format(cluster_id, node_ids[0]))
        task = self.ssh_manager.check_call(
            admin_ip,
            cmd).stdout_json
        self.assert_cli_task_success(task, timeout=80 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)

        assert_equal(
            1,
            len(self.fuel_web.get_nailgun_node_by_status('provisioned')),
            'Some unexpected nodes were provisioned,'
            ' current list of provisioned '
            'nodes {}'.format(
                self.fuel_web.get_nailgun_node_by_status('provisioned')))

        # Add and provision 1 compute node_ids[1]
        self.show_step(7, details='using node id {}'.format(node_ids[1]))
        cmd = (
            'fuel --env-id={0} node set --node {1} --role=compute'
            ''.format(cluster_id, node_ids[1]))
        self.ssh_manager.check_call(admin_ip, cmd)
        self.update_node_interfaces(node_ids[1])

        cmd = (
            'fuel --env-id={0} node --provision --node={1} --json'
            ''.format(cluster_id, node_ids[1]))
        task = self.ssh_manager.check_call(admin_ip, cmd,).stdout_json
        self.assert_cli_task_success(task, timeout=10 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)

        assert_equal(
            2,
            len(self.fuel_web.get_nailgun_node_by_status('provisioned')),
            'Some unexpected nodes were provisioned,'
            ' current list of provisioned '
            'nodes {}'.format(
                self.fuel_web.get_nailgun_node_by_status('provisioned')))

        # Add and provision 1 cinder node_ids[2]
        self.show_step(8, details='using node id {}'.format(node_ids[2]))
        cmd = (
            'fuel --env-id={0} node set --node {1} --role=cinder'
            ''.format(cluster_id, node_ids[2]))
        self.ssh_manager.check_call(admin_ip, cmd)
        self.update_node_interfaces(node_ids[2])

        cmd = (
            'fuel --env-id={0} node --provision  --node={1} --json'
            ''.format(cluster_id, node_ids[2]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=10 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)

        assert_equal(
            3,
            len(self.fuel_web.get_nailgun_node_by_status('provisioned')),
            'Some unexpected nodes were provisioned,'
            ' current list of provisioned '
            'nodes {}'.format(
                self.fuel_web.get_nailgun_node_by_status('provisioned')))

        # Add and provision 2 ceph-osd node_ids[4], node_ids[5]
        self.show_step(9, details='using node ids {0}, {1}'.format(
            node_ids[4], node_ids[5]))
        cmd = (
            'fuel --env-id={0} node set --node {1},{2} '
            '--role=ceph-osd'.format(cluster_id, node_ids[4], node_ids[5]))
        self.ssh_manager.check_call(admin_ip, cmd)
        for node_id in (node_ids[4], node_ids[5]):
            self.update_node_interfaces(node_id)

        cmd = ('fuel '
               '--env-id={0} node --provision '
               '--node {1},{2} '
               '--json'.format(cluster_id, node_ids[4], node_ids[5]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=10 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)

        assert_equal(
            6,
            len(self.fuel_web.get_nailgun_node_by_status('provisioned')),
            'Some unexpected nodes were provisioned,'
            ' current list of provisioned '
            'nodes {}'.format(
                self.fuel_web.get_nailgun_node_by_status('provisioned')))
        # Add and provision 1 base-os node node_ids[6]
        self.show_step(10, details='using node ids {0}'.format(node_ids[6]))
        cmd = ('fuel --env-id={0} node set --node {1} '
               '--role=base-os'.format(cluster_id, node_ids[6]))
        self.ssh_manager.check_call(admin_ip, cmd)
        self.update_node_interfaces(node_ids[6])

        cmd = ('fuel --env-id={0} node --provision '
               '--node={1} --json'.format(cluster_id, node_ids[6]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=10 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)

        assert_equal(
            7,
            len(self.fuel_web.get_nailgun_node_by_status('provisioned')),
            'Some unexpected nodes were provisioned,'
            ' current list of provisioned '
            'nodes {}'.format(
                self.fuel_web.get_nailgun_node_by_status('provisioned')))

        self.show_step(11)
        # Add 2 compute but do not deploy node_ids[7] node_ids[8]
        cmd = ('fuel --env-id={0} node set --node {1},{2} '
               '--role=compute'.format(cluster_id, node_ids[7], node_ids[8]))
        self.ssh_manager.check_call(admin_ip, cmd)

        node_discover = self.fuel_web.get_nailgun_node_by_status('discover')
        assert_equal(
            2,
            len(node_discover),
            'Some unexpected nodes were provisioned,'
            ' current list of provisioned '
            'nodes {}'.format(
                [node['id'] for node in node_discover]))

        for node in node_discover:
            assert_true(node['pending_addition'])

        # Deploy ceph-osd and controller nodes
        # node_ids[0], node_ids[4] node_ids[5]
        self.show_step(12, details='for node ids {0}, {1}, {2}'.format(
            node_ids[0], node_ids[4], node_ids[5]))
        cmd = (
            'fuel --env-id={0} node --deploy --node {1},{2},{3} --json'.format(
                cluster_id, node_ids[0], node_ids[4], node_ids[5]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=80 * 60)

        self.assert_all_tasks_completed(cluster_id=cluster_id)
        self.show_step(13, details='for node id {}'.format(node_ids[1]))
        # Deploy the compute node node_ids[1]
        cmd = ('fuel --env-id={0} node --deploy --node {1} --json'.format(
            cluster_id, node_ids[1]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=30 * 60)
        self.assert_all_tasks_completed(cluster_id=cluster_id)

        # Deploy the cinder node node_ids[2]
        self.show_step(14, details='for node id {}'.format(node_ids[2]))
        cmd = ('fuel --env-id={0} node --deploy --node {1} --json'.format(
            cluster_id, node_ids[2]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=60 * 60)
        self.assert_all_tasks_completed(cluster_id=cluster_id)

        # Deploy the base-os node node_ids[6]
        self.show_step(15, details='for node id {}'.format(node_ids[6]))
        cmd = ('fuel --env-id={0} node --deploy --node {1} --json'.format(
            cluster_id, node_ids[6]))
        task = self.ssh_manager.check_call(admin_ip, cmd).stdout_json
        self.assert_cli_task_success(task, timeout=60 * 60)
        self.assert_all_tasks_completed(cluster_id=cluster_id)

        self.show_step(16)
        self.fuel_web.verify_network(cluster_id)
        node_discover_after_deploy = self.fuel_web.get_nailgun_node_by_status(
            'discover')
        assert_equal(
            2,
            len(node_discover_after_deploy),
            'Some unexpected nodes were deployed,'
            ' current list of discover nodes {}'.format(
                [node['id'] for node in node_discover_after_deploy]))

        for node in node_discover_after_deploy:
            assert_true(node['pending_addition'])
        self.show_step(17)
        task_id = self.get_first_task_id_by_name(cluster_id, 'deployment')
        self.get_deployment_info_cli(task_id)
        self.show_step(18)
        cluster_config = self.get_cluster_config_cli(task_id)
        self.show_step(19)
        assert_equal(cluster_settings,
                     cluster_config,
                     message='Cluster settings are not equal before'
                             ' and after deploy')
        # Run OSTF
        self.show_step(20)
        self.fuel_web.run_ostf(cluster_id=cluster_id,
                               test_sets=['ha', 'smoke', 'sanity'])
        self.env.make_snapshot("cli_selected_nodes_deploy_huge")
