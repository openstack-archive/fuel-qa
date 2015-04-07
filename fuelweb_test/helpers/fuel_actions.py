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

import yaml
import re

from devops.helpers.helpers import wait
from proboscis.asserts import assert_equal

from fuelweb_test import logger

from fuelweb_test.settings import FUEL_PLUGIN_BUILDER_REPO
from fuelweb_test.settings import FUEL_USE_LOCAL_NTPD


class BaseActions(object):
    def __init__(self, admin_remote):
        self.admin_remote = admin_remote
        self.container = None

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
            to copy from container to master node use:
                copy_from = container:path_from
                copy_to = path_to
            to copy from master node to container use:
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

    def wait_for_ready_container(self):
        wait(lambda: self.is_container_ready, 300)


class AdminActions(BaseActions):
    """ All actions relating to the admin node.
    """

    def __init__(self, admin_remote):
        super(AdminActions, self).__init__(admin_remote)

    def modify_configs(self, router):
        # Slave nodes sould use the gateway of 'admin' network as the default
        # gateway during provisioning and as an additional DNS server.
        # resolv.conf should contains nameserver that resolve intranet URLs.
        config = '/etc/fuel/astute.yaml'
        resolv = '/etc/resolv.conf'

        # wait until fuelmenu fill the astute.yaml
        cmd = "fgrep 'dhcp_gateway' {0}".format(config)
        wait(lambda: not self.admin_remote.execute(cmd)['exit_code'], 60)

        cmd = ("sed -i 's/dhcp_gateway:.*/dhcp_gateway: {0}/' {1} &&"
               "sed -i 's/\\(DNS_UPSTREAM:\\) \\(.*\\)/\\1 {0} \\2/' {1} &&"
               "sed -i 's/\\(nameserver\\) \\(.*\\)/\\1 {0} \\2/' {2}"
               .format(router, config, resolv))
        result = self.admin_remote.execute(cmd)
        assert_equal(0, result['exit_code'],
                     "Command [{cmd}] failed with the following result: {res}"
                     .format(cmd=cmd, res=result))

        if FUEL_USE_LOCAL_NTPD:
            #Try to use only ntpd on the host as the time sourse for admin node
            cmd = 'ntpdate -p 4 -t 0.2 -ub {0}'.format(router)

            if not self.admin_remote.execute(cmd)['exit_code']:
                # Local ntpd on the host is alive, so
                # remove all NTP sources and add the host instead.
                cmd = ("sed -i '/^NTP/d' {0} && echo 'NTP1: {1}' >> {0}"
                       .format(config, router))
                logger.info("Switching NTPD on the Fuel admin node to use "
                            "{0} as the time source.".format(router))
                result = self.admin_remote.execute(cmd)
                assert_equal(0, result['exit_code'],
                             "Command [{cmd}] failed with the following "
                             "result: {res}".format(cmd=cmd, res=result))


class NailgunActions(BaseActions):
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


class FuelPluginBuilder(object):
    """
    Basic class for fuel plugin builder support in tests.

    Initializes BaseActions.
    """
    def __init__(self, admin_remote):
        self.admin_remote = admin_remote
        self.admin_node = BaseActions(self.admin_remote)

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

        self.admin_node.execute_in_container(fpb_cmd, 'nailgun', 0)

    def fpb_create_plugin(self, name):
        """
        Creates new plugin with given name
        :param name: name for plugin created
        :return: nothing
        """
        self.admin_node.execute_in_container("fpb --create {0}"
                                             .format(name), 'nailgun', 0)

    def fpb_build_plugin(self, path):
        """
        Builds plugin from path
        :param path: path to plugin. For ex.: /root/example_plugin
        :return: nothing
        """
        self.admin_node.execute_in_container("fpb --build {0}"
                                             .format(path), 'nailgun', 0)

    def fpb_validate_plugin(self, path):
        """
        Validates plugin for errors
        :param path: path to plugin to be verified
        :return: nothing
        """
        self.admin_node.execute_in_container("fpb --check {0}"
                                             .format(path), 'nailgun', 0)

    def fpb_copy_plugin_from_container(self, plugin_name, path_to):
        """
        Copies plugin with given name to path
        outside container on the master node
        :param plugin_name: plugin to be copied
        :param path_to: path to copy to
        :return: nothing
        """
        self.admin_node.copy_between_node_and_container(
            'nailgun:/root/{0}/*.rpm'.format(plugin_name),
            '{0}/{1}.rpm'.format(path_to, plugin_name))

    def fpb_replace_plugin_content(self, local_file, remote_file):
        """
        Replaces file inside nailgun container with given local file
        :param local_file: path to the local file
        :param remote_file: file to be replaced
        :return: nothing
        """
        self.admin_node.execute_in_container(
            "rm -rf {0}".format(remote_file), 'nailgun')
        self.admin_remote.upload(local_file, "/tmp/temp.file")
        self.admin_node.copy_between_node_and_container(
            '/tmp/temp.file', 'nailgun:{0}'.format(remote_file))

    def fpb_change_plugin_version(self, plugin_name, new_version):
        """
        Changes plugin version with given one
        :param plugin_name: plugin name
        :param new_version: new version to be used for plugin
        :return: nothing
        """
        self.admin_node.execute_in_container(
            'sed -i "s/^\(version:\) \(.*\)/\\1 {0}/g" '
            '/root/{1}/metadata.yaml'
            .format(new_version, plugin_name), 'nailgun')

    def fpb_change_package_version(self, plugin_name, new_version):
        """
        Changes plugin's package version
        :param plugin_name: plugin to be used for changing version
        :param new_version: version to be changed at
        :return: nothing
        """
        self.admin_node.execute_in_container(
            'sed -i "s/^\(package_version: \'\)\(.*\)\(\'\)/\\1{0}\\3/g" '
            '/root/{1}/metadata.yaml'
            .format(new_version, plugin_name), 'nailgun')

    def change_content_in_yaml(self, old_file, new_file, element, value):
        """
        Changes content in old_file at element is given to the new value
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


class CobblerActions(BaseActions):
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
