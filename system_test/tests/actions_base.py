#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
import time

from proboscis import SkipTest
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test.helpers import checkers
from fuelweb_test.helpers.utils import timestat
from fuelweb_test import settings as test_settings

from system_test import logger
from system_test.tests import base_actions_factory
from system_test.helpers.decorators import make_snapshot_if_step_fail
from system_test.helpers.decorators import deferred_decorator
from system_test.helpers.decorators import action


class PrepareBase(base_actions_factory.BaseActionsFactory):
    """Base class with prepare actions

    _action_setup_master - setup master node in environment
    _action_config_release - preconfig releases if it needs
    _action_make_slaves - boot slaves and snapshop environment with
        bootstraped slaves
    _action_revert_slaves - revert environment with bootstraped slaves
    """

    def _start_case(self):
        """Start test case"""
        class_doc = getattr(self, "__doc__", self.__class__.__name__)
        name = class_doc.splitlines()[0]
        class_scenario = class_doc.splitlines()[1:]
        start_case = "[ START {} ]".format(name)
        header = "<<< {:=^142} >>>".format(start_case)
        indent = ' ' * 4
        scenario = '\n'.join(class_scenario)
        logger.info("\n{header}\n\n"
                    "{indent}Configuration: {config}\n"
                    "\n{scenario}".format(
                        header=header,
                        indent=indent,
                        config=self.config_name,
                        scenario=scenario))
        self._start_time = time.time()

    def _finish_case(self):
        """Finish test case"""
        case_time = time.time() - self._start_time
        minutes = int(round(case_time)) / 60
        seconds = int(round(case_time)) % 60
        name = getattr(self, "__doc__",
                       self.__class__.__name__).splitlines()[0]
        finish_case = "[ FINISH {} CASE TOOK {} min {} sec ]".format(
            name,
            minutes,
            seconds)
        footer = "<<< {:=^142} >>>".format(finish_case)
        logger.info("\n{footer}\n".format(footer=footer))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def setup_master(self):
        """Setup master node"""
        self.check_run("empty")
        with timestat("setup_environment", is_uniq=True):
            self.env.setup_environment()

        self.env.make_snapshot("empty", is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def config_release(self):
        """Configuration releases"""
        self.check_run("ready")
        self.env.revert_snapshot("empty", skip_timesync=True)

        self.fuel_web.get_nailgun_version()
        self.fuel_web.change_default_network_settings()

        if (test_settings.REPLACE_DEFAULT_REPOS and
                test_settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE):
            self.fuel_web.replace_default_repos()

        self.env.make_snapshot("ready", is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def make_slaves(self):
        """Bootstrap slave and make snapshot

        Use slaves parameter from case section
        """
        slaves = int(self.full_config['template']['slaves'])
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)
        logger.info("Bootstrap {} nodes".format(slaves))
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:slaves],
                                 skip_timesync=True)
        self.env.make_snapshot(snapshot_name, is_make=True)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def revert_slaves(self):
        """Revert bootstraped nodes

        Skip if snapshot with cluster exists
        """
        self.check_run(self.env_config['name'])
        slaves = int(self.full_config['template']['slaves'])
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        self.env.revert_snapshot(snapshot_name)


class ActionsBase(PrepareBase):
    """Basic actions for acceptance cases

    For chousing action order use actions_order variable, set list of actions
        order

    Actions:
        create_env - create and configure environment
        add_nodes - add nodes to environment
        deploy_cluster - deploy en environment
        network_check - run network check
        health_check - run all ostf tests
        reset_cluster - reset an environment (NotImplemented)
        delete_cluster - delete en environment (NotImplemented)
        stop_deploy - stop deploying of environment (NotImplemented)
    """

    base_group = None
    actions_order = None

    def __init__(self, config=None):
        super(ActionsBase, self).__init__()
        self.full_config = config
        self.env_config = config['template']['cluster-template']
        self.env_settings = config['template']['cluster-template']['settings']
        self.config_name = config['template']['name']
        self.cluster_id = None
        self.assigned_slaves = set()
        self.scale_step = 0

    def _add_node(self, nodes_list):
        """Add nodes to Environment"""
        logger.info("Add nodes to env {}".format(self.cluster_id))
        names = "slave-{:02}"
        slaves = int(self.full_config['template']['slaves'])
        num = iter(xrange(1, slaves + 1))
        nodes = {}
        for new in nodes_list:
            for one in xrange(new['count']):
                name = names.format(next(num))
                while name not in self.assigned_slaves:
                    name = names.format(next(num))

                self.assigned_slaves.add(name)
                nodes[name] = new['roles']
                logger.info("Set roles {} to node {}".format(new['roles'],
                                                             name))
        self.fuel_web.update_nodes(self.cluster_id, nodes)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def create_env(self):
        """Create Fuel Environment

        For configure Environment use environment-config section in config file

        Skip action if we have snapshot with Environment name
        """
        self.check_run(self.env_config['name'])

        logger.info("Create env {}".format(
            self.env_config['name']))
        settings = {
            "murano": self.env_settings['components'].get('murano', False),
            "sahara": self.env_settings['components'].get('sahara', False),
            "ceilometer": self.env_settings['components'].get('ceilometer',
                                                              False),
            "user": self.env_config.get("user", "admin"),
            "password": self.env_config.get("password", "admin"),
            "tenant": self.env_config.get("tenant", "admin"),
            "volumes_lvm": self.env_settings['storages'].get("volume-lvm",
                                                             False),
            "volumes_ceph": self.env_settings['storages'].get("volume-ceph",
                                                              False),
            "images_ceph": self.env_settings['storages'].get("image-ceph",
                                                             False),
            "ephemeral_ceph": self.env_settings['storages'].get(
                "ephemeral-ceph", False),
            "objects_ceph": self.env_settings['storages'].get("rados-ceph",
                                                              False),
            "osd_pool_size": str(self.env_settings['storages'].get(
                "replica-ceph", 2)),
            "net_provider": self.env_config['network'].get('provider',
                                                           'neutron'),
            "net_segment_type": self.env_config['network'].get('segment-type',
                                                               'vlan'),
            "assign_to_all_nodes": self.env_config['network'].get(
                'pubip-to-all',
                False)
        }
        self.cluster_id = self.fuel_web.create_cluster(
            name=self.env_config['name'],
            mode=test_settings.DEPLOYMENT_MODE,
            release_name=self.env_config['release'],
            settings=settings)

        logger.info("Cluster created with ID:{}".format(self.cluster_id))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def add_nodes(self):
        """Add nodes to environment

        Used sub-section nodes in environment-config section

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self._add_node(self.env_config['nodes'])

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def deploy_cluster(self):
        """Deploy environment

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.deploy_cluster_wait(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def network_check(self):
        """Run network checker

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.verify_network(self.cluster_id)

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def health_check(self):
        """Run health checker

        Skip action if cluster doesn't exist
        """
        if self.cluster_id is None:
            raise SkipTest()

        self.fuel_web.run_ostf(
            cluster_id=self.cluster_id,
            should_fail=getattr(self, 'ostf_tests_should_failed', 0))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def save_load_environment(self):
        """Load existen environment from snapshot or save it"""
        env_name = self.env_config['name']
        if self.cluster_id is None:
            logger.info("Revert Environment from "
                        "snapshot({})".format(env_name))
            assert_true(self.env.d_env.has_snapshot(env_name))
            self.env.revert_snapshot(env_name)
            self.cluster_id = self.fuel_web.client.get_cluster_id(env_name)
            logger.info("Cluster with ID:{} reverted".format(self.cluster_id))
        else:
            logger.info("Make snapshot of Environment '{}' ID:{}".format(
                env_name, self.cluster_id))
            self.env.make_snapshot(env_name, is_make=True)
            self.env.resume_environment()

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def check_haproxy(self):
        """HAProxy backend checking"""
        controller_nodes = self.fuel_web.get_nailgun_cluster_nodes_by_roles(
            self.cluster_id, ['controller'])

        for node in controller_nodes:
            remote = self.env.d_env.get_ssh_to_remote(node['ip'])
            logger.info("Check all HAProxy backends on {}".format(
                node['meta']['system']['fqdn']))
            haproxy_status = checkers.check_haproxy_backend(remote)
            remote.clear()
            assert_equal(haproxy_status['exit_code'], 1,
                         "HAProxy backends are DOWN. {0}".format(
                             haproxy_status))

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def scale_node(self):
        """Scale node in cluster"""
        step_config = self.env_config['scale_node'][self.scale_step]
        self._add_node(step_config)
        self.scale_step += 1

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def reset_cluster(self):
        """Reset environment"""
        raise NotImplementedError

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def delete_cluster(self):
        """Delete environment"""
        raise NotImplementedError

    @deferred_decorator([make_snapshot_if_step_fail])
    @action
    def stop_deploy(self):
        """Deploy environment"""
        raise NotImplementedError
