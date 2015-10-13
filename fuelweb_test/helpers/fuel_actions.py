#    Copyright 2014 Mirantis, Inc.
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
import re
import yaml

from devops.helpers.helpers import wait
from devops.error import TimeoutError
from devops.models import DiskDevice
from devops.models import Node
from devops.models import Volume
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test import logwrap
from fuelweb_test.helpers import checkers

from fuelweb_test.helpers.regenerate_repo import regenerate_centos_repo
from fuelweb_test.helpers.regenerate_repo import regenerate_ubuntu_repo
from fuelweb_test.helpers.utils import cond_upload
from fuelweb_test.settings import FUEL_PLUGIN_BUILDER_REPO
from fuelweb_test.settings import FUEL_USE_LOCAL_NTPD
from fuelweb_test import settings as hlp_data
from fuelweb_test.settings import NESSUS_IMAGE_PATH


class BaseActions(object):
    """BaseActions."""  # TODO documentation

    def __init__(self, admin_remote):
        self.admin_remote = admin_remote
        self.container = None

    def __repr__(self):
        klass, obj_id = type(self), hex(id(self))
        container = getattr(self, 'container', None)
        return "[{klass}({obj_id}), container:{container}]".format(
            klass=klass,
            obj_id=obj_id,
            container=container)

    def execute_in_container(self, command, container=None, exit_code=None,
                             stdin=None):
        if not container:
            container = self.container
        cmd = 'dockerctl shell {0} {1}'.format(container, command)
        if stdin is not None:
            cmd = 'echo "{0}" | {1}'.format(stdin, cmd)
        result = self.admin_remote.execute(cmd)
        if exit_code is not None:
            assert_equal(exit_code,
                         result['exit_code'],
                         ('Command {cmd} returned exit code "{e}", but '
                          'expected "{c}". Output: {out}; {err} ').format(
                             cmd=cmd,
                             e=result['exit_code'],
                             c=exit_code,
                             out=result['stdout'],
                             err=result['stderr']
                         ))
        return ''.join(result['stdout']).strip()

    def copy_between_node_and_container(self, copy_from, copy_to):
        """ Copy files from/to container.
        :param copy_from: path to copy file from
        :param copy_to: path to copy file to
        For ex.:

            - to copy from container to master node use:
                 copy_from = container:path_from
                 copy_to = path_to
            - to copy from master node to container use:
                 copy_from = path_from
                 copy_to = container:path_to

        :return:
            Standard output from console
        """
        cmd = 'dockerctl copy {0} {1}'.format(copy_from, copy_to)
        result = self.admin_remote.execute(cmd)
        assert_equal(0, result['exit_code'],
                     ('Command copy returned exit code "{e}", but '
                      'expected "0". Output: {out}; {err} ').format(
                         cmd=cmd,
                         e=result['exit_code'],
                         out=result['stdout'],
                         err=result['stderr']))
        return ''.join(result['stdout']).strip()

    @property
    def is_container_ready(self):
        result = self.admin_remote.execute("timeout 5 dockerctl check {0}"
                                           .format(self.container))
        return (result['exit_code'] == 0)

    def wait_for_ready_container(self, timeout=300):
        wait(lambda: self.is_container_ready, timeout=timeout)

    def change_content_in_yaml(self, old_file, new_file, element, value):
        """Changes content in old_file at element is given to the new value
        and creates new file with changed content
        :param old_file: a path to the file content from to be changed
        :param new_file: a path to the new file to ve created with new content
        :param element: tuple with path to element to be changed
        for example: ['root_elem', 'first_elem', 'target_elem']
        if there are a few elements with equal names use integer
        to identify which element should be used
        :return: nothing
        """

        with open(old_file, 'r') as f_old:
            yaml_dict = yaml.load(f_old)

        origin_yaml = yaml_dict
        for k in element[:-1]:
            yaml_dict = yaml_dict[k]
        yaml_dict[element[-1]] = value

        with open(new_file, 'w') as f_new:
            yaml.dump(origin_yaml, f_new)

    def change_yaml_file_in_container(
            self, path_to_file, element, value, container=None):
        """Changes values in the yaml file stored at container
        There is no need to copy file manually
        :param path_to_file: absolutely path to the file
        :param element: list with path to the element be changed
        :param value: new value for element
        :param container: Container with file. By default it is nailgun
        :return: Nothing
        """
        if not container:
            container = self.container

        old_file = '/tmp/temp_file.old.yaml'
        new_file = '/tmp/temp_file.new.yaml'

        self.copy_between_node_and_container(
            '{0}:{1}'.format(container, path_to_file), old_file)
        self.admin_remote.download(old_file, old_file)
        self.change_content_in_yaml(old_file, new_file, element, value)
        self.admin_remote.upload(new_file, new_file)
        self.copy_between_node_and_container(
            new_file, '{0}:{1}'.format(container, path_to_file))


class AdminActions(BaseActions):
    """ All actions relating to the admin node."""

    def __init__(self, admin_remote):
        super(AdminActions, self).__init__(admin_remote)

    @logwrap
    def modify_configs(self, router):
        # Slave nodes sould use the gateway of 'admin' network as the default
        # gateway during provisioning and as an additional DNS server.
        # resolv.conf should contains nameserver that resolve intranet URLs.
        config = '/etc/fuel/astute.yaml'
        resolv = '/etc/resolv.conf'

        # wait until fuelmenu fill the astute.yaml
        cmd = "fgrep 'dhcp_gateway' {0}".format(config)
        wait(lambda: not self.admin_remote.execute(cmd)['exit_code'], 60)
        # wait until fuelmenu is finished
        cmd = "ps -C fuelmenu"
        wait(lambda: self.admin_remote.execute(cmd)['exit_code'], 60)

        cmd = ("sed -i 's/\"dhcp_gateway\":.*/\"dhcp_gateway\": \"{0}\"/' {1} "
               "&& sed -i 's/\\(\"DNS_UPSTREAM\":\\).*/\\1 \"{0}\"/' {1} &&"
               "sed -i 's/\\(nameserver\\) \\(.*\\)/\\1 {0} \\2/' {2}"
               .format(router, config, resolv))
        result = self.admin_remote.execute(cmd)
        assert_equal(0, result['exit_code'],
                     "Command [{cmd}] failed with the following result: {res}"
                     .format(cmd=cmd, res=result))

        if FUEL_USE_LOCAL_NTPD:
            # Try to use only ntpd on the host as the time source
            # for admin node
            cmd = 'ntpdate -p 4 -t 0.2 -ub {0}'.format(router)

            if not self.admin_remote.execute(cmd)['exit_code']:
                # Local ntpd on the host is alive, so
                # remove all NTP sources and add the host instead.
                cmd = ("sed -i '/^\"NTP/d' {0} && echo '\"NTP1\": \"{1}\"' "
                       ">> {0}".format(config, router))
                logger.info("Switching NTPD on the Fuel admin node to use "
                            "{0} as the time source.".format(router))
                result = self.admin_remote.execute(cmd)
                assert_equal(0, result['exit_code'],
                             "Command [{cmd}] failed with the following "
                             "result: {res}".format(cmd=cmd, res=result))

    @logwrap
    def upload_packages(self, local_packages_dir, centos_repo_path,
                        ubuntu_repo_path):
        logger.info("Upload fuel's packages from directory {0}."
                    .format(local_packages_dir))

        centos_files_count = 0
        ubuntu_files_count = 0

        if centos_repo_path:
            centos_files_count = cond_upload(
                self.admin_remote, local_packages_dir,
                os.path.join(centos_repo_path, 'Packages'),
                "(?i).*\.rpm$")
            if centos_files_count > 0:
                regenerate_centos_repo(self.admin_remote, centos_repo_path)

        if ubuntu_repo_path:
            ubuntu_files_count = cond_upload(
                self.admin_remote, local_packages_dir,
                os.path.join(ubuntu_repo_path, 'pool/main'),
                "(?i).*\.deb$")
            if ubuntu_files_count > 0:
                regenerate_ubuntu_repo(self.admin_remote, ubuntu_repo_path)

        return centos_files_count, ubuntu_files_count

    @logwrap
    def clean_generated_image(self, distro):
        images = ''.join(
            self.admin_remote.execute(
                "find /var/www/nailgun/targetimages/ -name"
                " 'env*{}*' -printf '%P\n'".format(distro.lower())))

        logger.debug("images are {}".format(images))
        self.admin_remote.execute(
            "find /var/www/nailgun/targetimages/ -name 'env*{}*'"
            " -delete".format(distro.lower()))

    def upgrade_master_node(self):
        """This method upgrades master node with current state."""

        with self.admin_remote as master:
            checkers.upload_tarball(master, hlp_data.TARBALL_PATH, '/var')
            checkers.check_file_exists(master,
                                       os.path.join(
                                           '/var',
                                           os.path.basename(hlp_data.
                                                            TARBALL_PATH)))
            checkers.untar(master, os.path.basename(hlp_data.TARBALL_PATH),
                           '/var')

            keystone_pass = hlp_data.KEYSTONE_CREDS['password']
            checkers.run_script(master, '/var', 'upgrade.sh',
                                password=keystone_pass)
            checkers.wait_upgrade_is_done(master, 3000,
                                          phrase='*** UPGRADING MASTER NODE'
                                                 ' DONE SUCCESSFULLY')
            checkers.check_upgraded_containers(master,
                                               hlp_data.UPGRADE_FUEL_FROM,
                                               hlp_data.UPGRADE_FUEL_TO)


class NailgunActions(BaseActions):
    """NailgunActions."""  # TODO documentation

    def __init__(self, admin_remote):
        super(NailgunActions, self).__init__(admin_remote)
        self.container = 'nailgun'

    def update_nailgun_settings_once(self, settings):
        # temporary change Nailgun settings (until next container restart)
        cfg_file = '/etc/nailgun/settings.yaml'
        ng_settings = yaml.load(self.execute_in_container(
            'cat {0}'.format(cfg_file), exit_code=0))
        ng_settings.update(settings)
        logger.debug('Uploading new nailgun settings: {}'.format(
            ng_settings))
        self.execute_in_container('tee {0}'.format(cfg_file),
                                  stdin=yaml.dump(ng_settings),
                                  exit_code=0)

    def set_collector_address(self, host, port, ssl=False):
        cmd = ("awk '/COLLECTOR.*URL/' /usr/lib/python2.6"
               "/site-packages/nailgun/settings.yaml")
        protocol = 'http' if not ssl else 'https'
        parameters = {}
        for p in self.execute_in_container(cmd, exit_code=0).split('\n'):
            parameters[p.split(': ')[0]] = re.sub(
                r'https?://\{collector_server\}',
                '{0}://{1}:{2}'.format(protocol, host, port),
                p.split(': ')[1])[1:-1]
        parameters['OSWL_COLLECT_PERIOD'] = 0
        logger.debug('Custom collector parameters: {0}'.format(parameters))
        self.update_nailgun_settings_once(parameters)
        if ssl:
            # if test collector server doesn't have trusted SSL cert
            # installed we have to use this hack in order to disable cert
            # verification and allow using of self-signed SSL certificate
            cmd = ("sed -i '/elf.verify/ s/True/False/' /usr/lib/python2.6"
                   "/site-packages/requests/sessions.py")
            self.execute_in_container(cmd, exit_code=0)

    def force_fuel_stats_sending(self):
        log_file = '/var/log/nailgun/statsenderd.log'
        # Rotate logs on restart in order to get rid of old errors
        cmd = 'mv {0}{{,.backup_$(date +%s)}}'.format(log_file)
        self.execute_in_container(cmd)
        cmd = 'supervisorctl restart statsenderd'
        self.execute_in_container(cmd, exit_code=0)
        cmd = 'grep -sw "ERROR" {0}'.format(log_file)
        try:
            self.execute_in_container(cmd, exit_code=1)
        except AssertionError:
            logger.error(("Fuel stats were sent with errors! Check its log"
                         "s in {0} for details.").format(log_file))
            raise

    def force_oswl_collect(self, resources=['vm', 'flavor', 'volume',
                                            'image', 'tenant',
                                            'keystone_user']):
        for resource in resources:
            cmd = 'supervisorctl restart oswl' \
                  '_{0}_collectord'.format(resource)
            self.execute_in_container(cmd, exit_code=0)


class PostgresActions(BaseActions):
    """PostgresActions."""  # TODO documentation

    def __init__(self, admin_remote):
        super(PostgresActions, self).__init__(admin_remote)
        self.container = 'postgres'

    def run_query(self, db, query):
        cmd = "su - postgres -c 'psql -qt -d {0} -c \"{1};\"'".format(
            db, query)
        return self.execute_in_container(cmd, exit_code=0)

    def action_logs_contain(self, action, group=False,
                            table='action_logs'):
        logger.info("Checking that '{0}' action was logged..".format(
            action))
        log_filter = "action_name" if not group else "action_group"
        q = "select id from {0} where {1} = '\"'\"'{2}'\"'\"'".format(
            table, log_filter, action)
        logs = [i.strip() for i in self.run_query('nailgun', q).split('\n')
                if re.compile(r'\d+').match(i.strip())]
        logger.info("Found log records with ids: {0}".format(logs))
        return len(logs) > 0

    def count_sent_action_logs(self, table='action_logs'):
        q = "select count(id) from {0} where is_sent = True".format(table)
        return int(self.run_query('nailgun', q))


class FuelPluginBuilder(BaseActions):
    """
    Basic class for fuel plugin builder support in tests.

    Initializes BaseActions.
    """
    def __init__(self, admin_remote):
        super(FuelPluginBuilder, self).__init__(admin_remote)
        self.container = 'nailgun'

    def fpb_install(self):
        """
        Installs fuel plugin builder from sources
        in nailgun container on master node

        :return: nothing
        """
        fpb_cmd = """bash -c 'yum -y install git tar createrepo \
                    rpm dpkg-devel rpm-build;
                    git clone {0};
                    cd fuel-plugins/fuel_plugin_builder;
                    python setup.py sdist;
                    cd dist;
                    pip install *.tar.gz'""".format(FUEL_PLUGIN_BUILDER_REPO)

        self.execute_in_container(fpb_cmd, self.container, 0)

    def fpb_create_plugin(self, name):
        """
        Creates new plugin with given name
        :param name: name for plugin created
        :return: nothing
        """
        self.execute_in_container("fpb --create {0}".format(
            name), self.container, 0)

    def fpb_build_plugin(self, path):
        """
        Builds plugin from path
        :param path: path to plugin. For ex.: /root/example_plugin
        :return: nothing
        """
        self.execute_in_container("fpb --build {0}".format(
            path), self.container, 0)

    def fpb_validate_plugin(self, path):
        """
        Validates plugin for errors
        :param path: path to plugin to be verified
        :return: nothing
        """
        self.execute_in_container("fpb --check {0}".format(
            path), self.container, 0)

    def fpb_copy_plugin_from_container(self, plugin_name, path_to):
        """
        Copies plugin with given name to path
        outside container on the master node
        :param plugin_name: plugin to be copied
        :param path_to: path to copy to
        :return: nothing
        """
        self.copy_between_node_and_container(
            '{0}:/root/{1}/*.rpm'.format(self.container, plugin_name),
            '{0}/{1}.rpm'.format(path_to, plugin_name))

    def fpb_replace_plugin_content(self, local_file, remote_file):
        """
        Replaces file inside nailgun container with given local file
        :param local_file: path to the local file
        :param remote_file: file to be replaced
        :return: nothing
        """
        self.execute_in_container(
            "rm -rf {0}".format(remote_file), self.container)
        self.admin_remote.upload(local_file, "/tmp/temp.file")
        self.copy_between_node_and_container(
            '/tmp/temp.file', '{0}:{1}'.format(self.container, remote_file))

    def fpb_change_plugin_version(self, plugin_name, new_version):
        """
        Changes plugin version with given one
        :param plugin_name: plugin name
        :param new_version: new version to be used for plugin
        :return: nothing
        """
        self.change_yaml_file_in_container(
            '/root/{}/metadata.yaml'.format(plugin_name),
            ['version'],
            new_version)

    def fpb_change_package_version(self, plugin_name, new_version):
        """
        Changes plugin's package version
        :param plugin_name: plugin to be used for changing version
        :param new_version: version to be changed at
        :return: nothing
        """
        self.change_yaml_file_in_container(
            '/root/{}/metadata.yaml'.format(plugin_name),
            ['package_version'],
            new_version)


class CobblerActions(BaseActions):
    """CobblerActions."""  # TODO documentation

    def __init__(self, admin_remote):
        super(CobblerActions, self).__init__(admin_remote)
        self.container = 'cobbler'

    def add_dns_upstream_server(self, dns_server_ip):
        self.execute_in_container(
            command="sed '$anameserver {0}' -i /etc/dnsmasq.upstream".format(
                dns_server_ip),
            exit_code=0,
        )
        self.execute_in_container(
            command='service dnsmasq restart',
            exit_code=0
        )


class DockerActions(object):
    """DockerActions."""  # TODO documentation

    def __init__(self, admin_remote):
        self.admin_remote = admin_remote

    def list_containers(self):
        return self.admin_remote.execute('dockerctl list')['stdout']

    def wait_for_ready_containers(self, timeout=300):
        cont_actions = []
        for container in self.list_containers():
            cont_action = BaseActions(self.admin_remote)
            cont_action.container = container
            cont_actions.append(cont_action)
        try:
            wait(lambda: all([cont_action.is_container_ready
                              for cont_action in cont_actions]),
                 timeout=timeout)
        except TimeoutError:
            failed_containers = [x.container for x in cont_actions
                                 if not x.is_container_ready]
            raise TimeoutError(
                "Container(s) {0} failed to start in {1} seconds."
                .format(failed_containers, timeout))

    def restart_container(self, container):
        self.admin_remote.execute('dockerctl restart {0}'.format(container))
        cont_action = BaseActions(self.admin_remote)
        cont_action.container = container
        cont_action.wait_for_ready_container()

    def restart_containers(self):
        for container in self.list_containers():
            self.restart_container(container)

    def execute_in_containers(self, cmd):
        for container in self.list_containers():
            self.admin_remote.execute(
                "dockerctl shell {0} bash -c '{1}'".format(container, cmd))


class NessusActions(object):
    """ NessusActions."""   # TODO documentation

    def __init__(self, d_env):
        self.devops_env = d_env

    def add_nessus_node(self):
        node = Node.node_create(
            name='slave-nessus',
            environment=self.devops_env,
            boot=['hd'])
        node.attach_to_networks()
        volume = Volume.volume_get_predefined(NESSUS_IMAGE_PATH)
        DiskDevice.node_attach_volume(node=node, volume=volume)
        node.define()
        node.start()
