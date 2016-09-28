#    Copyright 2013 Mirantis, Inc.
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

from __future__ import division

import hashlib
import json
import os
import re
from time import sleep

from devops.error import TimeoutError
from devops.helpers.helpers import wait_pass
from devops.helpers.helpers import wait
from devops.helpers.ssh_client import SSHAuth
from netaddr import IPAddress
from netaddr import IPNetwork
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true

from keystoneauth1 import exceptions
import yaml

from core.helpers.log_helpers import logwrap

from fuelweb_test import logger
from fuelweb_test.helpers.ssh_manager import SSHManager
from fuelweb_test.helpers.utils import get_mongo_partitions
from fuelweb_test.settings import EXTERNAL_DNS
from fuelweb_test.settings import EXTERNAL_NTP
from fuelweb_test.settings import OPENSTACK_RELEASE
from fuelweb_test.settings import OPENSTACK_RELEASE_UBUNTU
from fuelweb_test.settings import POOLS
from fuelweb_test.settings import PUBLIC_TEST_IP
from fuelweb_test.settings import SSH_IMAGE_CREDENTIALS


ssh_manager = SSHManager()


@logwrap
def validate_minimal_amount_nodes(
        nodes, expected_amount,
        state='discover', online=True):
    """Validate amount of nodes in state

    :type nodes: iterable
    :type expected_amount: int
    :type state: str
    :type online: bool
    :raises: Exception
    """
    fnodes = [
        node for node in nodes
        if node['online'] == online and node['status'] == state]
    if len(fnodes) < expected_amount:
        raise Exception(
            'Nodes in state {state} (online: {online}): '
            '{amount}, while expected: {expected}'.format(
                state=state,
                online=online,
                amount=len(fnodes),
                expected=expected_amount
            )
        )


@logwrap
def check_cinder_status(ip):
    """Parse output and return False if any enabled service is down.
    'cinder service-list' stdout example:
    | cinder-scheduler | node-1.test.domain.local | nova | enabled |   up  |
    | cinder-scheduler | node-2.test.domain.local | nova | enabled |  down |
    """
    cmd = '. openrc; cinder service-list'
    result = ssh_manager.execute_on_remote(
        ip=ip,
        cmd=cmd,
        raise_on_assert=False
    )
    cinder_services = result['stdout_str']
    logger.debug('>$ cinder service-list\n{}'.format(cinder_services))
    if result['exit_code'] == 0:
        return all(' up ' in x.split('enabled')[1]
                   for x in cinder_services.split('\n')
                   if 'cinder' in x and 'enabled' in x and
                   len(x.split('enabled')))
    return False


@logwrap
def check_image(image, md5, path):
    local_path = "{0}/{1}".format(path, image)
    logger.debug('Check md5 {0} of image {1}/{2}'.format(md5, path, image))
    if not os.path.isfile(local_path):
        logger.error('Image {0} not found in {1} directory'.format(
            image, path))
        return False
    with open(local_path, mode='rb') as fimage:
        digits = hashlib.md5()
        while True:
            buf = fimage.read(4096)
            if not buf:
                break
            digits.update(buf)
        md5_local = digits.hexdigest()
    if md5_local != md5:
        logger.error('MD5 of {0}/{1} is not correct, aborting'.format(
            path, image))
        return False
    return True


@logwrap
def verify_service(ip, service_name, count=1,
                   ignore_count_of_proccesses=False):
    ps_output = ssh_manager.execute_on_remote(
        ip=ip,
        cmd='ps ax'
    )['stdout']
    api = [ps for ps in ps_output if service_name in ps]
    logger.debug("{} \\n: {}".format(service_name, str(api)))
    if not ignore_count_of_proccesses:
        assert_equal(len(api), count,
                     "{0} count not equal to {1}".format(service_name, count))
    else:
        assert_true(len(api), "Service '{0}' not found!".format(service_name))


@logwrap
def verify_service_list_api(os_conn, service_count):
    def _verify():
        ret = os_conn.get_nova_service_list()
        logger.debug('Service list {0}'.format(ret))
        assert_equal(service_count, len(ret),
                     'Expected service count is {0},'
                     ' but get {1} count, actual list {2}'.format(
                         service_count, len(ret), ret))
        for service in ret:
            logger.debug('service is {0}'.format(service))
            assert_equal(
                service.state, 'up',
                'Service {0} on host {1} has next '
                'state {2}'.format(service.binary,
                                   service.host,
                                   service.state))
    try:
        _verify()
    except AssertionError:
        logger.debug(
            "Services still not read. Sleeping for 60 seconds and retrying")
        sleep(60)
        _verify()


@logwrap
def verify_glance_image_api(os_conn):
    ret = os_conn.get_image_list()
    assert_equal(1, len([i for i in ret if i.name == 'TestVM']),
                 "TestVM not found in glance image-list")


@logwrap
def verify_network_list_api(os_conn, net_count=None):
    ret = os_conn.get_nova_network_list()
    assert_equal(net_count, len(ret),
                 'Unexpected count of networks detected, '
                 'expected: {0}, current {1} count,'
                 ' full list {2}'.format(net_count, len(ret), ret))


@logwrap
def check_ceph_image_size(ip, expected_size, device='vdc'):
    ret = ssh_manager.check_call(
        ip=ip,
        command="df -m /dev/{device}* | grep ceph | awk"
                " {size}".format(device=device,
                                 size=re.escape('{print $2}'))
    ).stdout

    if not ret:
        logger.error(
            "Partition not present! {}: ".format(
                ssh_manager.check_call(ip=ip, command="df -m").stdout_str))
        raise Exception()
    logger.debug("Partitions: {part}".format(part=ret))
    assert_true(abs(float(ret[0].rstrip()) / expected_size - 1) < 0.1,
                "size {0} is not equal"
                " to {1}".format(ret[0].rstrip(),
                                 expected_size))


@logwrap
def check_cinder_image_size(ip, expected_size, device='vdc3'):
    ret = get_mongo_partitions(ip, device)[0].rstrip().rstrip('G')
    cinder_size = float(ret) * 1024
    assert_true(abs(cinder_size / expected_size - 1) < 0.1,
                "size {0} is not equal"
                " to {1}".format(ret[0].rstrip(),
                                 expected_size))


@logwrap
def check_unallocated_space(disks, contr_img_ceph=False):
    for disk in disks:
        # In case we have Ceph for images all space on controller
        # should be given to Base System space:
        if contr_img_ceph:
            logger.info("Check that all space on /dev/{d} is allocated for "
                        "Base System Space".format(d=disk['name']))
            if not bool(disk["volumes"][0]["size"] == disk["size"]):
                return False
        else:
            logger.info("Get overall size of volumes")
            sizes = [v['size'] for v in disk["volumes"]]
            logger.info("Space on disk: {s}".format(s=disk['size']))
            logger.info("Summary space of disks on /dev/{d}: {s}".format(
                d=disk["name"], s=sum(sizes)))
            if not bool(sum(sizes) == disk["size"]):
                return False
    return True


@logwrap
def check_archive_type(tar_path):
    if os.path.splitext(tar_path)[1] not in [".tar", ".lrz", ".fp", ".rpm"]:
        raise Exception("Wrong archive type!")


@logwrap
def check_file_exists(ip, path):
    assert_true(ssh_manager.exists_on_remote(ip, path),
                'Can not find {0}'.format(path))
    logger.info('File {0} exists on {1}'.format(path, ip))


@logwrap
def wait_phrase_in_log(ip, timeout, interval, phrase, log_path):
    cmd = "grep '{0}' '{1}'".format(phrase, log_path)
    wait(
        lambda: not SSHManager().execute(ip=ip, cmd=cmd)['exit_code'],
        interval=interval,
        timeout=timeout,
        timeout_msg="The phrase {0} not found in {1} file on "
                    "remote node".format(phrase, log_path))


@logwrap
def enable_feature_group(env, group):
    fuel_settings = env.admin_actions.get_fuel_settings()
    if group not in fuel_settings["FEATURE_GROUPS"]:
        fuel_settings["FEATURE_GROUPS"].append(group)
    env.admin_actions.save_fuel_settings(fuel_settings)

    # NOTE(akostrikov) We use FUEL_SETTINGS_YAML as primary source or truth and
    # update nailgun configs via puppet from that value
    ssh_manager.check_call(
        ip=ssh_manager.admin_ip,
        command='puppet apply /etc/puppet/modules/fuel/examples/nailgun.pp'
    )

    def check_api_group_enabled():
        try:
            return (group in
                    env.fuel_web.client.get_api_version()["feature_groups"])
        except exceptions.HttpError:
            return False

    wait(check_api_group_enabled, interval=10, timeout=60 * 20,
         timeout_msg='Failed to enable feature group - {!r}'.format(group))


def find_backup(ip):
    backups = ssh_manager.execute(ip,
                                  "ls -1u /var/backup/fuel/*/*.lrz")["stdout"]
    if backups:
        arch_path = backups[0]
        logger.info('Backup archive found: {0}'.format(arch_path))
        return arch_path
    else:
        raise ValueError("No backup file found in the '/var/backup/fuel/'")


@logwrap
def backup_check(ip):
    logger.info("Backup check archive status")
    path = find_backup(ip)
    assert_true(path, "Can not find backup. Path value '{0}'".format(path))
    test_result = ssh_manager.execute(ip,
                                      "test -e {0}".format(path.rstrip()))
    assert_true(test_result['exit_code'] == 0,
                "Archive '{0}' does not exist".format(path.rstrip()))


_md5_record = re.compile(r'(?P<md5>\w+)[ \t]+(?P<filename>\w+)')


def parse_md5sum_output(string):
    """Process md5sum command output and return dict filename: md5

    :param string: output of md5sum
    :type string: str
    :rtype: dict
    :return: dict
    """
    return {filename: md5 for md5, filename in _md5_record.findall(string)}


def diff_md5(before, after, no_dir_change=True):
    """Diff md5sum output

    :type before: str
    :type after: str
    :param no_dir_change: Check, that some files was added or removed
    :type no_dir_change: bool
    """
    before_dict = parse_md5sum_output(before)
    after_dict = parse_md5sum_output(after)

    before_files = set(before_dict.keys())
    after_files = set(after_dict.keys())

    diff_filenames = before_files ^ after_files

    dir_change = (
        "Directory contents changed:\n"
        "\tRemoved files: {removed}\n"
        "\tNew files: {created}".format(
            removed=[
                filename for filename in diff_filenames
                if filename in before_files],
            created=[
                filename for filename in diff_filenames
                if filename in after_files],
        )
    )
    if no_dir_change:
        assert_true(len(diff_filenames) == 0, dir_change)
    else:
        logger.debug(dir_change)

    changelist = [
        {
            'filename': filename,
            'before': before_dict[filename],
            'after': after_dict[filename]}
        for filename in before_files & after_files
        if before_dict[filename] != after_dict[filename]
    ]
    assert_true(
        len(changelist) == 0,
        "Files has been changed:\n"
        "{}".format(
            "".join(
                map(
                    lambda record: "{filename}: {before} -> {after}\n".format(
                        **record),
                    changelist
                )
            )
        )
    )


@logwrap
def restore_check_sum(ip):
    logger.debug('Check if removed file /etc/fuel/data was restored')

    assert_true(
        ssh_manager.exists_on_remote(ip=ip, path='/etc/fuel/data'),
        'Test file /etc/fuel/data was not restored!!!')

    logger.info("Restore check md5sum")
    md5sum_backup = ssh_manager.check_call(ip, "cat /etc/fuel/sum")
    assert_true(md5sum_backup['stdout_str'],
                'Command cat /etc/fuel/sum '
                'failed with {0}'.format(md5sum_backup['stderr']))
    md5sum_restore = ssh_manager.check_call(
        ip=ip,
        command="md5sum /etc/fuel/data | sed -n 1p | awk '{print $1}'"
    )
    assert_equal(
        md5sum_backup.stdout_str, md5sum_restore.stdout_str,
        "Checksum is not equal:\n"
        "\tOLD: {0}\n"
        "\tNEW: {1}".format(
            md5sum_backup.stdout_str, md5sum_restore.stdout_str
        )
    )


@logwrap
def iptables_check(ip):
    logger.info("Iptables check")
    ssh_manager.execute(ip, "iptables-save > /etc/fuel/iptables-restore")
    iptables_backup = ssh_manager.execute(
        ip=ip,
        cmd="sed -e '/^:/d; /^#/d' /etc/fuel/iptables-backup"
    )
    iptables_restore = ssh_manager.execute(
        ip=ip,
        cmd="sed -e '/^:/d; /^#/d' /etc/fuel/iptables-restore"
    )
    assert_equal(iptables_backup, iptables_restore,
                 "list of iptables rules are not equal")


@logwrap
def check_mysql(ip, node_name):
    check_cmd = 'pkill -0 -x mysqld'
    check_crm_cmd = ('crm resource status clone_p_mysqld |'
                     ' grep -q "is running on: $HOSTNAME"')
    check_galera_cmd = ("mysql --connect_timeout=5 -sse \"SELECT"
                        " VARIABLE_VALUE FROM"
                        " information_schema.GLOBAL_STATUS"
                        " WHERE VARIABLE_NAME"
                        " = 'wsrep_local_state_comment';\"")

    wait(lambda: ssh_manager.execute(ip, check_cmd)['exit_code'] == 0,
         timeout=10 * 60,
         timeout_msg='MySQL daemon is down on {0}'.format(node_name))
    logger.info('MySQL daemon is started on {0}'.format(node_name))

    # TODO(astudenov): add timeout_msg
    wait_pass(
        lambda: assert_equal(
            ssh_manager.execute(
                ip,
                check_crm_cmd)['exit_code'],
            0,
            'MySQL resource is NOT running on {0}'.format(node_name)),
        timeout=120)
    try:
        wait(lambda: ''.join(ssh_manager.execute(
            ip, check_galera_cmd)['stdout']).rstrip() == 'Synced', timeout=600,
            timeout_msg='galera status != "Synced" on node {!r} with ip {}'
                        ''.format(node_name, ip))
    except TimeoutError:
        logger.error('galera status is {0}'.format(''.join(ssh_manager.execute(
            ip, check_galera_cmd)['stdout']).rstrip()))
        raise


@logwrap
def check_action_logs(scenario, postgres_actions):
    def _check(_action, _group=False):
        assert_true(postgres_actions.action_logs_contain(_action, _group),
                    "Action logs are missed for '{0}'!".format(
                        _action))

    actions = [
        {
            'desc': [''],
            'name': ['master_node_settings'],
            'group': [],
            'regex': False,
        },
        {
            'desc': [r'create\s+.*(cluster|environment|cloud)'],
            'name': ['cluster_collection'],
            'group': ['cluster_attributes', 'network_configuration'],
            'regex': True,
        },
        {
            'desc': ['deploy'],
            'name': ['deploy_changes', 'provision', 'deployment',
                     'cluster_collection', 'check_before_deployment'],
            'group': ['cluster_changes', 'cluster_checking'],
            'regex': True,
        },
        {
            'desc': [r'verif.*\s+.*network|network.*\s+.*verif'],
            'name': ['check_networks', 'verify_networks'],
            'group': ['network_verification'],
            'regex': True,
        },
        {
            'desc': [r'(stop|abort).*(deployment|provision)'],
            'name': ['stop_deployment'],
            'group': ['cluster_changes'],
            'regex': True,
        },
        {
            'desc': [r'reset.*(deployment|provision)'],
            'name': ['reset'],
            'group': ['cluster_changes'],
            'regex': True,
        },
        {
            'desc': [r'rename.*(cluster|environment|cloud)'],
            'name': ['cluster_instance'],
            'group': ['cluster_changes'],
            'regex': True,
        },
        {
            'desc': [r'upgrade'],
            'name': ['releases_collection'],
            'group': ['release_changes'],
            'regex': True,
        },
        {
            'desc': [r'update.*(cluster|environment|cloud)'],
            'name': ['update'],
            'group': ['cluster_changes'],
            'regex': True,
        },
        {
            'desc': [r'upload.*deployment'],
            'name': ['deployment_info'],
            'group': ['orchestrator'],
            'regex': True,
        },
        {
            'desc': [r'upload.*provisioning'],
            'name': ['provisioning_info'],
            'group': ['orchestrator'],
            'regex': True,
        },
        # Logging of OSTF isn't implemented yet, so actions list is
        # empty
        {
            'desc': ['OSTF', 'Health'],
            'name': [],
            'group': [],
            'regex': False,
        },
    ]

    # Check logs in Nailgun database
    for action in actions:
        if action['regex']:
            if not any(re.search(regex, scenario, re.IGNORECASE)
                       for regex in action['desc']):
                continue
        elif not any(action in scenario for action in action['desc']):
            logger.info(action['desc'])
            continue
        for action_name in action['name']:
            _check(action_name, _group=False)
        for action_group in action['group']:
            _check(action_group, _group=True)


def execute_query_on_collector(collector_remote, master_uuid, query,
                               collector_db='collector',
                               collector_db_user='collector',
                               collector_db_pass='collector'):
    if master_uuid is not None:
        query = "{0} where master_node_uid = '{1}';".format(query, master_uuid)
    cmd = 'PGPASSWORD={0} psql -qt -h 127.0.0.1 -U {1} -d {2} -c "{3}"'.\
        format(collector_db_pass, collector_db_user, collector_db, query)
    logger.debug('query collector is {0}'.format(cmd))
    return ''.join(collector_remote.execute(cmd)['stdout']).strip()


def count_stats_on_collector(collector_remote, master_uuid):
    return execute_query_on_collector(collector_remote, master_uuid=None,
                                      query="select (select count(*) from "
                                            "action_logs where master_node_uid"
                                            " = \'{0}\') + (select count(*) "
                                            "from installation_structures "
                                            "where master_node_uid = \'{0}\')".
                                      format(master_uuid))


@logwrap
def check_stats_on_collector(collector_remote, postgres_actions, master_uuid):
    sent_logs_count = postgres_actions.count_sent_action_logs()
    logger.info("Number of logs that were sent to collector: {}".format(
        sent_logs_count
    ))
    logs = collector_remote.get_action_logs_count(master_uuid)
    logger.info("Number of logs that were saved on collector: {}".format(logs))
    assert_true(sent_logs_count <= int(logs),
                ("Count of action logs in Nailgun DB ({0}) is bigger than on "
                 "Collector ({1}), but should be less or equal").format(
                    sent_logs_count, logs))

    sum_stats_count = len(
        [collector_remote.get_installation_info(master_uuid)['id']])
    assert_equal(int(sum_stats_count), 1,
                 "Installation structure wasn't saved on Collector side proper"
                 "ly: found: {0}, expected: 1 record.".format(sum_stats_count))

    summ_stats = collector_remote.get_installation_info_data(master_uuid)
    general_stats = {
        'clusters_num': int,
        'allocated_nodes_num': int,
        'unallocated_nodes_num': int,
        'fuel_release': dict,
        'clusters': list,
        'user_information': dict,
    }

    # Check that important data (clusters number, nodes number, nodes roles,
    # user's email, used operation system, OpenStack stats) is saved correctly
    for stat_type in general_stats:
        assert_true(
            isinstance(summ_stats[stat_type], general_stats[stat_type]),
            "Installation structure in Collector's DB doesn't contain"
            "the following stats: {0}".format(stat_type))

    real_clusters_number = int(postgres_actions.run_query(
        db='nailgun', query='select count(*) from clusters;'))
    assert_equal(real_clusters_number, summ_stats['clusters_num'],
                 'Real clusters number is {0}, but usage statistics says '
                 'that clusters number is {1}'.format(
                     real_clusters_number, summ_stats['clusters_num']))

    real_allocated_nodes_num = int(postgres_actions.run_query(
        db='nailgun',
        query='select count(id) from nodes where cluster_id is not Null;'))
    assert_equal(real_allocated_nodes_num, summ_stats['allocated_nodes_num'],
                 'Real allocated nodes number is {0}, but usage statistics '
                 'says that allocated nodes number is {1}'.format(
                     real_allocated_nodes_num,
                     summ_stats['allocated_nodes_num']))

    real_user_email = json.loads(postgres_actions.run_query(
        db='nailgun', query='select settings from master_node_settings;')
    )['statistics']['email']['value']
    assert_equal(real_user_email, summ_stats['user_information']['email'],
                 "Usage statistics contains incorrect user's email address: "
                 "'{0}', but should be {1}".format(
                     summ_stats['user_information']['email'],
                     real_user_email))

    for cluster in summ_stats['clusters']:
        for node in cluster['nodes']:
            assert_true(len(node['roles']) > 0,
                        "Usage statistics contains nodes without roles: node-"
                        "{0} roles: {1}".format(node['id'], node['roles']))
        assert_equal(len(cluster['nodes']), cluster['nodes_num'],
                     "Usage statistics contains incorrect number of nodes"
                     "assigned to cluster!")
        real_cluster_os = postgres_actions.run_query(
            db="nailgun", query="select operating_system from releases where "
                                "id = (select release_id from clusters where "
                                "id  = {0});".format(cluster['id']))
        assert_equal(real_cluster_os, cluster['release']['os'],
                     "Usage statistics contains incorrect operation system "
                     "that is used for environment with ID '{0}'. Expected: "
                     "'{1}', reported: '{2}'.".format(
                         cluster['id'], real_cluster_os,
                         cluster['release']['os']))

    logger.info("Usage stats were properly saved to collector's database.")


@logwrap
def check_stats_private_info(collector_remote, postgres_actions,
                             master_uuid, _settings):
    def _contain_secret_data(data):
        _has_private_data = False
        # Check that stats doesn't contain private data (e.g.
        # specific passwords, settings, emails)
        for _private in private_data:
            _regex = r'(?P<key>"\S+"): (?P<value>[^:]*"{0}"[^:]*)'.format(
                private_data[_private])
            for _match in re.finditer(_regex, data):
                logger.warning('Found private info in usage statistics using '
                               'pattern: {0}'. format(_regex))
                logger.debug('Usage statistics with private data:\n {0}'.
                             format(data))
                logger.error("Usage statistics contains private info: '{type}:"
                             " {value}'. Part of the stats: {match}".format(
                                 type=_private,
                                 value=private_data[_private],
                                 match=_match.group('key', 'value')))
                _has_private_data = True
        # Check that stats doesn't contain private types of data (e.g. any kind
        # of passwords)
        for _data_type in secret_data_types:
            _regex = (r'(?P<secret>"[^"]*{0}[^"]*": (\{{[^\}}]+\}}|\[[^\]+]\]|'
                      r'"[^"]+"))').format(secret_data_types[_data_type])

            for _match in re.finditer(_regex, data, re.IGNORECASE):
                logger.warning('Found private info in usage statistics using '
                               'pattern: {0}'. format(_regex))
                logger.debug('Usage statistics with private data:\n {0}'.
                             format(data))
                logger.error("Usage statistics contains private info: '{type}:"
                             " {value}'. Part of the stats: {match}".format(
                                 type=_data_type,
                                 value=secret_data_types[_data_type],
                                 match=_match.group('secret')))
                _has_private_data = True
        return _has_private_data

    def _contain_public_ip(data, _used_networks):
        _has_public_ip = False
        _ip_regex = (r'\b((\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])\.){3}'
                     r'(\d|[1-9]\d|1\d{2}|2[0-4]\d|25[0-5])\b')
        _not_public_regex = [
            r'\b10(\.\d{1,3}){3}',
            r'\b127(\.\d{1,3}){3}',
            r'\b169\.254(\.\d{1,3}){2}',
            r'172\.(1[6-9]|2[0-9]|3[0-1])(\.\d{1,3}){2}',
            r'192\.168(\.\d{1,3}){2}',
            r'2(2[4-9]|[3-5][0-9])(\.\d{1,3}){3}'
        ]
        for _match in re.finditer(_ip_regex, data):
            # If IP address isn't public and doesn't belong to defined for
            # deployment pools (e.g. admin, public, storage), then skip it
            if any(re.search(_r, _match.group()) for _r in _not_public_regex) \
                    and not any(IPAddress(str(_match.group())) in
                                IPNetwork(str(net)) for
                                net in _used_networks):
                continue
            logger.debug('Usage statistics with public IP(s):\n {0}'.
                         format(data))
            logger.error('Found public IP in usage statistics: "{0}"'.format(
                _match.group()))
            _has_public_ip = True
        return _has_public_ip

    private_data = {
        'hostname': _settings['HOSTNAME'],
        'dns_domain': _settings['DNS_DOMAIN'],
        'dns_search': _settings['DNS_SEARCH'],
        'dns_upstream': _settings['DNS_UPSTREAM'],
        'fuel_password': (
            _settings['FUEL_ACCESS']['password']
            if _settings['FUEL_ACCESS']['password'] != 'admin'
            else 'DefaultPasswordIsNotAcceptableForSearch'),
        'nailgun_password': _settings['postgres']['nailgun_password'],
        'keystone_password': _settings['postgres']['keystone_password'],
        'ostf_password': _settings['postgres']['ostf_password'],
        'cobbler_password': _settings['cobbler']['password'],
        'astute_password': _settings['astute']['password'],
        'mcollective_password': _settings['mcollective']['password'],
        'keystone_admin_token': _settings['keystone']['admin_token'],
        'keystone_nailgun_password': _settings['keystone']['nailgun_password'],
        'kesytone_ostf_password': _settings['keystone']['ostf_password'],
    }

    secret_data_types = {
        'some_password': 'password',
        'some_login': 'login',
        'some_tenant': 'tenant',
        'some_token': 'token',
        'some_ip': '\bip\b',
        'some_netmask': 'netmask',
        'some_network': 'network\b',
    }

    action_logs = [l.strip() for l in postgres_actions.run_query(
        'nailgun', 'select id from action_logs;').split('\n')]
    sent_stats = str(collector_remote.get_installation_info_data(master_uuid))
    logger.debug('installation structure is {0}'.format(sent_stats))
    used_networks = [POOLS[net_name][0] for net_name in POOLS.keys()]
    has_no_private_data = True

    logger.debug("Looking for private data in the installation structure, "
                 "that was sent to collector")

    if _contain_secret_data(sent_stats) or _contain_public_ip(sent_stats,
                                                              used_networks):
        has_no_private_data = False

    for log_id in action_logs:
        log_data = postgres_actions.run_query(
            'nailgun',
            "select additional_info from action_logs where id = '{0}';".format(
                log_id
            ))
        logger.debug("Looking for private data in action log with ID={0}".
                     format(log_id))
        if _contain_secret_data(log_data) or _contain_public_ip(log_data,
                                                                used_networks):
            has_no_private_data = False

    assert_true(has_no_private_data, 'Found private data in stats, check test '
                                     'output and logs for details.')
    logger.info('Found no private data in logs')


def check_kernel(kernel, expected_kernel):
    assert_equal(kernel, expected_kernel,
                 "kernel version is wrong, it is {0}".format(kernel))


@logwrap
def external_dns_check(ip):
    logger.info("External dns check")
    provided_dns = EXTERNAL_DNS
    logger.debug("provided to test dns is {}".format(provided_dns))
    cluster_dns = []
    for dns in provided_dns:
        ext_dns_ip = ''.join(
            ssh_manager.execute(
                ip=ip,
                cmd="grep {0} /etc/resolv.dnsmasq.conf | "
                    "awk {{'print $2'}}".format(dns)
            )["stdout"]).rstrip()
        cluster_dns.append(ext_dns_ip)
    logger.debug("external dns in conf is {}".format(cluster_dns))
    assert_equal(set(provided_dns), set(cluster_dns),
                 "/etc/resolv.dnsmasq.conf does not contain external dns ip")
    command_hostname = ''.join(
        ssh_manager.execute(ip,
                            "host {0} | awk {{'print $5'}}"
                            .format(PUBLIC_TEST_IP))
        ["stdout"]).rstrip()
    hostname = 'google-public-dns-a.google.com.'
    assert_equal(command_hostname, hostname,
                 "Can't resolve hostname")


def verify_bootstrap_on_node(ip, os_type, uuid=None):
    os_type = os_type.lower()
    if 'ubuntu' not in os_type:
        raise Exception("Only Ubuntu are supported, "
                        "you have chosen {0}".format(os_type))

    logger.info("Verify bootstrap on slave {0}".format(ip))

    cmd = 'cat /etc/*release'
    output = ssh_manager.execute_on_remote(ip, cmd)['stdout_str'].lower()
    assert_true(os_type in output,
                "Slave {0} doesn't use {1} image for bootstrap "
                "after {1} images were enabled, /etc/release "
                "content: {2}".format(ip, os_type, output))
    if not uuid:
        return

    cmd = "cat /etc/nailgun-agent/config.yaml"
    output = yaml.load(ssh_manager.execute_on_remote(ip, cmd)['stdout_str'])
    actual_uuid = output.get("runtime_uuid")
    assert_equal(actual_uuid, uuid,
                 "Actual uuid {0} is not the same as expected {1}"
                 .format(actual_uuid, uuid))


@logwrap
def external_ntp_check(ip, vrouter_vip):
    logger.info("External ntp check")
    provided_ntp = EXTERNAL_NTP
    logger.debug("provided to test ntp is {}".format(provided_ntp))
    cluster_ntp = []
    for ntp in provided_ntp:
        ext_ntp_ip = ''.join(
            ssh_manager.execute(
                ip=ip,
                cmd="awk '/^server +{0}/{{print $2}}' "
                    "/etc/ntp.conf".format(ntp))["stdout"]).rstrip()
        cluster_ntp.append(ext_ntp_ip)
    logger.debug("external ntp in conf is {}".format(cluster_ntp))
    assert_equal(set(provided_ntp), set(cluster_ntp),
                 "/etc/ntp.conf does not contain external ntp ip")
    try:
        wait(
            lambda: is_ntpd_active(ip, vrouter_vip), timeout=120)
    except Exception as e:
        logger.error(e)
        status = is_ntpd_active(ip, vrouter_vip)
        assert_equal(
            status, 1, "Failed updated ntp. "
                       "Exit code is {0}".format(status))


def check_swift_ring(ip):
    for ring in ['object', 'account', 'container']:
        res = ''.join(ssh_manager.execute(
            ip, "swift-ring-builder /etc/swift/{0}.builder".format(
                ring))['stdout'])
        logger.debug("swift ring builder information is {0}".format(res))
        balance = re.search('(\d+.\d+) balance', res).group(1)
        assert_true(float(balance) < 10,
                    "swift ring builder {1} is not ok,"
                    " balance is {0}".format(balance, ring))


def check_oswl_stat(postgres_actions, nailgun_actions,
                    remote_collector, master_uid,
                    operation='current',
                    resources=None):
    if resources is None:
        resources = [
            'vm', 'flavor', 'volume', 'image', 'tenant', 'keystone_user'
        ]
    logger.info("Checking that all resources were collected...")
    expected_resource_count = {
        'current':
        {'vm': 0,
         'flavor': 6,
         'volume': 0,
         'image': 0,
         'tenant': 2,
         'keystone_user': 8
         },
        'modified':
        {'vm': 0,
         'flavor': 0,
         'volume': 0,
         'image': 0,
         'tenant': 0,
         'keystone_user': 0
         },
        'removed':
        {'vm': 0,
         'flavor': 0,
         'volume': 0,
         'image': 0,
         'tenant': 0,
         'keystone_user': 0
         }
    }
    for resource in resources:
        q = "select resource_data from oswl_stats where" \
            " resource_type = '\"'\"'{0}'\"'\"';".format(resource)

        # pylint: disable=undefined-loop-variable
        def get_resource():
            result = postgres_actions.run_query('nailgun', q)
            logger.debug("resource state is {}".format(result))
            if not result:
                return False
            return (
                len(json.loads(result)[operation]) >
                expected_resource_count[operation][resource])
        # pylint: enable=undefined-loop-variable

        wait(get_resource, timeout=10,
             timeout_msg="resource {} wasn't updated in db".format(resource))
        q_result = postgres_actions.run_query('nailgun', q)
        assert_true(q_result.strip() is not None,
                    "Resource {0} is absent in 'oswl_stats' table, "
                    "please check /var/log/nailgun/oswl_{0}"
                    "_collectord.log on Fuel admin node for details."
                    .format(resource))
        resource_data = json.loads(q_result)

        logger.debug('db return {0}'.format(resource_data))
        assert_true(len(resource_data['added']) >
                    expected_resource_count[operation][resource],
                    "resource {0} wasn't added,"
                    " added is {1}".format(resource, resource_data['added']))
        assert_true(len(resource_data[operation]) >
                    expected_resource_count[operation][resource],
                    "number of resources in current {0},"
                    " expected is {1}".format(len(resource_data[operation]),
                                              expected_resource_count[
                                                  operation][resource]))

    # check stat on collector side

    def are_logs_sent():
        sent_logs = postgres_actions.count_sent_action_logs(
            table='oswl_stats')
        result = sent_logs == 6
        if not result:
            nailgun_actions.force_fuel_stats_sending()
        return result

    wait(are_logs_sent, timeout=20,
         timeout_msg='Logs status was not changed to sent in db')
    sent_logs_count = postgres_actions.count_sent_action_logs(
        table='oswl_stats')
    logger.info("Number of logs that were sent to collector: {}".format(
        sent_logs_count
    ))
    logger.debug('oswls are {}'.format(remote_collector.get_oswls(master_uid)))
    logs = remote_collector.get_oswls(master_uid)['paging_params']['total']
    logger.info("Number of logs that were saved"
                " on collector: {}".format(logs))
    assert_true(sent_logs_count <= int(logs),
                ("Count of action logs in Nailgun DB ({0}) is bigger than on "
                 "Collector ({1}), but should be less or equal").format(
                    sent_logs_count, logs))
    for resource in resources:
        resource_data = remote_collector.get_oswls_by_resource_data(
            master_uid, resource)

        logger.debug('resource data on'
                     ' collector is {0}'.format(resource_data))
        assert_true(len(resource_data['added']) >
                    expected_resource_count[operation][resource],
                    "resource {0} wasn't added,"
                    " added is {1}".format(resource, resource_data['added']))
        assert_true(len(resource_data[operation]) >
                    expected_resource_count[operation][resource],
                    "number of resources in current {0},"
                    " expected is {1}".format(len(resource_data[operation]),
                                              expected_resource_count[
                                                  operation][resource]))

    logger.info("OSWL stats were properly saved to collector's database.")


@logwrap
def check_ping(ip, host, deadline=10, size=56, timeout=1, interval=1):
    """Check network connectivity from remote to host using ICMP (ping)
    :param ip: remote ip
    :param host: string IP address or host/domain name
    :param deadline: time in seconds before ping exits
    :param size: size of data to be sent
    :param timeout: time to wait for a response, in seconds
    :param interval: wait interval seconds between sending each packet
    :return: bool: True if ping command
    """
    ssh_manager = SSHManager()
    cmd = ("ping -W {timeout} -i {interval} -s {size} -c 1 -w {deadline} "
           "{host}".format(host=host,
                           size=size,
                           timeout=timeout,
                           interval=interval,
                           deadline=deadline))
    res = ssh_manager.execute(ip, cmd)
    return int(res['exit_code']) == 0


@logwrap
def check_neutron_dhcp_lease(ip, instance_ip, instance_mac,
                             dhcp_server_ip, dhcp_port_tag):
    """Check if the DHCP server offers a lease for a client with the specified
       MAC address
       :param ip: remote IP
       :param str instance_ip: IP address of instance
       :param str instance_mac: MAC address that will be checked
       :param str dhcp_server_ip: IP address of DHCP server for request a lease
       :param str dhcp_port_tag: OVS port tag used for access the DHCP server
       :return bool: True if DHCP lease for the 'instance_mac' was obtained
    """
    logger.debug("Checking DHCP server {0} for lease {1} with MAC address {2}"
                 .format(dhcp_server_ip, instance_ip, instance_mac))
    ovs_port_name = 'tapdhcptest1'
    ovs_cmd = '/usr/bin/ovs-vsctl --timeout=10 --oneline --format=json -- '
    ovs_add_port_cmd = ("--if-exists del-port {0} -- "
                        "add-port br-int {0} -- "
                        "set Interface {0} type=internal -- "
                        "set Port {0} tag={1}"
                        .format(ovs_port_name, dhcp_port_tag))
    ovs_del_port_cmd = ("--if-exists del-port {0}".format(ovs_port_name))

    # Add an OVS interface with a tag for accessing the DHCP server
    ssh_manager.execute_on_remote(ip, ovs_cmd + ovs_add_port_cmd)

    # Set to the created interface the same MAC address
    # that was used for the instance.
    ssh_manager.execute_on_remote(
        ip, "ifconfig {0} hw ether {1}".format(ovs_port_name,
                                               instance_mac))
    ssh_manager.execute_on_remote(ip, "ifconfig {0} up".format(ovs_port_name))

    # Perform a 'dhcpcheck' request to check if the lease can be obtained
    lease = ssh_manager.execute_on_remote(
        ip=ip,
        cmd="dhcpcheck request {0} {1} --range_start {2} "
            "--range_end 255.255.255.255 | fgrep \" {1} \""
            .format(ovs_port_name, dhcp_server_ip, instance_ip))['stdout']

    # Remove the OVS interface
    ssh_manager.execute_on_remote(ip, ovs_cmd + ovs_del_port_cmd)

    logger.debug("DHCP server answer: {}".format(lease))
    return ' ack ' in lease


def is_ntpd_active(ip, ntpd_ip):
    cmd = 'ntpdate -d -p 4 -t 0.2 -u {0}'.format(ntpd_ip)
    return not ssh_manager.execute(ip, cmd)['exit_code']


def check_repo_managment(ip):
    """Check repo management

    run 'yum -y clean all && yum check-update' or
        'apt-get clean all && apt-get update' exit code should be 0

    :type ip: node ip
        :rtype Dict
    """
    if OPENSTACK_RELEASE == OPENSTACK_RELEASE_UBUNTU:
        cmd = "apt-get clean all && apt-get update > /dev/null"
    else:
        cmd = "yum -y clean all && yum check-update > /dev/null"
    ssh_manager.execute_on_remote(
        ip=ip,
        cmd=cmd
    )


def check_public_ping(ip):
    """ Check if ping public vip
    :type ip: node ip
    """
    cmd = ('ruby /etc/puppet/modules/osnailyfacter/'
           'modular/virtual_ips/public_vip_ping_post.rb')
    ssh_manager.execute_on_remote(
        ip=ip,
        cmd=cmd,
        err_msg='Public ping check failed'
    )


def check_cobbler_node_exists(ip, node_id):
    """Check node with following node_id
    is present in the cobbler node list
    :param ip: node ip
    :param node_id: fuel node id
    :return: bool: True if exit code of command (node) == 0
    """
    logger.debug("Check that cluster contains node with ID:{0} ".
                 format(node_id))
    node = ssh_manager.execute(
        ip=ip,
        cmd='bash -c "cobbler system list" | grep '
            '-w "node-{0}"'.format(node_id)
    )
    return int(node['exit_code']) == 0


def check_cluster_presence(cluster_id, postgres_actions):
    logger.debug("Check cluster presence")
    query_result = postgres_actions.run_query(
        db='nailgun',
        query="select id from clusters where id={0}".format(cluster_id))
    return str(cluster_id) in query_result


def check_haproxy_backend(ip,
                          services=None, nodes=None,
                          ignore_services=None, ignore_nodes=None):
    """Check DOWN state of HAProxy backends. Define names of service or nodes
    if need check some specific service or node. Use ignore_services for ignore
    service status on all nodes. Use ignore_nodes for ignore all services on
    all nodes. Ignoring has a bigger priority.

    :type ip: node ip
    :type services: List
    :type nodes: List
    :type ignore_services: List
    :type ignore_nodes: List
        :rtype: Dict
    """
    cmd = 'haproxy-status | egrep -v "BACKEND|FRONTEND" | grep "DOWN"'

    positive_filter = (services, nodes)
    negative_filter = (ignore_services, ignore_nodes)
    grep = ['|egrep "{}"'.format('|'.join(n)) for n in positive_filter if n]
    grep.extend(
        ['|egrep -v "{}"'.format('|'.join(n)) for n in negative_filter if n])

    result = ssh_manager.execute(
        ip=ip,
        cmd="{}{}".format(cmd, ''.join(grep))
    )
    return result


def check_log_lines_order(ip, log_file_path, line_matcher):
    """Read log file and check that lines order are same as strings in list

    :param ip: ip of node in str format
    :param log_file_path: path to log file
    :param line_matcher: list of strings to search
    """
    check_file_exists(ip, path=log_file_path)

    previous_line_pos = 1
    previous_line = None
    for current_line in line_matcher:
        cmd = 'tail -n +{0} {1} | grep -n "{2}"'\
            .format(previous_line_pos, log_file_path, current_line)

        result = ssh_manager.execute_on_remote(
            ip=ip,
            cmd=cmd,
            err_msg="Line '{0}' not found after line '{1}' in the file "
                    "'{2}'.".format(current_line, previous_line, log_file_path)

        )

        # few lines found case
        assert_equal(1,
                     len(result['stdout']),
                     "Found {0} lines like {1} but should be only 1 in {2}"
                     " Command '{3}' executed with exit_code='{4}'\n"
                     "stdout:\n* {5} *\n"
                     "stderr:\n'* {6} *\n"
                     .format(len(result['stdout']),
                             current_line,
                             log_file_path,
                             cmd,
                             result['exit_code'],
                             '\n'.join(result['stdout']),
                             '\n'.join(result['stderr'])))

        current_line_pos = int(result['stdout'][0].split(':')[0])

        previous_line_pos += current_line_pos
        previous_line = current_line


def check_hiera_hosts(nodes, cmd):
    hiera_hosts = []
    for node in nodes:
        result = ssh_manager.execute_on_remote(
            ip=node['ip'],
            cmd=cmd
        )['stdout_str']
        hosts = result.split(',')
        logger.debug("hosts on {0} are {1}".format(node['hostname'], hosts))

        if not hiera_hosts:
            hiera_hosts = hosts
            continue
        else:
            assert_true(set(hosts) == set(hiera_hosts),
                        'Hosts on node {0} differ from'
                        ' others'.format(node['hostname']))


def check_client_smoke(ip):
    fuel_output = ssh_manager.execute(
        ip=ip,
        cmd='fuel env list'
    )['stdout'][2].split('|')[2].strip()
    fuel_2_output = ssh_manager.execute(
        ip=ip,
        cmd='fuel2 env list'
    )['stdout'][3].split('|')[3].strip()
    assert_equal(fuel_output, fuel_2_output,
                 "The fuel: {0} and fuel2: {1} outputs are not equal")


def check_offload(ip, interface, offload_type):
    command = "ethtool --show-offload {0} |" \
              " awk '/{1}/ {{print $2}}'".format(interface, offload_type)

    result = ssh_manager.execute_on_remote(
        ip=ip,
        cmd=command,
        err_msg="Failed to get Offload {0} "
                "on node {1}".format(offload_type, ip)
    )
    return result['stdout_str']


def check_get_network_data_over_cli(ip, cluster_id, path):
    logger.info("Download network data over cli")
    cmd = 'fuel --debug --env {0} network --dir {1} --json -d'.format(
        cluster_id, path)
    ssh_manager.execute_on_remote(
        ip=ip,
        cmd=cmd,
        err_msg='Failed to upload network data'
    )


def check_update_network_data_over_cli(ip, cluster_id, path):
    logger.info("Upload network data over cli")
    cmd = 'fuel --debug --env {0} network --dir {1} --json -u'.format(
        cluster_id, path)
    ssh_manager.execute_on_remote(
        ip=ip,
        cmd=cmd,
        err_msg='Failed to upload network data'
    )


def check_plugin_path_env(var_name, plugin_path):
    assert_true(
        plugin_path,
        '{var_name:s} variable is not set or set incorrectly: '
        '{plugin_path!r}'.format(
            var_name=var_name,
            plugin_path=plugin_path)
    )
    assert_true(
        os.path.exists(plugin_path),
        'File {plugin_path:s} (variable: {var_name:s}) does not exists!'
        ''.format(plugin_path=plugin_path, var_name=var_name)
    )


def incomplete_tasks(tasks, cluster_id=None):
    def get_last_tasks():
        last_tasks = {}
        for tsk in tasks:
            if cluster_id is not None and cluster_id != tsk['cluster']:
                continue
            if (tsk['cluster'], tsk['name']) not in last_tasks:
                last_tasks[(tsk['cluster'], tsk['name'])] = tsk
        return last_tasks

    deploy_tasks = {}
    not_ready_tasks = {}
    allowed_statuses = {'ready', 'skipped'}

    for (task_cluster, task_name), task in get_last_tasks().items():
        if task_name == 'deployment':
            deploy_tasks[task['cluster']] = task['id']
        if task['status'] not in allowed_statuses:
            if task_cluster not in not_ready_tasks:
                not_ready_tasks[task_cluster] = []
            not_ready_tasks[task_cluster].append(task)

    return not_ready_tasks, deploy_tasks


def incomplete_deploy(deployment_tasks):
    allowed_statuses = {'ready', 'skipped'}
    not_ready_deploy = {}

    for cluster_id, tasks in deployment_tasks.items():
        not_ready_jobs = {}
        for task in filter(
                lambda tsk: tsk['status'] not in allowed_statuses,
                tasks):
            if task['node_id'] not in not_ready_jobs:
                not_ready_jobs[task['node_id']] = []
            not_ready_jobs[task['node_id']].append(task)
        if not_ready_jobs:
            not_ready_deploy[cluster_id] = not_ready_jobs

    return not_ready_deploy


def fail_deploy(not_ready_transactions):
    if len(not_ready_transactions) > 0:
        cluster_info_template = "\n\tCluster ID: {cluster}{info}\n"
        task_details_template = (
            "\n"
            "\t\t\tTask name: {deployment_graph_task_name}\n"
            "\t\t\t\tStatus: {status}\n"
            "\t\t\t\tStart:  {time_start}\n"
            "\t\t\t\tEnd:    {time_end}\n"
        )

        failure_text = 'Not all deployments tasks completed: {}'.format(
            ''.join(
                cluster_info_template.format(
                    cluster=cluster,
                    info="".join(
                        "\n\t\tNode: {node_id}{details}\n".format(
                            node_id=node_id,
                            details="".join(
                                task_details_template.format(**task)
                                for task in sorted(
                                    tasks,
                                    key=lambda item: item['status'])
                            ))
                        for node_id, tasks in sorted(records.items())
                    ))
                for cluster, records in sorted(not_ready_transactions.items())
            ))
        logger.error(failure_text)
        assert_true(len(not_ready_transactions) == 0, failure_text)


@logwrap
def check_produced_vms(os_conn, vms_data, ip_jump_host=None):
    """Check VMs which were produced by
    method helpers.os_actions.OpenStackActions.boot_parameterized_vms

    :param os_conn: an instance of class helpers.common.Common
    :param vms_data: a list of produced vms data dicts, result of
    method helpers.os_actions.OpenStackActions.boot_parameterized_vms
    :param ip_jump_host: a str, ip of jump host
    """
    def check_instance_status_by_id(instance_id):
        server = os_conn.nova.servers.get(instance_id)
        status = os_conn.get_instance_detail(server).status
        logger.debug('Instance with id {!r} has status {!r}'
                     .format(instance_id, status))
        return status != "ACTIVE"

    def check_volume_status(vol_id, srv_id, bootable=False):
        volume = os_conn.cinder.volumes.get(vol_id)
        logger.debug('Volume with id {!r} has status {!r}'
                     .format(vol_id, volume.status))
        bootable_fail = False
        if bootable:
            logger.debug('Volume with id {!r} should be '
                         '"bootable", actually {!r}'
                         .format(vol_id, volume.bootable))
            bootable_fail = volume.bootable == 'false'

        if not volume.attachments:
            logger.warning('Volume {!r} is not attached to VM {!r}. Please, '
                           'check Openstack logs'.format(vol_id, srv_id))
            return False
        actual_server_id = volume.attachments[0]['server_id']

        logger.debug('Volume with id {!r} should be attached to '
                     'instance {!r}, actually attached to {!r}'
                     .format(vol_id, srv_id, actual_server_id))
        return volume.status != "in-use" \
            or bootable_fail or srv_id != actual_server_id

    def get_floating_ip_of_vm(vm_dict):
        addresses = vm_dict['addresses']
        for ip_address in addresses.values()[0]:
            if ip_address['OS-EXT-IPS:type'] == 'floating':
                logger.debug('Vm {!r} has floating ip {!r}'
                             .format(vm_dict['id'], ip_address['addr']))
                return ip_address['addr']
        logger.debug('Vm {!r} has not floating ip'.format(vm_dict['id']))

    def check_ssh_call_by_floating_ip(ip, ip_jump_host):
        if not ip_jump_host:
            logger.warning('IP of jump host was not passed! There is not the '
                           'possibility to check availability instance by SSH')
            return
        cirros_auth = SSHAuth(**SSH_IMAGE_CREDENTIALS)
        cmd = 'ls testfile'
        rmt = ssh_manager.get_remote(ip_jump_host)
        res = rmt.execute_through_host(
            hostname=ip,
            cmd=cmd,
            auth=cirros_auth
        )
        logger.debug('Command {!r} was executed on {!r}. The execution'
                     ' details: {!r}'.format(cmd, ip, res))
        return res.exit_code != 0

    instances = [x['server'] for x in vms_data
                 if 'server' in x]
    logger.info('Check instances status...')
    broken_vms = []
    for instance in instances:
        if check_instance_status_by_id(instance['id']):
            broken_vms.append(instance['id'])
    assert_false(broken_vms, 'Vms : {!r} are not in "ACTIVE" state! Please, '
                             'see sys_test.log for the more details'
                             .format(broken_vms))

    bootable_volumes = dict([
        (x['id'],
         x['os-extended-volumes:volumes_attached'][0]['id'])
        for x in instances
        if x['os-extended-volumes:volumes_attached']
    ])

    broken_bootable_volumes = []
    if bootable_volumes:
        logger.info('Check bootable volumes ...')
    for inst_id, vol_id in bootable_volumes.items():
        if check_volume_status(vol_id, inst_id, bootable=True):
            broken_bootable_volumes.append(vol_id)
    assert_false(broken_bootable_volumes,
                 'Volumes: {!r} are in invalid state. Please, see sys_test.log'
                 ' for more details'.format(broken_bootable_volumes))

    attached_volumes = [x['attached_volume'] for x in vms_data
                        if 'attached_volume' in x]
    broken_attached_volumes = []
    if attached_volumes:
        logger.info('Check attached volumes ...')
    for volume in attached_volumes:
        if check_volume_status(volume['id'],
                               volume['attachments'][0]['server_id']):
            broken_attached_volumes.append(volume['id'])
    assert_false(broken_attached_volumes,
                 'Volumes: {!r} are in invalid state. Please, see sys_test.log'
                 ' for more details'.format(broken_attached_volumes))

    floating_ips = [get_floating_ip_of_vm(x) for x in instances
                    if get_floating_ip_of_vm(x)]
    broken_access_by_floating = []
    if floating_ips:
        logger.info('Check availability VMs by floating ip ...')
    for ip in floating_ips:
        if check_ssh_call_by_floating_ip(ip, ip_jump_host):
            broken_access_by_floating.append(ip)
    assert_false(broken_access_by_floating,
                 'The access to instances is broken by the following '
                 'floating ips: {!r}. Please, see sys_test.log '
                 'for more details'.format(broken_access_by_floating))
