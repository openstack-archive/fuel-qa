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

# pylint: disable=redefined-builtin
# noinspection PyUnresolvedReferences
from six.moves import xrange
# pylint: enable=redefined-builtin

from fuelweb_test import logger
from fuelweb_test import settings
from fuelweb_test.helpers.decorators import create_diagnostic_snapshot
from fuelweb_test.helpers.utils import TimeStat
from fuelweb_test.tests.base_test_case import TestBasic as Basic

from system_test.core.discover import load_yaml


class Manager(Basic):
    """Manager class for tests."""

    def __init__(self, config_file, cls):
        super(Manager, self).__init__()
        self.full_config = None
        self.env_config = None
        self.env_settings = None
        self.config_name = None
        self._devops_config = None
        self._start_time = 0
        self.config_file = config_file
        if config_file:
            self._load_config()
        self._context = cls
        self.assigned_slaves = set()

    def _cluster_from_template(self):
        """Create cluster from template file."""

        slaves = int(self.full_config['template']['slaves'])
        cluster_name = self.env_config['name']
        snapshot_name = "ready_cluster_{}".format(cluster_name)
        if self.check_run(snapshot_name):
            self.env.revert_snapshot(snapshot_name)
            cluster_id = self.fuel_web.client.get_cluster_id(cluster_name)
            self._context._storage['cluster_id'] = cluster_id
            logger.info("Got deployed cluster from snapshot")
            return True
        elif self.get_ready_slaves(slaves):
            self.env.sync_time()
            logger.info("Create env {}".format(
                self.env_config['name']))
            cluster_settings = {
                "sahara": self.env_settings['components'].get(
                    'sahara', False),
                "ceilometer": self.env_settings['components'].get(
                    'ceilometer', False),
                "ironic": self.env_settings['components'].get(
                    'ironic', False),
                "user": self.env_config.get("user", "admin"),
                "password": self.env_config.get("password", "admin"),
                "tenant": self.env_config.get("tenant", "admin"),
                "volumes_lvm": self.env_settings['storages'].get(
                    "volume-lvm", False),
                "volumes_ceph": self.env_settings['storages'].get(
                    "volume-ceph", False),
                "images_ceph": self.env_settings['storages'].get(
                    "image-ceph", False),
                "ephemeral_ceph": self.env_settings['storages'].get(
                    "ephemeral-ceph", False),
                "objects_ceph": self.env_settings['storages'].get(
                    "rados-ceph", False),
                "osd_pool_size": str(self.env_settings['storages'].get(
                    "replica-ceph", 2)),
                "net_provider": self.env_config['network'].get(
                    'provider', 'neutron'),
                "net_segment_type": self.env_config['network'].get(
                    'segment-type', 'vlan'),
                "assign_to_all_nodes": self.env_config['network'].get(
                    'pubip-to-all',
                    False),
                "neutron_l3_ha": self.env_config['network'].get(
                    'neutron-l3-ha', False),
                "neutron_dvr": self.env_config['network'].get(
                    'neutron-dvr', False),
                "neutron_l2_pop": self.env_config['network'].get(
                    'neutron-l2-pop', False)
            }

            cluster_id = self.fuel_web.create_cluster(
                name=self.env_config['name'],
                mode=settings.DEPLOYMENT_MODE,
                release_name=self.env_config['release'],
                settings=cluster_settings)

            self._context._storage['cluster_id'] = cluster_id
            logger.info("Add nodes to env {}".format(cluster_id))
            names = "slave-{:02}"
            num = iter(xrange(1, slaves + 1))
            nodes = {}
            for new in self.env_config['nodes']:
                for _ in xrange(new['count']):
                    name = names.format(next(num))
                    while name in self.assigned_slaves:
                        name = names.format(next(num))

                    self.assigned_slaves.add(name)
                    nodes[name] = new['roles']
                    logger.info("Set roles {} to node {}".format(
                        new['roles'], name))
            self.fuel_web.update_nodes(cluster_id, nodes)
            self.fuel_web.verify_network(cluster_id)
            self.fuel_web.deploy_cluster_wait(cluster_id)
            self.fuel_web.verify_network(cluster_id)
            self.env.make_snapshot(snapshot_name, is_make=True)
            self.env.resume_environment()
            return True
        else:
            logger.error("Can't deploy cluster because snapshot"
                         " with bootstrapped nodes didn't revert")
            raise RuntimeError("Can't deploy cluster because snapshot"
                               " with bootstrapped nodes didn't revert")

    def _cluster_from_config(self, config):
        """Create cluster from predefined config."""

        slaves = len(config.get('nodes'))
        cluster_name = config.get('name', self._context.__name__)
        snapshot_name = "ready_cluster_{}".format(cluster_name)
        if self.check_run(snapshot_name):
            self.env.revert_snapshot(snapshot_name)
            cluster_id = self.fuel_web.client.get_cluster_id(cluster_name)
            self._context._storage['cluster_id'] = cluster_id
            logger.info("Getted deployed cluster from snapshot")
            return True
        elif self.get_ready_slaves(slaves):
            self.env.sync_time()
            logger.info("Create env {}".format(cluster_name))
            cluster_id = self.fuel_web.create_cluster(
                name=cluster_name,
                mode=config.get('mode', settings.DEPLOYMENT_MODE),
                settings=config.get('settings', {})
            )
            self._context._storage['cluster_id'] = cluster_id
            self.fuel_web.update_nodes(
                cluster_id,
                config.get('nodes')
            )
            self.fuel_web.verify_network(cluster_id)
            self.fuel_web.deploy_cluster_wait(cluster_id)
            self.fuel_web.verify_network(cluster_id)
            self.env.make_snapshot(snapshot_name, is_make=True)
            self.env.resume_environment()
            return True
        else:
            logger.error("Can't deploy cluster because snapshot"
                         " with bootstrapped nodes didn't revert")
            raise RuntimeError("Can't deploy cluster because snapshot"
                               " with bootstrapped nodes didn't revert")

    def check_run(self, snapshot_name):
        """Checks if run of current test is required.

        :param snapshot_name: Name of the snapshot the function should make
        :type snapshot_name: str

        """
        if snapshot_name:
            return self.env.d_env.has_snapshot(snapshot_name)

    def _load_config(self):
        """Read cluster config from yaml file."""

        config = load_yaml(self.config_file)
        self.full_config = config
        self.env_config = config[
            'template']['cluster_template']
        self.env_settings = config[
            'template']['cluster_template']['settings']
        self.config_name = config['template']['name']

        if 'devops_settings' in config['template']:
            self._devops_config = config

    def get_ready_setup(self):
        """Create virtual environment and install Fuel master node.
        """

        logger.info("Getting ready setup")
        if self.check_run("empty"):
            self.env.revert_snapshot("empty")
            return True
        else:
            with TimeStat("setup_environment", is_uniq=True):
                if list(self.env.d_env.get_nodes(role='fuel_master')):
                    self.env.setup_environment()
                    self.fuel_post_install_actions()

                elif list(self.env.d_env.get_nodes(role='centos_master')):
                    # need to use centos_master.yaml devops template
                    hostname = ''.join((settings.FUEL_MASTER_HOSTNAME,
                                        settings.DNS_SUFFIX))
                    self.centos_setup_fuel(hostname)
                else:
                    raise RuntimeError(
                        "No Fuel master nodes found!")

                self.env.make_snapshot("empty", is_make=True)
                self.env.resume_environment()
                return True

    def get_ready_release(self):
        """Make changes in release configuration."""

        logger.info("Getting ready release")
        if self.check_run("ready"):
            self.env.revert_snapshot("ready")
            logger.info("Getted ready release from snapshot")
            return True
        elif self.get_ready_setup():
            self.env.sync_time()
            self.fuel_web.get_nailgun_version()
            self.fuel_web.change_default_network_settings()

            if (settings.REPLACE_DEFAULT_REPOS and
                    settings.REPLACE_DEFAULT_REPOS_ONLY_ONCE):
                self.fuel_web.replace_default_repos()

            self.env.make_snapshot("ready", is_make=True)
            self.env.resume_environment()
            return True
        else:
            logger.error("Can't config releases setup "
                         "snapshot didn't revert")
            raise RuntimeError("Can't config releases setup "
                               "snapshot didn't revert")

    def get_ready_slaves(self, slaves=None):
        """Bootstrap slave nodes."""

        logger.info("Getting ready slaves")
        if not slaves:
            if hasattr(self._context, 'cluster_config'):
                slaves = len(self._context.cluster_config.get('nodes'))
            elif self.full_config:
                slaves = int(self.full_config['template']['slaves'])
            else:
                logger.error("Unable to count slaves")
                raise RuntimeError("Unable to count slaves")
        snapshot_name = "ready_with_{}_slaves".format(slaves)
        if self.check_run(snapshot_name):
            self.env.revert_snapshot(snapshot_name)
            logger.info("Getted ready slaves from snapshot")
            return True
        elif self.get_ready_release():
            self.env.sync_time()
            logger.info("Bootstrap {} nodes".format(slaves))
            self.env.bootstrap_nodes(self.env.d_env.nodes().slaves[:slaves],
                                     skip_timesync=True)
            self.env.make_snapshot(snapshot_name, is_make=True)
            self.env.resume_environment()
            return True
        logger.error(
            "Can't bootstrap nodes because release snapshot didn't revert")
        raise RuntimeError(
            "Can't bootstrap nodes because release snapshot didn't revert")

    def get_ready_cluster(self, config=None):
        """Create and deploy cluster."""

        logger.info("Getting deployed cluster")
        config = config or self._context.cluster_config or None
        if config:
            self._cluster_from_config(config=config)
        else:
            self._cluster_from_template()

    def show_step(self, step, details='', initialize=False):
        """Show a description of the step taken from docstring

           :param int/str step: step number to show
           :param str details: additional info for a step
        """
        test_func = self._context._current_test
        test_func_name = test_func.__name__

        if initialize or step == 1:
            self.current_log_step = step
        else:
            self.current_log_step += 1
            if self.current_log_step != step:
                error_message = 'The step {} should be {} at {}'
                error_message = error_message.format(
                    step,
                    self.current_log_step,
                    test_func_name
                )
                logger.error(error_message)

        docstring = test_func.__doc__
        docstring = '\n'.join([s.strip() for s in docstring.split('\n')])
        steps = {s.split('. ')[0]: s for s in
                 docstring.split('\n') if s and s[0].isdigit()}
        if details:
            details_msg = ': {0} '.format(details)
        else:
            details_msg = ''
        if str(step) in steps:
            logger.info("\n" + " " * 55 + "<<< {0} {1}>>>"
                        .format(steps[str(step)], details_msg))
        else:
            logger.info("\n" + " " * 55 + "<<< {0}. (no step description "
                        "in scenario) {1}>>>".format(str(step), details_msg))

    def make_diagnostic_snapshot(self, status, name):
        create_diagnostic_snapshot(self.env, status, name)

    def save_env_snapshot(self, name):
        self.env.make_snapshot(name, is_make=True)
