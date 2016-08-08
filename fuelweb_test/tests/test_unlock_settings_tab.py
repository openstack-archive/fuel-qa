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

from proboscis import SkipTest
from proboscis import test
from keystoneauth1.exceptions import HttpError
# pylint: disable=redefined-builtin
from six.moves import xrange
# pylint: enable=redefined-builtin

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import log_snapshot_after_test
from fuelweb_test.helpers.utils import SettingsChanger
from fuelweb_test.tests.base_test_case import SetupEnvironment
from fuelweb_test.tests.base_test_case import TestBasic


@test(groups=["unlock_settings_tab"])
class UnlockSettingsTab(TestBasic):
    """UnlockSettingsTab."""  # TODO documentation

    def __init__(self):
        super(UnlockSettingsTab, self).__init__()
        self._cluster_id = None
        self._cluster_name = None

    @property
    def cluster_id(self):
        return self._cluster_id

    @cluster_id.setter
    def cluster_id(self, cluster_id):
        self._cluster_id = cluster_id

    @property
    def cluster_name(self):
        return self._cluster_name

    @cluster_name.setter
    def cluster_name(self, cluster_name):
        self._cluster_name = cluster_name

    @staticmethod
    def load_config_from_file(path_to_conf=None):
        if not path_to_conf:
            logger.error("Please, specify file to load config from")
            raise SkipTest("File with config is not specified. "
                           "Aborting the test")
        with open(path_to_conf, 'r') as f:
            try:
                config = yaml.load(f)
                return config
            except ValueError:
                logger.error("Check config file for consistency")
                raise

    def revert_snapshot(self, nodes_count):
        """
        :param nodes_count: number of nodes
        :return: nothing, but reverts snapshot
        """
        if nodes_count == 1:
            num = '1'
        elif nodes_count <= 3:
            num = '3'
        elif nodes_count <= 5:
            num = '5'
        else:
            num = '9'
        self.env.revert_snapshot('ready_with_{}_slaves'.format(num))

    @staticmethod
    def check_config_for_ceph(attrs):
        storage = attrs['editable']['storage']
        options_to_check = ['volumes_ceph', 'objects_ceph', 'images_ceph',
                            'ephemeral_ceph']
        for option in options_to_check:
            if storage[option]['value']:
                pool_size = storage['osd_pool_size']['value']
                return int(pool_size)
        return None

    @staticmethod
    def get_existed_ceph_nodes_count(conf):
        nodes = conf['nodes']
        return len([node for node in nodes if 'ceph-osd' in nodes[node]])

    def add_ceph_nodes(self, count, ceph_nodes_count):
        self.env.bootstrap_nodes(
            self.env.d_env.nodes().slaves[count:count + ceph_nodes_count],
            skip_timesync=True)
        nodes = {'slave-0{}'.format(i): ['ceph-osd']
                 for i in xrange(count + 1, count + ceph_nodes_count + 1)}
        self.fuel_web.update_nodes(self.cluster_id, nodes)

    def load_config(self, file_name):
        conf_path = os.path.dirname(os.path.abspath(__file__))
        cluster_conf = \
            self.load_config_from_file(os.path.join(conf_path, file_name))
        return cluster_conf

    def create_cluster(self, conf):
        self.cluster_name = '_'.join([self.__class__.__name__, conf['name']])
        cluster_settings = {
            "net_provider": conf['network']['net_provider'],
            "net_segment_type": conf['network']['net_segment_type']}
        if conf.get('settings'):
            cluster_settings.update(conf['settings'])

        self.cluster_id = self.fuel_web.create_cluster(
            name=self.cluster_name,
            mode=settings.DEPLOYMENT_MODE,
            settings=cluster_settings)

    def update_nodes(self, conf):
        self.fuel_web.update_nodes(
            self.cluster_id,
            conf['nodes'])

    def deploy_cluster(self):
        try:
            self.fuel_web.deploy_cluster_wait(self.cluster_id)
        except AssertionError:
            self.env.make_snapshot(
                "error_" + self.cluster_name, is_make=True)
            return False
        else:
            return True

    def get_cluster_attributes(self):
        return self.fuel_web.client.get_cluster_attributes(self.cluster_id)

    def update_cluster_attributes(self, new_attrs):
        try:
            self.fuel_web.client.update_cluster_attributes(
                self.cluster_id, new_attrs)
        except HttpError:
            logger.info(
                "Failed to update cluster attributes, please check logs")
            return False
        else:
            return True

    def run_ostf(self):
        try:
            self.fuel_web.run_ostf(cluster_id=self.cluster_id)
        except AssertionError:
            logger.info("Some OSTF tests are failed. Check logs.")
            self.env.make_snapshot(
                "error_" + self.cluster_name, is_make=True)
            return False
        else:
            return True

    @test(depends_on=[SetupEnvironment.prepare_slaves_1,
                      SetupEnvironment.prepare_slaves_3,
                      SetupEnvironment.prepare_slaves_5,
                      SetupEnvironment.prepare_slaves_9],
          groups=["deploy_with_redeploy_and_modify_settings"])
    @log_snapshot_after_test
    def deploy_with_redeploy_and_modify_settings(self):
        """Deploy iteratively clusters from config, modify settings, redeploy

        Scenario:
            1. Load clusters' configurations from the file
            2. Revert snapshot with appropriate nodes count
            3. Create a cluster from config
            4. Update nodes accordingly to the config
            5. Deploy the cluster
            6. Get cluster attributes
            7. Modify randomly cluster attributes
            8. Add if it's needed ceph nodes
            9. Update cluster attributes with changed one
            10. Redeploy cluster
            11. Run OSTF
            12. Go to the next config

        Duration xxx m
        Snapshot will be made for all failed configurations
        """
        self.show_step(1)
        for conf in self.load_config('cluster_configs.yaml'):
            logger.info(
                "Creating cluster from config with name: {}".format(
                    conf['name']))
            self.show_step(2, initialize=True)
            self.revert_snapshot(len(conf['nodes']))
            self.show_step(3)
            self.create_cluster(conf)
            self.show_step(4)
            self.update_nodes(conf)
            self.show_step(5)
            if not self.deploy_cluster():
                logger.info(
                    "Initial deployment of cluster {} was failed. "
                    "Go to the next config".format(self.cluster_name))
                continue

            self.show_step(6)
            attrs = self.get_cluster_attributes()
            self.show_step(7)
            changer = SettingsChanger(attrs)
            logger.info(
                "The options below will NOT be changed: {}".format(
                    changer.SKIPPED_FIELDS_LIST))
            changer.make_changes(options=None, randomize=30)
            new_attrs = changer.attrs
            self.show_step(8)
            ceph_nodes_count = self.check_config_for_ceph(new_attrs)
            existed_ceph_count = self.get_existed_ceph_nodes_count(conf)
            if ceph_nodes_count > existed_ceph_count:
                count = len(conf['nodes'])
                if count + ceph_nodes_count > settings.NODES_COUNT - 1:
                    logger.info("There are not enough nodes to redeploy with "
                                "ceph nodes pool size. Go to the next config")
                    continue
                self.add_ceph_nodes(count, ceph_nodes_count)

            self.show_step(9)
            if not self.update_cluster_attributes(new_attrs):
                continue

            self.show_step(10)
            if not self.deploy_cluster():
                logger.info(
                    "Redeployment of cluster {} was failed. "
                    "Go to the next config".format(self.cluster_name))
                continue
            else:
                # Run ostf
                self.show_step(11)
                if not self.run_ostf():
                    continue
                logger.info(
                    "Redeployment and OSTF were successfully "
                    "executed for cluster {}".format(self.cluster_name))

            self.show_step(12)
