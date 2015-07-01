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
from fuelweb_test.tests import base_test_case
from fuelweb_test import logger
import os.path


def get_configs():
    import fuelweb_test
    path = os.path.join(os.path.dirname(fuelweb_test.__file__), 'environments')
    # print path
    return utils.load_yaml_files(path)


def case_factory(baseclass):
    # for config in get_configs():
    configs = get_configs()
    # print configs
    return [baseclass.caseclass_factory(
        c['case']['group-name'])(c) for c in configs]


class ActionsBase(base_test_case.TestBasic):

    base_group = None
    actions_order = None

    def __init__(self, config=None):
        super(ActionsBase, self).__init__()
        self.config = config

    @classmethod
    def get_actions(cls):
        return {m: getattr(cls, m) for m in dir(cls) if m.startswith(
                                                                '_action_')}

    @classmethod
    def get_actions_order(cls):
        if cls.actions_order is None:
            raise LookupError
        return cls.actions_order

    @classmethod
    def caseclass_factory(cls, case_group):
        actions_method = cls.get_actions()
        test_steps = {}
        for step, action in enumerate(cls.get_actions_order()):
            step_name = "test_{:03d}_{}".format(step, action)
            if step > 0:
                prev_step_name = "test_{:03d}_{}".format(
                    step - 1, cls.get_actions_order()[step - 1])
                test_steps[step_name] = test(
                    utils.copy_func(actions_method[action], step_name),
                    depends_on=[test_steps[prev_step_name]])
            else:
                test_steps[step_name] = test(
                    utils.copy_func(actions_method[action], step_name))
        groups = ['{}.{}'.format(g, case_group) for g in cls.base_group]
        groups = cls.base_group + groups
        return test(
            type(
                "Case_{}".format(cls.base_group),
                (cls,), test_steps),
            groups=groups)

    def _action_create_env(self):
        """Create ENV"""
        logger.info("Create env {}".format(
            self.config['environment-config']['name']))
        logger.info("Env with modules {}".format(
            self.config['environment-config']['modules']))
        assert 'env_create_ok' == 'env_create_ok'

    def _action_add_node(self):
        """Add node to environment"""
        logger.info("Add node to env {}".format(
            self.config['environment-config']['nodes']))
        assert 'add_node_ok' == 'add_node_ok'

    def _action_deploy_cluster(self):
        """Deploy environment"""
        logger.info("Start deploy env {}".format(
            self.config['environment-config']['name']))
        assert 'deploy_ok' == 'deploy_ok'
        logger.info("Deploy succefull env {}".format(
            self.config['environment-config']['name']))

    def _action_network_check(self):
        """Run network checker"""
        logger.info("Start network checker on env {}".format(
            self.config['environment-config']['name']))
        assert 'net_checker_ok' == 'net_checker_ok'

    def _action_health_check(self):
        """Run health checker"""
        logger.info("Start network checker on env {}".format(
            self.config['environment-config']['name']))
        assert 'health_checker_ok' == 'health_checker_ok'

    def _action_reset_cluster(self):
        """Reset environment"""
        logger.info("Reset on env {}".format(
            self.config['environment-config']['name']))
        assert 'reset_ok' == 'reset_ok'

    def _action_delete_cluster(self):
        """Delete environment"""
        logger.info("Reset on env {}".format(
            self.config['environment-config']['name']))
        assert 'delete_ok' == 'delete_ok'

    def _action_stop_deploy(self):
        """Deploy environment"""
        logger.info("Start stoping deploy env {}".format(
            self.config['environment-config']['name']))
        assert 'stop_ok' == 'stop_ok'
        logger.info("Stop finish succefull env {}".format(
            self.config['environment-config']['name']))
