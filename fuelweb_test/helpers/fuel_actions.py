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

from devops.helpers.helpers import wait
from devops.models import DiskDevice
from devops.models import Node
from devops.models import Volume
from proboscis.asserts import assert_true
import yaml

from core.helpers.log_helpers import logwrap

from fuelweb_test import logger
from fuelweb_test.helpers.decorators import retry
from fuelweb_test.helpers.regenerate_repo import regenerate_centos_repo
from fuelweb_test.helpers.regenerate_repo import regenerate_ubuntu_repo
from fuelweb_test.helpers import replace_repos
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import dict_merge
from fuelweb_test.settings import FUEL_PLUGIN_BUILDER_FROM_GIT
from fuelweb_test.settings import FUEL_PLUGIN_BUILDER_REPO
from fuelweb_test.settings import FUEL_PLUGIN_BUILDER_PACKET
from fuelweb_test.settings import FUEL_USE_LOCAL_NTPD
from fuelweb_test.settings import KEYSTONE_CREDS
from fuelweb_test.settings import MIRROR_UBUNTU
from fuelweb_test.settings import PLUGIN_PACKAGE_VERSION
from fuelweb_test.settings import FUEL_SETTINGS_YAML
from fuelweb_test.settings import NESSUS_IMAGE_PATH
from fuelweb_test.helpers.utils import YamlEditor


class BaseActions(object):
    """BaseActions."""  # TODO documentation

    def __init__(self):
        self.ssh_manager = SSHManager()
        self.admin_ip = self.ssh_manager.admin_ip

    def __repr__(self):
        klass, obj_id = type(self), hex(id(self))
        return "[{klass}({obj_id})]".format(
            klass=klass,
            obj_id=obj_id)

    def restart_service(self, service):
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="systemctl restart {0}".format(service),
            err_msg="Failed to restart service {!r}, please inspect logs for "
                    "details".format(service))


class AdminActions(BaseActions):
    """ All actions relating to the admin node."""

    @logwrap
    def is_fuel_service_ready(self, service):
        result = self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd="timeout 5 fuel-utils check_service {0}".format(service))
        return result['exit_code'] == 0

    @logwrap
    def is_fuel_ready(self):
        result = self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd="timeout 15 fuel-utils check_all")
        return result['exit_code'] == 0

    @logwrap
    def wait_for_fuel_ready(self, timeout=300):
        wait(lambda: self.is_fuel_ready, timeout=timeout,
             timeout_msg="Fuel services are not ready, please check the "
                         "output of 'fuel-utils check_all")

    @logwrap
    @retry()
    def ensure_cmd(self, cmd):
        self.ssh_manager.execute_on_remote(ip=self.admin_ip, cmd=cmd)

    @logwrap
    def upload_plugin(self, plugin):
        """ Upload plugin on master node.
        """
        logger.info("Upload fuel's plugin from path {}.".format(plugin))
        return self.ssh_manager.upload_to_remote(
            ip=self.ssh_manager.admin_ip,
            source=plugin,
            target='/var',
            port=self.ssh_manager.admin_port)

    @logwrap
    def install_plugin(self, plugin_file_name):
        """ Install plugin on master node.
        """
        return self.ssh_manager.execute_on_remote(
            ip=self.ssh_manager.admin_ip,
            cmd="cd /var && fuel plugins --install "
                "{plugin!s} ".format(plugin=plugin_file_name),
            port=self.ssh_manager.admin_port,
            err_msg='Install script failed'
        )

    @logwrap
    def modify_configs(self, router):
        # Slave nodes should use the gateway of 'admin' network as the default
        # gateway during provisioning and as an additional DNS server.
        fuel_settings = self.get_fuel_settings()
        fuel_settings['DEBUG'] = True
        fuel_settings['DNS_UPSTREAM'] = router
        fuel_settings['ADMIN_NETWORK']['dhcp_gateway'] = router
        fuel_settings["FUEL_ACCESS"]['user'] = KEYSTONE_CREDS['username']
        fuel_settings["FUEL_ACCESS"]['password'] = KEYSTONE_CREDS['password']

        if FUEL_USE_LOCAL_NTPD:
            # Try to use only ntpd on the host as the time source
            # for admin node
            cmd = 'ntpdate -p 4 -t 0.2 -ub {0}'.format(router)

            if not self.ssh_manager.execute(ip=self.admin_ip,
                                            cmd=cmd)['exit_code']:
                # Local ntpd on the host is alive, so
                # remove all NTP sources and add the host instead.
                logger.info("Switching NTPD on the Fuel admin node to use "
                            "{0} as the time source.".format(router))
                ntp_keys = [k for k in fuel_settings.keys()
                            if re.match(r'^NTP', k)]
                for key in ntp_keys:
                    fuel_settings.pop(key)
                fuel_settings['NTP1'] = router

        if MIRROR_UBUNTU:
            fuel_settings['BOOTSTRAP']['repos'] = \
                replace_repos.replace_ubuntu_repos(
                    {
                        'value': fuel_settings['BOOTSTRAP']['repos']
                    },
                    upstream_host='archive.ubuntu.com')
            logger.info("Replace default Ubuntu mirror URL for "
                        "bootstrap image in Fuel settings")
        self.save_fuel_settings(fuel_settings)

    @logwrap
    def update_fuel_setting_yaml(self, path):
        """This method override fuel settings yaml according to custom yaml

        :param path: a string of full path to custom setting yaml
        """

        fuel_settings = self.get_fuel_settings()
        with open(path) as fyaml:
            custom_fuel_settings = yaml.load(fyaml)

        fuel_settings = dict_merge(fuel_settings, custom_fuel_settings)
        self.save_fuel_settings(fuel_settings)
        logger.debug('File /etc/fuel/astute.yaml was updated.'
                     'And now is {}'.format(fuel_settings))

    @logwrap
    def upload_packages(self, local_packages_dir, centos_repo_path,
                        ubuntu_repo_path, clean_target=False):
        logger.info("Upload fuel's packages from directory {0}."
                    .format(local_packages_dir))

        centos_files_count = 0
        ubuntu_files_count = 0

        if centos_repo_path:
            centos_files_count = self.ssh_manager.cond_upload(
                ip=self.admin_ip,
                source=local_packages_dir,
                target=os.path.join(centos_repo_path, 'Packages'),
                condition="(?i).*\.rpm$",
                clean_target=clean_target
            )
            if centos_files_count > 0:
                regenerate_centos_repo(centos_repo_path)

        if ubuntu_repo_path:
            ubuntu_files_count = self.ssh_manager.cond_upload(
                ip=self.admin_ip,
                source=local_packages_dir,
                target=os.path.join(ubuntu_repo_path, 'pool/main'),
                condition="(?i).*\.deb$",
                clean_target=clean_target
            )
            if ubuntu_files_count > 0:
                regenerate_ubuntu_repo(ubuntu_repo_path)

        return centos_files_count, ubuntu_files_count

    @logwrap
    def clean_generated_image(self, distro):
        out = self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd="find /var/www/nailgun/targetimages/ -name "
                "'env*{}*' -printf '%P\n'".format(distro.lower())
        )
        images = ''.join(out)

        logger.debug("images are {}".format(images))
        self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd="find /var/www/nailgun/targetimages/ -name 'env*{}*'"
                " -delete".format(distro.lower())
        )

    def get_fuel_settings(self):
        return YamlEditor(
            file_path=FUEL_SETTINGS_YAML,
            ip=self.admin_ip
        ).get_content()

    def save_fuel_settings(self, settings):
        with YamlEditor(
                file_path=FUEL_SETTINGS_YAML,
                ip=self.admin_ip
        ) as data:
            data.content = settings

    @logwrap
    def get_tasks_description(self, release=None):
        """Get tasks description

        :param release: a string with release name
        :return: a dictionary of tasks description
        """
        if not release:
            release = ''
        cmd = "cat `find /etc/puppet/{} -name tasks.yaml`".format(release)
        return self.ssh_manager.check_call(self.admin_ip, cmd).stdout_yaml


class NailgunActions(BaseActions):
    """NailgunActions."""  # TODO documentation

    def update_nailgun_settings(self, settings):
        cfg_file = '/etc/nailgun/settings.yaml'
        with YamlEditor(file_path=cfg_file, ip=self.admin_ip) as ng_settings:
            ng_settings.content.update(settings)

            logger.debug('Uploading new nailgun settings: {}'.format(
                ng_settings))
        self.restart_service("nailgun")

    def set_collector_address(self, host, port, ssl=False):
        base_cfg_file = ('/usr/lib/python2.7/site-packages/'
                         'nailgun/settings.yaml')
        assert_true(
            self.ssh_manager.exists_on_remote(
                self.ssh_manager.admin_ip, base_cfg_file),
            "Nailgun config file was not found at {!r}".format(base_cfg_file))

        server = "{!s}:{!s}".format(host, port)
        parameters = {'COLLECTOR_SERVER': server,
                      'OSWL_COLLECT_PERIOD': 0}
        if not ssl:
            # replace https endpoints to http endpoints
            with self.ssh_manager.open_on_remote(self.admin_ip,
                                                 base_cfg_file) as f:
                data = yaml.load(f)
            for key, value in data.items():
                if (isinstance(key, str) and key.startswith("COLLECTOR") and
                        key.endswith("URL") and value.startswith("https")):
                    parameters[key] = "http" + value[len("https"):]
        logger.debug('Custom collector parameters: {!r}'.format(parameters))
        self.update_nailgun_settings(parameters)

    def force_fuel_stats_sending(self):
        log_file = '/var/log/nailgun/statsenderd.log'
        # Rotate logs on restart in order to get rid of old errors
        cmd = 'mv {0}{{,.backup_$(date +%s)}}'.format(log_file)
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip, cmd=cmd, raise_on_assert=False)
        self.restart_service('statsenderd')

        wait(lambda: self.ssh_manager.exists_on_remote(self.admin_ip,
                                                       log_file),
             timeout=10)
        cmd = 'grep -sw "ERROR" {0}'.format(log_file)
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip, cmd=cmd, assert_ec_equal=[1],
            err_msg=("Fuel stats were sent with errors! Check its logs"
                     " in {0} for details.").format(log_file))

    def force_oswl_collect(self, resources=None):
        resources = resources or ['vm', 'flavor', 'volume', 'image', 'tenant',
                                  'keystone_user']
        for resource in resources:
            self.restart_service("oswl_{}_collectord".format(resource))


class PostgresActions(BaseActions):
    """PostgresActions."""  # TODO documentation

    def run_query(self, db, query):
        cmd = "su - postgres -c 'psql -qt -d {0} -c \"{1};\"'".format(
            db, query)
        return self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=cmd)['stdout_str']

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
    def fpb_install(self):
        """
        Installs fuel plugin builder on master node

        :return: nothing
        """
        fpb_packet = "git+{}".format(FUEL_PLUGIN_BUILDER_REPO)\
            if FUEL_PLUGIN_BUILDER_FROM_GIT else "fuel-plugin-builder"

        cmd = ("bash -c 'yum -y install tar createrepo rpm dpkg-devel "
               "dpkg-dev rpm-build python-pip git;"
               "pip install {}'").format(fpb_packet)

        self.ssh_manager.check_call(self.admin_ip, cmd)

    def fpb_create_plugin(self, name, package_version=PLUGIN_PACKAGE_VERSION):
        """
        Creates new plugin with given name
        :param name: name for plugin created
        :param package_version: plugin package version to create template for
        :return: nothing
        """
        cmd = "fpb --create {0}".format(name)
        if package_version != '':
            cmd += ' --package-version {0}'.format(package_version)
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=cmd
        )

    def fpb_build_plugin(self, path):
        """
        Builds plugin from path
        :param path: path to plugin. For ex.: /root/example_plugin
        :return: packet name
        """
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="bash -c 'fpb --build {0}'".format(path)
        )
        packet_name = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="bash -c 'basename {0}/*.rpm'".format(path)
        )['stdout_str']
        return packet_name

    def fpb_update_release_in_metadata(self, path):
        """Update fuel version and openstack release version

        :param path: path to plugin's dir on master node
        """
        metadata_path = os.path.join(path, 'metadata.yaml')
        output = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip, cmd="fuel --fuel-version --json",
            jsonify=True)['stdout_json']
        fuel_version = [str(output['release'])]
        openstack_version = str(output['openstack_version'])
        with YamlEditor(metadata_path, ip=self.admin_ip) as editor:
            editor.content['fuel_version'] = fuel_version
            editor.content['releases'][0]['version'] = openstack_version

    def fpb_validate_plugin(self, path):
        """
        Validates plugin for errors
        :param path: path to plugin to be verified
        :return: nothing
        """
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="fpb --check {0}".format(path))

    def fpb_replace_plugin_content(self, local_file, remote_file):
        """
        Replaces file  with given local file
        :param local_file: path to the local file
        :param remote_file: file to be replaced
        :return: nothing
        """
        self.ssh_manager.rm_rf_on_remote(ip=self.admin_ip, path=remote_file)
        self.ssh_manager.upload_to_remote(
            ip=self.admin_ip,
            source=local_file,
            target=remote_file
        )

    def fpb_change_plugin_version(self, plugin_name, new_version):
        """
        Changes plugin version with given one
        :param plugin_name: plugin name
        :param new_version: new version to be used for plugin
        :return: nothing
        """
        with YamlEditor('/root/{}/metadata.yaml'.format(plugin_name),
                        ip=self.admin_ip) as editor:
            editor.content['version'] = new_version

    def fpb_change_package_version(self, plugin_name, new_version):
        """
        Changes plugin's package version
        :param plugin_name: plugin to be used for changing version
        :param new_version: version to be changed at
        :return: nothing
        """
        with YamlEditor('/root/{}/metadata.yaml'.format(plugin_name),
                        ip=self.admin_ip) as editor:
            editor.content['package_version'] = new_version

    def fpb_copy_plugin(self, source, target):
        """
        Copy new plugin from source to target
        :param source: initial plugin location
        :param target: target path
        :return: nothing
        """
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="cp {0} {1}".format(source, target))


class CobblerActions(BaseActions):
    """CobblerActions."""  # TODO documentation

    def add_dns_upstream_server(self, dns_server_ip):
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="sed '$anameserver {0}' -i /etc/dnsmasq.upstream".format(
                dns_server_ip))
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd='service dnsmasq restart')


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


class FuelBootstrapCliActions(AdminActions):
    def get_bootstrap_default_config(self):
        fuel_settings = self.get_fuel_settings()
        return fuel_settings["BOOTSTRAP"]

    @staticmethod
    def parse_uuid(message):
        uuid_regex = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-" \
                     r"[0-9a-f]{4}-[0-9a-f]{12}"

        # NOTE: Splitting for matching only first uuid in case of parsing
        # images list, because image label could contain matching strings
        message_lines = message.splitlines()
        uuids = []

        for line in message_lines:
            match = re.search(uuid_regex, line)
            if match is not None:
                uuids.append(match.group())

        if not uuids:
            raise Exception("Could not find uuid in fuel-bootstrap "
                            "output: {0}".format(message))
        return uuids

    def activate_bootstrap_image(self, uuid):
        command = "fuel-bootstrap activate {0}".format(uuid)
        result = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=command,
        )['stdout_str']

        return self.parse_uuid(result)[0]

    def build_bootstrap_image(self, **kwargs):
        simple_fields = \
            ("ubuntu-release", "http-proxy", "https-proxy", "script",
             "label", "extend-kopts", "kernel-flavor",
             "root-ssh-authorized-file", "output-dir", "image-build-dir")
        list_fields = ("repo", "direct-repo-addr", "package", "extra-dir")
        flag_fields = ("activate", )
        command = "fuel-bootstrap build "

        for field in simple_fields:
            if kwargs.get(field) is not None:
                command += "--{0} {1} ".format(field, kwargs.get(field))

        for field in list_fields:
            if kwargs.get(field) is not None:
                for value in kwargs.get(field):
                    command += "--{0} {1} ".format(field, value)

        for field in flag_fields:
            if kwargs.get(field) is not None:
                command += "--{0} ".format(field)

        logger.info("Building bootstrap image: {0}".format(command))
        result = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=command,
        )['stdout_str']

        logger.info("Bootstrap image has been built: {0}".format(result))
        uuid = self.parse_uuid(result)[0]
        path = os.path.join(kwargs.get("output-dir", "/tmp"),
                            "{0}.tar.gz".format(uuid))
        return uuid, path

    def import_bootstrap_image(self, filename, activate=False):
        command = ("fuel-bootstrap import {0} {1}"
                   .format(filename,
                           "--activate" if activate else ""))

        result = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=command,
        )['stdout_str']
        return self.parse_uuid(result)[0]

    def list_bootstrap_images(self):
        command = "fuel-bootstrap list"
        result = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=command,
        )['stdout_str']
        return result

    def list_bootstrap_images_uuids(self):
        return self.parse_uuid(self.list_bootstrap_images())

    def get_active_bootstrap_uuid(self):
        command = "fuel-bootstrap list"
        bootstrap_images = \
            self.ssh_manager.execute_on_remote(
                ip=self.admin_ip,
                cmd=command)['stdout_str'].split('\n')

        for line in bootstrap_images:
            if "active" in line:
                return self.parse_uuid(line)[0]

        logger.warning("No active bootstrap. Fuel-bootstrap list:\n{0}"
                       .format("".join(bootstrap_images)))

    def delete_bootstrap_image(self, uuid):
        command = "fuel-bootstrap delete {0}".format(uuid)
        result = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd=command,
        )['stdout_str']
        return self.parse_uuid(result)[0]
