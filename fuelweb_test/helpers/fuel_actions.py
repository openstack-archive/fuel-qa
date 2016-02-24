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
from devops.error import DevopsCalledProcessError
from devops.models import DiskDevice
from devops.models import Node
from devops.models import Volume
from proboscis.asserts import assert_equal

from fuelweb_test import logger
from fuelweb_test import logwrap

from fuelweb_test.helpers.regenerate_repo import regenerate_centos_repo
from fuelweb_test.helpers.regenerate_repo import regenerate_ubuntu_repo
from fuelweb_test.helpers import replace_repos
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.settings import MASTER_IS_CENTOS7
from fuelweb_test.settings import FUEL_PLUGIN_BUILDER_REPO
from fuelweb_test.settings import FUEL_USE_LOCAL_NTPD
from fuelweb_test.settings import MIRROR_UBUNTU
from fuelweb_test import settings as hlp_data
from fuelweb_test.settings import NESSUS_IMAGE_PATH


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
        result = self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd="systemctl restart {0}".format(service))
        return result['exit_code'] == 0

    def put_value_to_local_yaml(self, old_file, new_file, element, value):
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
            yaml.dump(origin_yaml, f_new, default_flow_style=False,
                      default_style='"')

    def get_value_from_local_yaml(self, yaml_file, element):
        """Get a value of the element from the local yaml file

           :param str yaml_file: a path to the yaml file
           :param list element:
               list with path to element to be read
               for example: ['root_elem', 'first_elem', 'target_elem']
               if there are a few elements with equal names use integer
               to identify which element should be used
           :return obj: value
        """
        with open(yaml_file, 'r') as f_old:
            yaml_dict = yaml.load(f_old)

        for i, k in enumerate(element):
            try:
                yaml_dict = yaml_dict[k]
            except IndexError:
                raise IndexError("Element {0} not found in the file {1}"
                                 .format(element[: i + 1], f_old))
            except KeyError:
                raise KeyError("Element {0} not found in the file {1}"
                               .format(element[: i + 1], f_old))
        return yaml_dict

    def change_remote_yaml(self, path_to_file, element, value):
        """Changes values in the yaml file stored
        There is no need to copy file manually
        :param path_to_file: absolute path to the file
        :param element: list with path to the element be changed
        :param value: new value for element
        :return: Nothing
        """
        old_file = '/tmp/temp_file_{0}.old.yaml'.format(str(os.getpid()))
        new_file = '/tmp/temp_file_{0}.new.yaml'.format(str(os.getpid()))

        self.ssh_manager.download_from_remote(
            ip=self.admin_ip,
            destination=path_to_file,
            target=old_file
        )
        self.put_value_to_local_yaml(old_file, new_file, element, value)
        self.ssh_manager.upload_to_remote(
            ip=self.admin_ip,
            source=new_file,
            target=path_to_file
        )
        os.remove(old_file)
        os.remove(new_file)

    def get_value_from_remote_yaml(self, path_to_file, element):
        """Get a value from the yaml file stored
           on the master node

        :param str path_to_file: absolute path to the file
        :param list element: list with path to the element
        :return obj: value
        """

        host_tmp_file = '/tmp/temp_file_{0}.yaml'.format(str(os.getpid()))
        self.ssh_manager.download_from_remote(
            ip=self.admin_ip,
            destination=path_to_file,
            target=host_tmp_file
        )
        value = self.get_value_from_local_yaml(host_tmp_file, element)
        os.remove(host_tmp_file)
        return value

    def put_value_to_remote_yaml(self, path_to_file, element, value):
        """Put a value to the yaml file stored
           on the master node

        :param str path_to_file: absolute path to the file
        :param list element: list with path to the element be changed
        :param value: new value for element
        :return: None
        """

        host_tmp_file = '/tmp/temp_file_{0}.yaml'.format(str(os.getpid()))
        self.ssh_manager.download_from_remote(
            ip=self.admin_ip,
            destination=path_to_file,
            target=host_tmp_file
        )
        self.put_value_to_local_yaml(host_tmp_file, host_tmp_file,
                                     element, value)
        self.ssh_manager.upload_to_remote(
            ip=self.admin_ip,
            source=host_tmp_file,
            target=path_to_file
        )
        os.remove(host_tmp_file)


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
        wait(lambda: self.is_fuel_ready, timeout=timeout)

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
        fuel_settings['DNS_UPSTREAM'] = router
        fuel_settings['ADMIN_NETWORK']['dhcp_gateway'] = router

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
    def upload_packages(self, local_packages_dir, centos_repo_path,
                        ubuntu_repo_path):
        logger.info("Upload fuel's packages from directory {0}."
                    .format(local_packages_dir))

        centos_files_count = 0
        ubuntu_files_count = 0

        if centos_repo_path:
            centos_files_count = self.ssh_manager.cond_upload(
                ip=self.admin_ip,
                source=local_packages_dir,
                target=os.path.join(centos_repo_path, 'Packages'),
                condition="(?i).*\.rpm$"
            )
            if centos_files_count > 0:
                regenerate_centos_repo(centos_repo_path)

        if ubuntu_repo_path:
            ubuntu_files_count = self.ssh_manager.cond_upload(
                ip=self.admin_ip,
                source=local_packages_dir,
                target=os.path.join(ubuntu_repo_path, 'pool/main'),
                condition="(?i).*\.deb$"
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
        cmd = 'cat {cfg_file}'.format(cfg_file=hlp_data.FUEL_SETTINGS_YAML)
        result = self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd=cmd
        )
        if result['exit_code'] == 0:
            fuel_settings = yaml.load(result['stdout_str'])
        else:
            raise Exception('Can\'t output {cfg_file} file: {error}'.
                            format(cfg_file=hlp_data.FUEL_SETTINGS_YAML,
                                   error=result['stderr']))
        return fuel_settings

    def save_fuel_settings(self, settings):
        cmd = 'echo \'{0}\' > {1}'.format(yaml.dump(settings,
                                                    default_style='"',
                                                    default_flow_style=False),
                                          hlp_data.FUEL_SETTINGS_YAML)
        result = self.ssh_manager.execute(
            ip=self.admin_ip,
            cmd=cmd
        )
        assert_equal(result['exit_code'], 0,
                     "Saving Fuel settings failed: {0}!".format(result))


class NailgunActions(BaseActions):
    """NailgunActions."""  # TODO documentation

    def update_nailgun_settings_once(self, settings):
        # temporary change Nailgun settings (until next container restart)
        cfg_file = '/etc/nailgun/settings.yaml'
        ng_settings = yaml.load(
            self.ssh_manager.execute_on_remote(
                ip=self.admin_ip,
                cmd='cat {0}'.format(cfg_file))['stdout_str']
        )

        ng_settings.update(settings)
        logger.debug('Uploading new nailgun settings: {}'.format(
            ng_settings))
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd='echo "{0}" | tee {1}'.format(yaml.dump(ng_settings), cfg_file)
        )

    def set_collector_address(self, host, port, ssl=False):
        cmd = ("awk '/COLLECTOR.*URL/' /usr/lib/python2.7"
               "/site-packages/nailgun/settings.yaml")
        protocol = 'http' if not ssl else 'https'
        parameters = {}
        for p in self.ssh_manager.execute_on_remote(
                ip=self.admin_ip,
                cmd=cmd)['stdout_str'].split('\n'):
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
            self.ssh_manager.execute_on_remote(ip=self.admin_ip, cmd=cmd)

    def force_fuel_stats_sending(self):
        log_file = '/var/log/nailgun/statsenderd.log'
        # Rotate logs on restart in order to get rid of old errors
        cmd = 'cp {0}{{,.backup_$(date +%s)}}'.format(log_file)
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip, cmd=cmd, raise_on_assert=False)
        cmd = "bash -c 'echo > /var/log/nailgun/statsenderd.log'"
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip, cmd=cmd, raise_on_assert=False)
        cmd = 'supervisorctl restart statsenderd'
        if MASTER_IS_CENTOS7:
            cmd = 'systemctl restart statsenderd'
        self.ssh_manager.execute_on_remote(ip=self.admin_ip, cmd=cmd)
        cmd = 'grep -sw "ERROR" {0}'.format(log_file)
        try:
            self.ssh_manager.execute_on_remote(
                ip=self.admin_ip,
                cmd=cmd,
                assert_ec_equal=[1]
            )
        except AssertionError:
            logger.error(("Fuel stats were sent with errors! Check its log"
                         "s in {0} for details.").format(log_file))
            raise

    def force_oswl_collect(self, resources=None):
        if resources is None:
            resources = [
                'vm', 'flavor', 'volume', 'image', 'tenant', 'keystone_user'
            ]
        for resource in resources:
            cmd = 'supervisorctl restart oswl' \
                  '_{0}_collectord'.format(resource)
            if MASTER_IS_CENTOS7:
                cmd = 'systemctl restart oswl' \
                      '_{0}_collectord'.format(resource)
            self.ssh_manager.execute_on_remote(ip=self.admin_ip, cmd=cmd)


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
        Installs fuel plugin builder from sources
        on master node

        :return: nothing
        """
        fpb_cmd = """bash -c 'yum -y install git tar createrepo \
                    rpm dpkg-devel dpkg-dev rpm-build python-pip;
                    git clone {0};
                    cd fuel-plugins;
                    python setup.py sdist;
                    cd dist;
                    pip install *.tar.gz'""".format(FUEL_PLUGIN_BUILDER_REPO)

        self.ssh_manager.execute_on_remote(ip=self.admin_ip, cmd=fpb_cmd)

    def fpb_create_plugin(self, name):
        """
        Creates new plugin with given name
        :param name: name for plugin created
        :return: nothing
        """
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="fpb --create {0}".format(name)
        )

    def fpb_build_plugin(self, path):
        """
        Builds plugin from path
        :param path: path to plugin. For ex.: /root/example_plugin
        :return: packet name
        """
        packet_name = self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="bash -c 'fpb --build {0} >> /dev/null && basename {0}/*.rpm'"
            .format(path)
        )['stdout_str']
        return packet_name

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
        self.ssh_manager.execute_on_remote(
            ip=self.admin_ip,
            cmd="rm -rf {0}".format(remote_file),
            raise_on_assert=False
        )
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
        self.change_remote_yaml(
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
        self.change_remote_yaml(
            '/root/{}/metadata.yaml'.format(plugin_name),
            ['package_version'],
            new_version)

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
    def _execute_check_retcode(self, command):
        result = self.ssh_manager.execute(ip=self.admin_ip, cmd=command)
        if result['exit_code'] != 0:
            raise DevopsCalledProcessError(command=command,
                                           returncode=result['exit_code'],
                                           output=result['stderr'])

        return result['stdout_str']

    def get_bootstrap_default_config(self):
        fuel_settings = self.get_fuel_settings()
        return fuel_settings["BOOTSTRAP"]

    def parse_uuid(self, message):
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
        result = self._execute_check_retcode(command)
        if "centos" in uuid:
            return "centos"
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
        result = self._execute_check_retcode(command)

        logger.info("Bootstrap image has been built: {0}".format(result))
        uuid = self.parse_uuid(result)[0]
        path = os.path.join(kwargs.get("output-dir", "/tmp"),
                            "{0}.tar.gz".format(uuid))
        return uuid, path

    def import_bootstrap_image(self, filename, activate=False):
        command = ("fuel-bootstrap import {0} {1}"
                   .format(filename,
                           "--activate" if activate else ""))

        result = self._execute_check_retcode(command)
        return self.parse_uuid(result)[0]

    def list_bootstrap_images(self):
        command = "fuel-bootstrap list"
        result = self._execute_check_retcode(command)
        return result

    def list_bootstrap_images_uuids(self):
        return self.parse_uuid(self.list_bootstrap_images())

    def get_active_bootstrap_uuid(self):
        command = "fuel-bootstrap list"
        bootstrap_images = \
            self.ssh_manager.execute_on_remote(
                ip=self.admin_ip,
                cmd=command)['stdout_str']

        for line in bootstrap_images:
            if "active" in line and "centos" not in line:
                return self.parse_uuid(line)[0]

        logger.warning("No active bootstrap. Possibly centos is active or "
                       "something went wrong. fuel-bootstrap list:\n{0}"
                       .format("".join(bootstrap_images)))

    def delete_bootstrap_image(self, uuid):
        command = "fuel-bootstrap delete {0}".format(uuid)
        result = self._execute_check_retcode(command)
        return self.parse_uuid(result)[0]
