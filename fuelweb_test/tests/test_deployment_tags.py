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

import os
import yaml

from proboscis import asserts
from proboscis import test
import pprint

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["deployment_tags"])
class DeploymentTags(TestBasic):
    """DeploymentTags."""  # TODO documentation

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["create_get_update_delete_tags"])
    @log_snapshot_after_test
    def create_get_update_delete_tags(self):
        """Basic CRUD test for new Tag entity

        Scenario:
            1. Get tags list
            2. Create new release tag
            3. Get tags list and check new release tag
            4. Modify release tag and check new values
            5. Delete release tag
            6. Get tags list and check absence of the new release tag

        Duration xxx m
        Snapshot: create_get_update_delete_tags
        """
        self.show_step(1)
        tags_list = self.fuel_web.client.list_tags()
        logger.info("Current tags list: {}".format(tags_list))

        self.show_step(2)
        releases = self.fuel_web.client.get_releases()
        logger.info("Available releases: {}".format(releases))

        new_tag = self.fuel_web.client.create_tag(
            tag="NewTag",
            owner_id=releases[0]["id"],
            owner_type="release")
        logger.info("New tag created: {}".format(new_tag))

        self.show_step(3)
        tags_ids = [tag["id"] for tag in tags_list]
        tags_ids_diff = [tag["id"] for tag in self.fuel_web.client.list_tags()
                         if tag["id"] not in tags_ids]

        asserts.assert_true(new_tag["id"] in tags_ids_diff,
                            "New tag {0} is not in tags list: {1}"
                            .format(new_tag, self.fuel_web.client.list_tags()))

        self.show_step(4)
        cluster_id = self.fuel_web.create_cluster(name=self.__class__.__name__)
        self.fuel_web.client.update_tag(
            tag_id=new_tag["id"],
            tag="BrandNewTag",
            owner_id=cluster_id,
            owner_type="cluster"
        )
        new_tag = self.fuel_web.client.get_tag(new_tag["id"])
        logger.info("New tag values: {}".format(new_tag))
        asserts.assert_equal(new_tag["tag"], "BrandNewTag")
        asserts.assert_equal(new_tag["owner_id"], cluster_id)
        asserts.assert_equal(new_tag["owner_type"], "cluster")

        self.show_step(5)
        self.fuel_web.client.delete_tag(new_tag["id"])

        self.show_step(6)
        tags_ids_diff = [tag["id"] for tag in self.fuel_web.client.list_tags()
                         if tag["id"] not in tags_ids]
        asserts.assert_true(new_tag["id"] not in tags_ids_diff,
                            "New tag {0} is not in tags list: {1}"
                            .format(new_tag, self.fuel_web.client.list_tags()))

    @test(depends_on=[SetupEnvironment.prepare_slaves_5],
          groups=["check_tags_assignment"])
    @log_snapshot_after_test
    def check_tags_assignment(self):
        """Basic tags assignment operations

        Scenario:
            1. Create two clusters
            2. Assign controller and compute nodes to the first cluster
            3. Check nodes tags
            4. Create new cluster tag for the first cluster and assign it
            5. Add node to the second cluster and assign custom tag

        Duration xxx m
        Snapshot: check_tags_assignment
        """

        self.show_step(1)
        first_cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__ + "_First")
        second_cluster_id = self.fuel_web.create_cluster(
            name=self.__class__.__name__ + "_Second")

        self.show_step(2)
        self.fuel_web.update_nodes(
            first_cluster_id,
            {
                'slave-01': ['controller'],
                'slave-02': ['compute'],
                'slave-03': ['compute']
            }
        )

        self.show_step(3)
        for node_name in ["slave-01"]:
            node = self.fuel_web.get_nailgun_node_by_name(node_name)
            logger.info("{0} node attributes: {1}"
                        .format(pprint.pformat(node)))

        self.show_step(4)
        tag = self.fuel_web.client.create_tag(
            tag="cluster_one_tag",
            owner_id=first_cluster_id,
            owner_type="cluster"
        )

        slave_01 = self.fuel_web.get_nailgun_node_by_name("slave-01")
        slave_01["tags"].append(tag["tag"])
        self.fuel_web.client.update_node(slave_01["id"], slave_01)

        logger.info(
            "{0} node attributes: {1}".format(pprint.pformat(
                self.fuel_web.get_nailgun_node_by_name("slave-01"))))

        self.show_step(5)
        self.fuel_web.update_nodes(
            second_cluster_id,
            {
                'slave-04': ['controller'],
                'slave-05': ['compute']
            }
        )

        slave_04 = self.fuel_web.get_nailgun_node_by_name("slave-04")
        slave_04["tags"].append(tag["tag"])
        self.fuel_web.client.update_node(slave_04["id"], slave_01)
