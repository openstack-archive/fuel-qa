#    Copyright 2017 Mirantis, Inc.
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

from copy import deepcopy
from keystoneauth1.exceptions import HttpError

from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true
from proboscis import test

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["test_tags"])
class TagsCRUD(TestBasic):
    """TagsCRUD."""  # TODO documentation

    def __init__(self):
        super(TagsCRUD, self).__init__()
        self._cluster_id = None
        self.nailgun = self.fuel_web.client

    @property
    def cluster_id(self):
        return self._cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        self._cluster_id = cluster_id

    def create_cluster(self, data=None):
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__,
            mode=settings.DEPLOYMENT_MODE,
            settings=data)

    def update_nodes(self, nodes=None):
        self.fuel_web.update_nodes(
            self.cluster_id,
            nodes
        )

    def deploy_cluster(self, check_services=True):
        self.fuel_web.deploy_cluster_wait(self.cluster_id,
                                          check_services=check_services)

    def run_ostf(self, should_fail=0, failed_tests=None):
        logger.info('Should fail = {}, failed tests: {}'.format(
            should_fail, failed_tests))
        self.fuel_web.run_ostf(cluster_id=self.cluster_id,
                               should_fail=should_fail,
                               failed_test_name=failed_tests)

    def verify_networks(self):
        self.fuel_web.verify_network(self.cluster_id)

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["tags_crud"])
    @log_snapshot_after_test
    def tags_crud(self):
        """Base CRUD for tag entity

        Scenario:
            1. Create a new tag for a release
            2. Create an existing tag for release
            3. Get the newly created tag for release
            4. Update the newly created tag for release
            5. Get all the tags from release
            6. Delete the newly created tag for release
            7. Delete already deleted tag for release
            8. Create a new tag for a cluster
            9. Create an existing tag for cluster
            10. Get the newly created tag for cluster
            11. Update the newly created tag for cluster
            12. Get all the tags from release for cluster
            13. Delete the newly created tag for cluster
            14. Delete already deleted tag for cluster

        Duration 3m
        Snapshot tags_crud

        """
        self.env.revert_snapshot("ready_with_1_slaves")
        rel_id = self.nailgun.get_release_id()
        self.create_cluster()
        self.current_log_step = 1
        for parent_id, parent, tag_name in \
                zip([rel_id, self.cluster_id], ['releases', 'clusters'],
                    ['new_rel_tag', 'new_cls_tag']):

            tag_data = {"meta": {"has_primary": False}, "name": tag_name}

            # step 1 or 8
            self.show_step(self.current_log_step, initialize=True)
            self.nailgun.add_new_tag(parent_id, tag_data, parent)
            # step 2 or 9
            self.show_step(self.next_step)
            exp_code = 409
            try:
                self.nailgun.add_new_tag(parent_id, tag_data, parent)
            except HttpError as exc:
                if exc.http_status != exp_code:
                    logger.error(
                        'Raised:   {exc!s},\n'
                        'Expected: {exp} with code={code}'.format(
                            exc=exc,
                            exp=HttpError,
                            code=exp_code))

            # step 3 or 10
            self.show_step(self.next_step)
            new_tag_data = self.nailgun.get_tag_data(
                parent_id, tag_name, parent)
            err_msg = \
                'Tags current data: "{new_data}" is not equal to the data ' \
                'on creation: "{old_data}"'.format(new_data=new_tag_data,
                                                   old_data=tag_data)
            assert_equal(new_tag_data, tag_data, err_msg)

            # step 4 or 11
            self.show_step(self.next_step)
            tag_data['meta']['has_primary'] = True
            new_tag_data = self.nailgun.update_tag_data(
                parent_id, tag_name, tag_data, parent)
            assert_equal(new_tag_data, tag_data, err_msg)

            # step 5 or 12
            self.show_step(self.next_step)
            all_tags = self.nailgun.get_all_tags(parent_id, parent)
            err_msg = \
                'Newly created tag {tag_name} is not in the list of tags ' \
                '{all_tags}'.format(tag_name=tag_name, all_tags=all_tags)
            assert_true([tag for tag in all_tags if tag == tag_data] != [],
                        err_msg)

            # step 6 or 13
            self.show_step(self.next_step)
            self.nailgun.del_tag(parent_id, tag_name, parent)
            all_tags = self.nailgun.get_all_tags(parent_id, parent)
            err_msg = \
                'Deleted tag {tag_name} is still presented in the list of ' \
                'tags {all_tags}'.format(tag_name=tag_name, all_tags=all_tags)

            assert_true([tag for tag in all_tags if tag == tag_data] == [],
                        err_msg)

            # step 7 or 14
            self.show_step(self.next_step)
            exp_code = 404
            try:
                self.nailgun.del_tag(parent_id, tag_name, parent)
            except HttpError as exc:
                if exc.http_status != exp_code:
                    logger.error(
                        'Raised:   {exc!s},\n'
                        'Expected: {exp} with code={code}'.format(
                            exc=exc,
                            exp=HttpError,
                            code=exp_code))

            self.current_log_step += 1

        self.env.make_snapshot("tags_crud")

    @test(depends_on=[SetupEnvironment.prepare_slaves_1],
          groups=["roles_to_tags"])
    @log_snapshot_after_test
    def roles_to_tags(self):
        """Assign role and check tags assignment

        Scenario:
            1. Create a new tag
            2. Create a new role for a release
            3. Repeat the Step 2 with non-existing tag name
            4. Create a cluster
            5. Deploy the cluster
            6. Run OSTF

        Duration 30m
        Snapshot roles_to_tags

        """
        role_data = {
            "meta": {
                "group": "base",
                "description": "New controller role",
                "weight": 10,
                "tags": ["controller", "database", "keystone", "neutron",
                         "new_tag"],
                "update_required": ["compute", "cinder"],
                "public_ip_required": True,
                "conflicts": ["compute"],
                "public_for_dvr_required": True,
                "name": "Controller_new"
            },
            "name": "controller_new",
            "volumes_roles_mapping": [{
                "id": "os",
                "allocate_size": "min"
            }, {
                "id": "logs",
                "allocate_size": "min"
            }, {
                "id": "image",
                "allocate_size": "all"
            }, {
                "id": "mysql",
                "allocate_size": "min"
            }, {
                "id": "horizon",
                "allocate_size": "min"
            }]
        }
        self.env.revert_snapshot("ready_with_1_slaves")
        rel_id = self.nailgun.get_release_id()
        self.show_step(1, initialize=True)
        tag_data = {"meta": {"has_primary": False}, "name": "new_tag"}
        self.nailgun.add_new_tag(rel_id, tag_data)
        self.show_step(2)
        self.nailgun.add_new_role(rel_id, role_data)
        self.show_step(3)
        invalid_role_data = deepcopy(role_data)
        invalid_role_data['meta']['tags'].append("non_existing_tag")
        exp_code = 400
        try:
            self.nailgun.add_new_role(rel_id, invalid_role_data)
        except HttpError as exc:
            if exc.http_status != exp_code:
                logger.error(
                    'Raised:   {exc!s},\n'
                    'Expected: {exp} with code={code}'.format(
                        exc=exc,
                        exp=HttpError,
                        code=exp_code))
        new_role_data = self.nailgun.get_role_data(rel_id, 'controller_new')
        err_msg = 'Roles downloaded: {} and uploaded: {} are not equal'.format(
            new_role_data, role_data)
        assert_equal(new_role_data, role_data, err_msg)
        self.show_step(4)
        self.create_cluster()
        nodes = {'slave-01': ['controller_new']}
        self.update_nodes(nodes)
        self.show_step(5)
        self.deploy_cluster()
        self.show_step(6)
        self.run_ostf()

        self.env.make_snapshot("roles_to_tags")

    @test(depends_on=[SetupEnvironment.prepare_slaves_9],
          groups=["separate_rabbit_via_role"])
    @log_snapshot_after_test
    def separate_rabbit_via_role(self):
        """Deploy cluster with 3 separate via tag rabbitmq roles

        Scenario:
            1. Remove rabbit tag from controller role
            2. Create new role rabbitmq
            3. Create cluster
            4. Add 3 nodes with controller role
            5. Add 3 nodes with newly created rabbit role
            6. Add 1 compute and cinder
            7. Verify networks
            8. Deploy the cluster
            9. Verify networks
            10. Run OSTF
            11. Compare deployed nodes with tag rabbitmq

        Duration 120m
        Snapshot separate_rabbit_via_role
        """

        rabbitmq_role = {
            "meta": {
                "group": "base",
                "description": "Separated rabbitmq from controller role",
                "weight": 100,
                "tags": ["rabbitmq"],
                "update_required": ["controller", "standalone-rabbitmq"],
                "conflicts": ["controller", "compute"],
                "name": "Standalone-Rabbitmq"
            },
            "name": "standalone-rabbitmq",
            "volumes_roles_mapping": [{
                "id": "os",
                "allocate_size": "min"
            }]
        }
        self.env.revert_snapshot("ready_with_9_slaves")
        rel_id = self.nailgun.get_release_id()

        self.show_step(1)
        controller_role = self.nailgun.get_role_data(rel_id, 'controller')
        controller_role['meta']['tags'].remove('rabbitmq')
        self.nailgun.update_role_data(rel_id, 'controller', controller_role)

        self.show_step(2)
        self.nailgun.add_new_role(rel_id, rabbitmq_role)

        self.show_step(3)
        data = {
            'tenant': 'separaterabbit',
            'user': 'separaterabbit',
            'password': 'separaterabbit',
            "net_provider": 'neutron',
            "net_segment_type": settings.NEUTRON_SEGMENT['vlan'],
        }

        self.create_cluster(data)
        self.show_step(4)
        self.show_step(5)
        self.show_step(6)
        nodes = {
            'slave-01': ['controller'],
            'slave-02': ['controller'],
            'slave-03': ['controller'],
            'slave-04': ['standalone-rabbitmq'],
            'slave-05': ['standalone-rabbitmq'],
            'slave-06': ['standalone-rabbitmq'],
            'slave-07': ['compute'],
            'slave-08': ['cinder']
        }
        self.update_nodes(nodes)

        self.show_step(7)
        self.verify_networks()
        self.show_step(8)
        self.deploy_cluster(check_services=False)
        self.show_step(9)
        self.verify_networks()
        self.show_step(10)
        self.run_ostf(should_fail=1, failed_tests=['Check pacemaker status'])
        self.show_step(11)
        rabbitmq_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ['standalone-rabbitmq'])
        rabbitmq_ctl_nodes = self.fuel_web.get_rabbit_running_nodes('slave-04')
        err_msg = \
            'Nodes with tag rabbitmq: {} are not equal deployed nodes with ' \
            'role standalone-rabbitmq: {}'.format(rabbitmq_nodes,
                                                  rabbitmq_ctl_nodes)
        assert_equal(rabbitmq_nodes, rabbitmq_ctl_nodes, err_msg)
        self.env.make_snapshot("separate_rabbit_via_role")
