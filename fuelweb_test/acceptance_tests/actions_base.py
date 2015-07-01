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

from proboscis import test
from fuelweb_test.helpers import utils
from fuelweb_test.helpers.utils import timestat
from fuelweb_test.tests import base_test_case
from fuelweb_test import logger
from fuelweb_test import settings as test_settings
import os.path


def get_configs():
    """Return list of dict environment configurations"""
    import fuelweb_test
    path = os.path.join(os.path.dirname(fuelweb_test.__file__), 'environments')
    return utils.load_yaml_files(path)


def case_factory(baseclass):
    """Return list of instance """
    configs = get_configs()
    return [baseclass.caseclass_factory(
        c['case']['group-name'])(c) for c in configs]


class ActionFactory(base_test_case.TestBasic):

    @classmethod
    def get_actions(cls):
        """Return all action methods"""
        return {m: getattr(cls, m) for m in
                dir(cls) if m.startswith('_action_')}

    @classmethod
    def get_actions_order(cls):
        """Get order of actions"""
        if cls.actions_order is None:
            raise LookupError
        return cls.actions_order

    @classmethod
    def caseclass_factory(cls, case_group):
        """Create new clonned cls class contains only action methods"""
        actions_method = cls.get_actions()
        case_name = "Case_{}".format(case_group)
        test_steps = {}
        for step, action in enumerate(cls.get_actions_order()):
            n_action = action.replace("_action", "")
            step_name = "{}_Step{:03d}_{}".format(case_name, step, n_action)
            if step > 0:
                prev_step_name = "{}_Step{:03d}_{}".format(
                    case_name,
                    step - 1,
                    cls.get_actions_order()[step - 1].replace("_action", ""))
                method = utils.copy_func(actions_method[action], step_name)
                test_steps[step_name] = test(
                    method,
                    depends_on=[test_steps[prev_step_name]])
            else:
                test_steps[step_name] = test(
                    utils.copy_func(actions_method[action], step_name))
        groups = ['{}.{}'.format(g, case_group) for g in cls.base_group]
        groups = cls.base_group + groups
        ret = test(
            type(case_name, (cls,), test_steps),
            groups=groups)
        return ret


class PrepareBase(ActionFactory):
    """Base class with prepare actions

    _action_setup_master - setup master node in environment
    _action_config_release - preconfig releases if it needs
    _action_make_slaves - boot slaves and snapshop environment with
        bootstraped slaves
    _action_revert_slaves - revert environment with bootstraped slaves
    """

    def _action_setup_master(self):
        """Setup master node"""
        self.check_run("empty")
        with timestat("setup_environment", is_uniq=True):
            self.env.setup_environment()

        self.env.make_snapshot("empty", is_make=True)

    def _action_config_release(self):
        """Configuration releases"""
        self.check_run("ready")
        self.env.revert_snapshot("empty", skip_timesync=True)

        self.fuel_web.get_nailgun_version()
        if (test_settings.REPLACE_DEFAULT_REPOS and
                test_settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE):
            self.fuel_web.replace_default_repos()

        self.env.make_snapshot("ready", is_make=True)

    def _action_make_slaves(self):
        """Bootstrap slave and make snapshot

        Use slaves parameter from case section
        """
        slaves = int(self.full_config['case']['slaves'])
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        self.check_run(snapshot_name)
        self.env.revert_snapshot("ready", skip_timesync=True)
        logger.info("Bootstrap {} nodes".format(slaves))
        self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:slaves],
                                 skip_timesync=True)
        self.env.make_snapshot(snapshot_name, is_make=True)

    def _action_revert_slaves(self):
        "Run pre-saved Environment"
        slaves = int(self.full_config['case']['slaves'])
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        self.env.revert_snapshot(snapshot_name)


class ActionsBase(PrepareBase):
    """Basic actions for acceptance cases

    For chousing action order use actions_order variable, set list of actions
        order

    _action_create_env - create and configure environment
    _action_add_nodes - add nodes to environment
    _action_deploy_cluster - deploy en environment
    _action_network_check - run network check
    _action_health_check - run all ostf tests
    _action_reset_cluster - reset an environment (NotImplemented)
    _action_delete_cluster - delete en environment (NotImplemented)
    _action_stop_deploy - stop deploying of environment (NotImplemented)
    """

    base_group = None
    actions_order = None

    def __init__(self, config=None):
        super(ActionsBase, self).__init__()
        self.full_config = config
        self.env_config = config['environment-config']
        self.cluster_id = None

    def _action_create_env(self):
        """Create Fuel Environment

        For configure Environment use environment-config section in config file
        """
        logger.info("Create env {}".format(
            self.env_config['name']))
        settings = {
            "murano": self.env_config['components'].get('murano', False),
            "sahara": self.env_config['components'].get('sahara', False),
            "ceilometer": self.env_config['components'].get('ceilometer',
                                                            False),
            "user": self.env_config.get("user", "admin"),
            "password": self.env_config.get("password", "admin"),
            "tenant": self.env_config.get("tenant", "admin"),
            "volumes_lvm": self.env_config['storages'].get("volume-lvm",
                                                           False),
            "volumes_ceph": self.env_config['storages'].get("volume-ceph",
                                                            False),
            "images_ceph": self.env_config['storages'].get("image-ceph",
                                                           False),
            "ephemeral_ceph": self.env_config['storages'].get("ephemeral-ceph",
                                                              False),
            "objects_ceph": self.env_config['storages'].get("rados-ceph",
                                                            False),
            "osd_pool_size": str(self.env_config['storages'].get(
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

    def _action_add_nodes(self):
        """Add nodes to environment

        Used sub-section nodes in environment-config section
        """
        logger.info("Add nodes to env {}".format(self.cluster_id))
        names = "slave-{:02}"
        num = iter(xrange(1, test_settings.NODES_COUNT))
        nodes = {}
        for new in self.env_config['nodes']:
            for one in xrange(new['count']):
                name = names.format(next(num))
                nodes[name] = new['roles']
                logger.info("Set roles {} to node {}".format(new['roles'],
                                                             name))
        self.fuel_web.update_nodes(self.cluster_id, nodes)

    def _action_deploy_cluster(self):
        """Deploy environment"""
        self.fuel_web.deploy_cluster_wait(self.cluster_id)

    def _action_network_check(self):
        """Run network checker"""
        self.fuel_web.verify_network(self.cluster_id)

    def _action_health_check(self):
        """Run health checker"""
        self.fuel_web.run_ostf(cluster_id=self.cluster_id)

    def _action_reset_cluster(self):
        """Reset environment"""
        raise NotImplementedError

    def _action_delete_cluster(self):
        """Delete environment"""
        raise NotImplementedError

    def _action_stop_deploy(self):
        """Deploy environment"""
        raise NotImplementedError
