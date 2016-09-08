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


import os
import time

_boolean_states = {'1': True, 'yes': True, 'true': True, 'on': True,
                   '0': False, 'no': False, 'false': False, 'off': False}


def get_var_as_bool(name, default):
    value = os.environ.get(name, '')
    return _boolean_states.get(value.lower(), default)

# Default timezone for clear logging
TIME_ZONE = 'UTC'

ENV_NAME = os.environ.get("ENV_NAME", "fuel_system_test")
VIRTUAL_ENV = os.environ.get("VIRTUAL_ENV", "")

ACPI_ENABLE = get_var_as_bool('DRIVER_ENABLE_ACPI', False)

nic_name_mask = 'enp0s{}' if not ACPI_ENABLE else 'ens{}'

INTERFACES_DICT = {
    'eth0': os.environ.get('IFACE_0', nic_name_mask.format(3)),
    'eth1': os.environ.get('IFACE_1', nic_name_mask.format(4)),
    'eth2': os.environ.get('IFACE_2', nic_name_mask.format(5)),
    'eth3': os.environ.get('IFACE_3', nic_name_mask.format(6)),
    'eth4': os.environ.get('IFACE_4', nic_name_mask.format(7)),
    'eth5': os.environ.get('IFACE_5', nic_name_mask.format(8)),
}


# NOTE(akostrikov) The method is here to avoid problems with imports
# Refactor when additional logic is needed like info from master node/devops.
def iface_alias(interface_name):
    return INTERFACES_DICT[interface_name]

ISO_PATH = os.environ.get('ISO_PATH')
LOGS_DIR = os.environ.get('LOGS_DIR', os.getcwd())
# cdrom or usb
ADMIN_BOOT_DEVICE = os.environ.get('ADMIN_BOOT_DEVICE', 'cdrom')
ISO_MIRANTIS_FEATURE_GROUP = get_var_as_bool(
    'ISO_MIRANTIS_FEATURE_GROUP',
    False)
ISO_LABEL = 'Mirantis_Fuel' if ISO_MIRANTIS_FEATURE_GROUP else 'OpenStack_Fuel'
SHOW_FUELMENU = get_var_as_bool('SHOW_FUELMENU', False)
DNS = os.environ.get('DNS', '8.8.8.8')
PUBLIC_TEST_IP = os.environ.get('PUBLIC_TEST_IP', '8.8.8.8')

FORCE_HTTPS_MASTER_NODE = get_var_as_bool('FORCE_HTTPS_MASTER_NODE', False)
DISABLE_SSL = get_var_as_bool('DISABLE_SSL', False)
VERIFY_SSL = get_var_as_bool('VERIFY_SSL', False)
SSL_CN = os.environ.get('SSL_CN', 'public.fuel.local')
SSL_CERTS_DIR = os.environ.get('SSL_CERTS_DIR', os.getcwd())
if not os.path.exists(SSL_CERTS_DIR):
    os.makedirs(SSL_CERTS_DIR)
USER_OWNED_CERT = get_var_as_bool('USER_OWNED_CERT', True)
PATH_TO_CERT = os.environ.get('PATH_TO_CERT', os.path.join(
    SSL_CERTS_DIR, 'ca.crt'))
PATH_TO_PEM = os.environ.get('PATH_TO_PEM', os.path.join(
    SSL_CERTS_DIR, 'ca.pem'))

OPENSTACK_RELEASE_CENTOS = 'centos'
OPENSTACK_RELEASE_UBUNTU = os.environ.get('OPENSTACK_RELEASE_UBUNTU',
                                          'Ubuntu 14.04').lower()
OPENSTACK_RELEASE_UBUNTU_UCA = os.environ.get(
    'OPENSTACK_RELEASE_UBUNTU_UCA', 'Ubuntu+UCA 14.04').lower()
OPENSTACK_RELEASE = os.environ.get(
    'OPENSTACK_RELEASE', OPENSTACK_RELEASE_UBUNTU).lower()

RELEASE_VERSION = os.environ.get('RELEASE_VERSION', "mitaka")

# FIXME(mattmymo): Update CI jobs to use 'Ubuntu 14.04' for OPENSTACK_RELEASE
if OPENSTACK_RELEASE == 'ubuntu':
    OPENSTACK_RELEASE = OPENSTACK_RELEASE_UBUNTU

DEPLOYMENT_MODE_SIMPLE = "multinode"
DEPLOYMENT_MODE_HA = "ha_compact"
DEPLOYMENT_MODE = os.environ.get("DEPLOYMENT_MODE", DEPLOYMENT_MODE_HA)
DEPLOYMENT_TIMEOUT = int(os.environ.get("DEPLOYMENT_TIMEOUT", 7800))
DEPLOYMENT_RETRIES = int(os.environ.get("DEPLOYMENT_RETRIES", 1))
BOOTSTRAP_TIMEOUT = int(os.environ.get("BOOTSTRAP_TIMEOUT", 900))
WAIT_FOR_PROVISIONING_TIMEOUT = int(os.environ.get(
    "WAIT_FOR_PROVISIONING_TIMEOUT", 1200))

ADMIN_NODE_SETUP_TIMEOUT = os.environ.get("ADMIN_NODE_SETUP_TIMEOUT", 30)
ADMIN_NODE_BOOTSTRAP_TIMEOUT = os.environ.get(
    "ADMIN_NODE_BOOTSTRAP_TIMEOUT", 3600)


HARDWARE = {
    "admin_node_memory": os.environ.get("ADMIN_NODE_MEMORY", 3072),
    "admin_node_cpu": os.environ.get("ADMIN_NODE_CPU", 2),
    "slave_node_cpu": os.environ.get("SLAVE_NODE_CPU", 1),
    "numa_nodes": os.environ.get("NUMA_NODES", 0),
}
if OPENSTACK_RELEASE_UBUNTU in OPENSTACK_RELEASE:
    slave_mem_default = 2560
else:
    slave_mem_default = 2048
HARDWARE["slave_node_memory"] = int(
    os.environ.get("SLAVE_NODE_MEMORY", slave_mem_default))
NODE_VOLUME_SIZE = int(os.environ.get('NODE_VOLUME_SIZE', 50))
NODES_COUNT = os.environ.get('NODES_COUNT', 10)

MULTIPATH = get_var_as_bool('MULTIPATH', False)
SLAVE_MULTIPATH_DISKS_COUNT = int(os.environ.get('SLAVE_MULTIPATH_DISKS_COUNT',
                                                 '0'))
MULTIPATH_TEMPLATE = os.environ.get(
    'MULTIPATH_TEMPLATE',
    os.path.join(
        os.getcwd(),
        'system_test/tests_templates/tests_configs/multipath_3_nodes.yaml'))
if MULTIPATH and not SLAVE_MULTIPATH_DISKS_COUNT:
    os.environ.setdefault('SLAVE_MULTIPATH_DISKS_COUNT', '2')
    SLAVE_MULTIPATH_DISKS_COUNT = int(
        os.environ.get('SLAVE_MULTIPATH_DISKS_COUNT'))

MULTIPLE_NETWORKS = get_var_as_bool('MULTIPLE_NETWORKS', False)
MULTIPLE_NETWORKS_TEMPLATE = os.environ.get(
    'MULTIPLE_NETWORKS_TEMPLATE',
    os.path.join(os.getcwd(),
                 'system_test/tests_templates/tests_configs/multirack.yaml'))

USE_HAPROXY_TEMPLATE = get_var_as_bool("USE_HAPROXY_TEMPLATE", False)
EXTERNAL_HAPROXY_TEMPLATE = os.environ.get(
    'EXTERNAL_HAPROXY_TEMPLATE',
    os.path.join(os.getcwd(),
                 'system_test/tests_templates/tests_configs/'
                 'external_haproxy.yaml'))

if MULTIPLE_NETWORKS:
    NODEGROUPS = (
        {
            'name': 'default',
            'networks': {
                'fuelweb_admin': 'admin',
                'public': 'public',
                'management': 'management',
                'storage': 'storage',
                'private': 'private'
            }
        },
        {
            'name': 'group-custom-1',
            'networks': {
                'fuelweb_admin': 'admin2',
                'public': 'public2',
                'management': 'management2',
                'storage': 'storage',
                'private': 'private2'
            }
        },
        {
            'name': 'group-custom-2',
            'networks': {
                'fuelweb_admin': 'admin3',
                'public': 'public3',
                'management': 'management3',
                'storage': 'storage',
                'private': 'private3'
            }
        }
    )
    FORWARD_DEFAULT = os.environ.get('FORWARD_DEFAULT', 'route')
    ADMIN_FORWARD = os.environ.get('ADMIN_FORWARD', 'nat')
    PUBLIC_FORWARD = os.environ.get('PUBLIC_FORWARD', 'nat')
else:
    NODEGROUPS = ()
    FORWARD_DEFAULT = os.environ.get('FORWARD_DEFAULT', None)
    ADMIN_FORWARD = os.environ.get('ADMIN_FORWARD', FORWARD_DEFAULT or 'nat')
    PUBLIC_FORWARD = os.environ.get('PUBLIC_FORWARD', FORWARD_DEFAULT or 'nat')

MGMT_FORWARD = os.environ.get('MGMT_FORWARD', FORWARD_DEFAULT)
PRIVATE_FORWARD = os.environ.get('PRIVATE_FORWARD', FORWARD_DEFAULT)
STORAGE_FORWARD = os.environ.get('STORAGE_FORWARD', FORWARD_DEFAULT)

DEFAULT_INTERFACE_ORDER = 'admin,public,management,private,storage'
INTERFACE_ORDER = os.environ.get('INTERFACE_ORDER',
                                 DEFAULT_INTERFACE_ORDER).split(',')

FORWARDING = {
    'admin': ADMIN_FORWARD,
    'public': PUBLIC_FORWARD,
    'management': MGMT_FORWARD,
    'private': PRIVATE_FORWARD,
    'storage': STORAGE_FORWARD,
}

DHCP = {
    'admin': False,
    'public': False,
    'management': False,
    'private': False,
    'storage': False,
}

INTERFACES = {
    'admin': iface_alias('eth0'),
    'public': iface_alias('eth1'),
    'management': iface_alias('eth2'),
    'private': iface_alias('eth3'),
    'storage': iface_alias('eth4'),
}

# May be one of virtio, e1000, pcnet, rtl8139
INTERFACE_MODEL = os.environ.get('INTERFACE_MODEL', 'virtio')

POOL_DEFAULT = os.environ.get('POOL_DEFAULT', '10.109.0.0/16:24')
POOL_ADMIN = os.environ.get('POOL_ADMIN', POOL_DEFAULT)
POOL_PUBLIC = os.environ.get('POOL_PUBLIC', POOL_DEFAULT)
POOL_MANAGEMENT = os.environ.get('POOL_MANAGEMENT', POOL_DEFAULT)
POOL_PRIVATE = os.environ.get('POOL_PRIVATE', POOL_DEFAULT)
POOL_STORAGE = os.environ.get('POOL_STORAGE', POOL_DEFAULT)

DEFAULT_POOLS = {
    'admin': POOL_ADMIN,
    'public': POOL_PUBLIC,
    'management': POOL_MANAGEMENT,
    'private': POOL_PRIVATE,
    'storage': POOL_STORAGE,
}

POOLS = {
    'admin': os.environ.get(
        'PUBLIC_POOL',
        DEFAULT_POOLS.get('admin')).split(':'),
    'public': os.environ.get(
        'PUBLIC_POOL',
        DEFAULT_POOLS.get('public')).split(':'),
    'management': os.environ.get(
        'PRIVATE_POOL',
        DEFAULT_POOLS.get('management')).split(':'),
    'private': os.environ.get(
        'INTERNAL_POOL',
        DEFAULT_POOLS.get('private')).split(':'),
    'storage': os.environ.get(
        'NAT_POOL',
        DEFAULT_POOLS.get('storage')).split(':'),
}

if MULTIPLE_NETWORKS:
    FORWARDING['admin2'] = ADMIN_FORWARD
    FORWARDING['public2'] = PUBLIC_FORWARD
    FORWARDING['management2'] = MGMT_FORWARD
    FORWARDING['private2'] = PRIVATE_FORWARD
    FORWARDING['storage2'] = STORAGE_FORWARD

    DHCP['admin2'] = False
    DHCP['public2'] = False
    DHCP['management2'] = False
    DHCP['private2'] = False
    DHCP['storage2'] = False

    INTERFACES['admin2'] = iface_alias('eth5')

    POOL_DEFAULT2 = os.environ.get('POOL_DEFAULT2', '10.108.0.0/16:24')
    POOL_ADMIN2 = os.environ.get('POOL_ADMIN2', POOL_DEFAULT2)
    POOL_PUBLIC2 = os.environ.get('POOL_PUBLIC2', POOL_DEFAULT2)
    POOL_MANAGEMENT2 = os.environ.get('POOL_MANAGEMENT', POOL_DEFAULT2)
    POOL_PRIVATE2 = os.environ.get('POOL_PRIVATE', POOL_DEFAULT2)
    POOL_STORAGE2 = os.environ.get('POOL_STORAGE', POOL_DEFAULT2)

    CUSTOM_POOLS = {
        'admin2': POOL_ADMIN2,
        'public2': POOL_PUBLIC2,
        'management2': POOL_MANAGEMENT2,
        'private2': POOL_PRIVATE2,
        'storage2': POOL_STORAGE2,
    }

    POOLS['admin2'] = os.environ.get(
        'PUBLIC_POOL2',
        CUSTOM_POOLS.get('admin2')).split(':')
    POOLS['public2'] = os.environ.get(
        'PUBLIC_POOL2',
        CUSTOM_POOLS.get('public2')).split(':')
    POOLS['management2'] = os.environ.get(
        'PUBLIC_POOL2',
        CUSTOM_POOLS.get('management2')).split(':')
    POOLS['private2'] = os.environ.get(
        'PUBLIC_POOL2',
        CUSTOM_POOLS.get('private2')).split(':')
    POOLS['storage2'] = os.environ.get(
        'PUBLIC_POOL2',
        CUSTOM_POOLS.get('storage2')).split(':')

    CUSTOM_INTERFACE_ORDER = os.environ.get(
        'CUSTOM_INTERFACE_ORDER',
        'admin2,public2,management2,private2,storage2')
    INTERFACE_ORDER.extend(CUSTOM_INTERFACE_ORDER.split(','))

BONDING = get_var_as_bool("BONDING", False)

BONDING_INTERFACES = {
    'admin': [iface_alias('eth0')],
    'public': [
        iface_alias('eth1'),
        iface_alias('eth2'),
        iface_alias('eth3'),
        iface_alias('eth4')
    ]
}

NETWORK_MANAGERS = {
    'flat': 'FlatDHCPManager',
    'vlan': 'VlanManager'
}

NETWORK_PROVIDERS = [
    'neutron',
    'nova_network'
]

NEUTRON = 'neutron'

NEUTRON_SEGMENT = {
    'gre': 'gre',
    'vlan': 'vlan',
    'tun': 'tun'
}

NEUTRON_SEGMENT_TYPE = NEUTRON_SEGMENT.get(
    os.environ.get('NEUTRON_SEGMENT_TYPE', None), None)

# Path to a network template dedicated for reduced footprint environments
RF_NET_TEMPLATE = os.environ.get("RF_NET_TEMPLATE", None)

USE_ALL_DISKS = get_var_as_bool('USE_ALL_DISKS', True)

UPLOAD_MANIFESTS = get_var_as_bool('UPLOAD_MANIFESTS', False)
SYNC_DEPL_TASKS = get_var_as_bool('SYNC_DEPL_TASKS', False)
UPLOAD_MANIFESTS_PATH = os.environ.get(
    'UPLOAD_MANIFESTS_PATH', '~/git/fuel/deployment/puppet/')
SITEPP_FOR_UPLOAD = os.environ.get(
    'SITEPP_PATH', '/etc/puppet/modules/osnailyfacter/examples/site.pp')

GERRIT_REFSPEC = os.environ.get('GERRIT_REFSPEC')
PATCH_PATH = os.environ.get(
    'PATCH_PATH', '/tmp/fuel-ostf')

KVM_USE = get_var_as_bool('KVM_USE', False)
VCENTER_USE = get_var_as_bool('VCENTER_USE', False)
DEBUG_MODE = get_var_as_bool('DEBUG_MODE', True)

# vCenter tests
VCENTER_IP = os.environ.get('VCENTER_IP')
VCENTER_USERNAME = os.environ.get('VCENTER_USERNAME')
VCENTER_PASSWORD = os.environ.get('VCENTER_PASSWORD')
VCENTER_DATACENTER = os.environ.get('VC_DATACENTER')
VCENTER_DATASTORE = os.environ.get('VC_DATASTORE')
VMWARE_IMG_URL = os.environ.get('VMWARE_IMG_URL')
VMWARE_IMG_NAME = os.environ.get('VMWARE_IMG_NAME')
VMWARE_IMG_LOGIN = os.environ.get('VMWARE_IMG_LOGIN')
VMWARE_IMG_PASSWORD = os.environ.get('VMWARE_IMG_PASSWORD')

# Services tests
SERVTEST_LOCAL_PATH = os.environ.get('SERVTEST_LOCAL_PATH', '/tmp')
SERVTEST_USERNAME = os.environ.get('SERVTEST_USERNAME', 'admin')
SERVTEST_PASSWORD = os.environ.get('SERVTEST_PASSWORD', SERVTEST_USERNAME)
SERVTEST_TENANT = os.environ.get('SERVTEST_TENANT', SERVTEST_USERNAME)

SERVTEST_SAHARA_VANILLA_2_IMAGE = (
    'sahara-liberty-vanilla-2.7.1-ubuntu-14.04.qcow2')
SERVTEST_SAHARA_VANILLA_2_IMAGE_NAME = (
    'sahara-liberty-vanilla-2.7.1-ubuntu-14.04')
SERVTEST_SAHARA_VANILLA_2_IMAGE_MD5 = '3da49911332fc46db0c5fb7c197e3a77'
SERVTEST_SAHARA_VANILLA_2_IMAGE_META = {'_sahara_tag_2.7.1': 'True',
                                        '_sahara_tag_vanilla': 'True',
                                        '_sahara_username': 'ubuntu'}

SERVTEST_MURANO_IMAGE = "ubuntu_14_04-murano-agent_stable_juno_26_02_15.qcow2"
SERVTEST_MURANO_IMAGE_MD5 = '3da5ec5984d6d19c1b88d0062c885a89'
SERVTEST_MURANO_IMAGE_NAME = 'murano'
SERVTEST_MURANO_IMAGE_META = {
    'murano_image_info': '{"type": "linux", "title": "murano"}'}

SERVTEST_EXTERNAL_MONGO_URLS = os.environ.get('EXTERNAL_MONGO_URLS')
SERVTEST_EXTERNAL_MONGO_DB_NAME = os.environ.get('EXTERNAL_MONGO_DB_NAME',
                                                 'ceilometer')
SERVTEST_EXTERNAL_MONGO_USER = os.environ.get('EXTERNAL_MONGO_USER')
SERVTEST_EXTERNAL_MONGO_PASS = os.environ.get('EXTERNAL_MONGO_PASS')
SERVTEST_EXTERNAL_MONGO_REPL_SET = os.environ.get('EXTERNAL_MONGO_REPL_SET')

DEFAULT_IMAGES_CENTOS = os.environ.get(
    'DEFAULT_IMAGES_CENTOS',
    '/var/lib/libvirt/images/centos6.4-base.qcow2')

DEFAULT_IMAGES_UBUNTU = os.environ.get(
    'DEFAULT_IMAGES_UBUNTU',
    '/var/lib/libvirt/images/ubuntu-12.04.1-server-amd64-p2.qcow2')

OS_IMAGE = os.environ.get('OS_IMAGE', DEFAULT_IMAGES_CENTOS)

OSTF_TEST_NAME = os.environ.get('OSTF_TEST_NAME',
                                'Check network connectivity'
                                ' from instance via floating IP')
OSTF_TEST_RETRIES_COUNT = int(os.environ.get('OSTF_TEST_RETRIES_COUNT', 50))

# The variable below is only for test:
#       fuelweb_test.tests.tests_strength.test_ostf_repeatable_tests
#       :OstfRepeatableTests.run_ostf_n_times_against_custom_deployment
DEPLOYMENT_NAME = os.environ.get('DEPLOYMENT_NAME')

# Need for iso with docker
TIMEOUT = int(os.environ.get('TIMEOUT', 60))
ATTEMPTS = int(os.environ.get('ATTEMPTS', 5))

# Create snapshots as last step in test-case
MAKE_SNAPSHOT = get_var_as_bool('MAKE_SNAPSHOT', False)

FUEL_SETTINGS_YAML = os.environ.get('FUEL_SETTINGS_YAML',
                                    '/etc/fuel/astute.yaml')
# Upgrade-related variables
UPGRADE_TEST_TEMPLATE = os.environ.get("UPGRADE_TEST_TEMPLATE")
UPGRADE_CUSTOM_STEP_NAME = os.environ.get("UPGRADE_CUSTOM_STEP_NAME", "")
TARBALL_PATH = os.environ.get('TARBALL_PATH')

OCTANE_REPO_LOCATION = os.environ.get('OCTANE_REPO_LOCATION', '')
if not OCTANE_REPO_LOCATION:
    FUEL_PROPOSED_REPO_URL = os.environ.get('FUEL_PROPOSED_REPO_URL', '')
    OCTANE_REPO_LOCATION = FUEL_PROPOSED_REPO_URL

UPGRADE_FUEL_FROM = os.environ.get('UPGRADE_FUEL_FROM', '8.0')
UPGRADE_FUEL_TO = os.environ.get('UPGRADE_FUEL_TO', '9.0')
OCTANE_PATCHES = os.environ.get('OCTANE_PATCHES', None)
EXAMPLE_V3_PLUGIN_REMOTE_URL = os.environ.get('EXAMPLE_V3_PLUGIN_REMOTE_URL',
                                              None)
EXAMPLE_V4_PLUGIN_REMOTE_URL = os.environ.get('EXAMPLE_V4_PLUGIN_REMOTE_URL',
                                              None)
UPGRADE_BACKUP_FILES_LOCAL_DIR = os.environ.get(
    'UPGRADE_BACKUP_FILES_LOCAL_DIR', os.path.join(
        os.path.curdir, "..", "backup_storage"))
UPGRADE_BACKUP_FILES_REMOTE_DIR = os.environ.get(
    'UPGRADE_BACKUP_FILES_REMOTE_DIR', "/var/upgrade/backups")
# End of upgrade-related variables

SNAPSHOT = os.environ.get('SNAPSHOT', '')

# Repos paths and files
MOS_REPOS = os.environ.get('MOS_REPOS',
                           'http://mirror.fuel-infra.org/mos-repos/')
CENTOS_REPO_PATH = os.environ.get(
    'CENTOS_REPO_PATH',
    MOS_REPOS + 'centos/mos{release_version}-centos7/')
UBUNTU_REPO_PATH = os.environ.get(
    'UBUNTU_REPO_PATH',
    MOS_REPOS + 'ubuntu/{release_version}/')
GPG_CENTOS_KEY_PATH = os.environ.get(
    'GPG_CENTOS_KEY',
    CENTOS_REPO_PATH + 'os/RPM-GPG-KEY-mos{release_version}')
MASTER_CENTOS_GPG = os.environ.get(
    'MASTER_CENTOS_GPG', 'http://packages.fuel-infra.org/repositories'
                         '/centos/master-centos7/os/RPM-GPG-KEY-'
)
PACKAGES_CENTOS = os.environ.get(
    'PACKAGES_CENTOS',
    'http://packages.fuel-infra.org/repositories/'
    'centos/master-centos7/os/x86_64/')

# Release name of local Ubuntu mirror on Fuel master node.
UBUNTU_RELEASE = os.environ.get('UBUNTU_RELEASE', 'precise')

UPDATE_TIMEOUT = os.environ.get('UPDATE_TIMEOUT', 3600)

PLUGIN_PACKAGE_VERSION = os.environ.get('PLUGIN_PACKAGE_VERSION', '')

# Plugin path for plugins tests

CONTRAIL_PLUGIN_PATH = os.environ.get('CONTRAIL_PLUGIN_PATH')
CONTRAIL_PLUGIN_PACK_UB_PATH = os.environ.get('CONTRAIL_PLUGIN_PACK_UB_PATH')
CONTRAIL_PLUGIN_PACK_CEN_PATH = os.environ.get('CONTRAIL_PLUGIN_PACK_CEN_PATH')
DVS_PLUGIN_PATH = os.environ.get('DVS_PLUGIN_PATH')
DVS_PLUGIN_VERSION = os.environ.get('DVS_PLUGIN_VERSION')
GLUSTER_PLUGIN_PATH = os.environ.get('GLUSTER_PLUGIN_PATH')
GLUSTER_CLUSTER_ENDPOINT = os.environ.get('GLUSTER_CLUSTER_ENDPOINT')
EXAMPLE_PLUGIN_PATH = os.environ.get('EXAMPLE_PLUGIN_PATH')
EXAMPLE_PLUGIN_V3_PATH = os.environ.get('EXAMPLE_PLUGIN_V3_PATH')
EXAMPLE_PLUGIN_V4_PATH = os.environ.get('EXAMPLE_PLUGIN_V4_PATH')
LBAAS_PLUGIN_PATH = os.environ.get('LBAAS_PLUGIN_PATH')
ZABBIX_PLUGIN_PATH = os.environ.get('ZABBIX_PLUGIN_PATH')
ZABBIX_SNMP_PLUGIN_PATH = os.environ.get('ZABBIX_SNMP_PLUGIN_PATH')
ZABBIX_SNMP_EMC_PLUGIN_PATH = os.environ.get('ZABBIX_SNMP_EMC_PLUGIN_PATH')
ZABBIX_SNMP_EXTREME_PLUGIN_PATH = os.environ.get(
    'ZABBIX_SNMP_EXTREME_PLUGIN_PATH')
LMA_COLLECTOR_PLUGIN_PATH = os.environ.get('LMA_COLLECTOR_PLUGIN_PATH')
LMA_INFRA_ALERTING_PLUGIN_PATH = os.environ.get(
    'LMA_INFRA_ALERTING_PLUGIN_PATH')
ELASTICSEARCH_KIBANA_PLUGIN_PATH = os.environ.get(
    'ELASTICSEARCH_KIBANA_PLUGIN_PATH')
INFLUXDB_GRAFANA_PLUGIN_PATH = os.environ.get('INFLUXDB_GRAFANA_PLUGIN_PATH')
SEPARATE_SERVICE_DB_PLUGIN_PATH = os.environ.get(
    'SEPARATE_SERVICE_DB_PLUGIN_PATH')
SEPARATE_SERVICE_RABBIT_PLUGIN_PATH = os.environ.get(
    'SEPARATE_SERVICE_RABBIT_PLUGIN_PATH')
SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH = os.environ.get(
    'SEPARATE_SERVICE_KEYSTONE_PLUGIN_PATH')
SEPARATE_SERVICE_HORIZON_PLUGIN_PATH = os.environ.get(
    'SEPARATE_SERVICE_HORIZON_PLUGIN_PATH')
ETCKEEPER_PLUGIN_REPO = os.environ.get(
    'ETCKEEPER_PLUGIN_REPO',
    'https://github.com/Mirantis/fuel-plugin-etckeeper')
SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH = os.environ.get(
    'SEPARATE_SERVICE_HAPROXY_PLUGIN_PATH')
SEPARATE_SERVICE_BALANCER_PLUGIN_PATH = os.environ.get(
    'SEPARATE_SERVICE_BALANCER_PLUGIN_PATH')
MURANO_PLUGIN_PATH = os.environ.get('MURANO_PLUGIN_PATH')

FUEL_STATS_CHECK = get_var_as_bool('FUEL_STATS_CHECK', False)
FUEL_STATS_ENABLED = get_var_as_bool('FUEL_STATS_ENABLED', True)
FUEL_STATS_SSL = get_var_as_bool('FUEL_STATS_SSL', False)
FUEL_STATS_HOST = os.environ.get('FUEL_STATS_HOST')
FUEL_STATS_PORT = os.environ.get('FUEL_STATS_PORT', '80')

ANALYTICS_IP = os.environ.get('ANALYTICS_IP')

CUSTOM_ENV = get_var_as_bool('CUSTOM_ENV', False)
SECURITY_TEST = get_var_as_bool('SECURITY_TEST', False)
NESSUS_IMAGE_PATH = os.environ.get('NESSUS_IMAGE_PATH',
                                   '/var/lib/libvirt/images/nessus.qcow2')
BUILD_IMAGES = get_var_as_bool('BUILD_IMAGES', False)

STORE_ASTUTE_YAML = get_var_as_bool('STORE_ASTUTE_YAML', False)

EXTERNAL_DNS = [
    string.strip() for string in
    os.environ.get('EXTERNAL_DNS', '208.67.220.220').split(',')
]
EXTERNAL_NTP = [
    string.strip() for string in
    os.environ.get('EXTERNAL_NTP', 'ua.pool.ntp.org').split(',')
]
DNS_SUFFIX = os.environ.get('DNS_SUFFIX', '.test.domain.local')
FUEL_MASTER_HOSTNAME = os.environ.get('FUEL_MASTER_HOSTNAME', 'nailgun')

TIMESTAT_PATH_YAML = os.environ.get(
    'TIMESTAT_PATH_YAML', os.path.join(
        LOGS_DIR, 'timestat_{}.yaml'.format(time.strftime("%Y%m%d"))))

FUEL_PLUGIN_BUILDER_REPO = 'https://github.com/openstack/fuel-plugins.git'

###############################################################################
# Change various Fuel master node default settings                           #
###############################################################################

# URL to custom mirror with new OSCI packages which should be tested
CUSTOM_PKGS_MIRROR = os.environ.get('CUSTOM_PKGS_MIRROR', '')

# Location of local mirrors on master node.
LOCAL_MIRROR_UBUNTU = os.environ.get('LOCAL_MIRROR_UBUNTU',
                                     '/var/www/nailgun/ubuntu/x86_64')
LOCAL_MIRROR_CENTOS = os.environ.get('LOCAL_MIRROR_CENTOS',
                                     '/var/www/nailgun/centos/x86_64')

# MIRROR_UBUNTU and EXTRA_DEB_REPOS - lists of repositories, separated by '|',
# for example:
# MIRROR_UBUNTU = 'deb http://... trusty main universe multiverse|deb ...'
# If MIRROR_UBUNTU set, it will replace the default upstream repositories,
# the first repo in string should point to upstream Ubuntu mirror
# and use sections 'main universe multiverse'.
# Repos from EXTRA_DEB_REPOS will be appended to the list of repositories.
MIRROR_UBUNTU = os.environ.get('MIRROR_UBUNTU', '')
MIRROR_UBUNTU_PRIORITY = os.environ.get('MIRROR_UBUNTU_PRIORITY', 1001)
EXTRA_DEB_REPOS = os.environ.get('EXTRA_DEB_REPOS', '')
EXTRA_DEB_REPOS_PRIORITY = os.environ.get('EXTRA_DEB_REPOS_PRIORITY', 1050)

# The same for Centos repository:
MIRROR_CENTOS = os.environ.get('MIRROR_CENTOS', '')
MIRROR_CENTOS_PRIORITY = os.environ.get('MIRROR_CENTOS_PRIORITY', 50)
EXTRA_RPM_REPOS = os.environ.get('EXTRA_RPM_REPOS', '')
EXTRA_RPM_REPOS_PRIORITY = os.environ.get('EXTRA_RPM_REPOS_PRIORITY', 20)

# Auxiliary repository priority will be set for a cluster if UPDATE_FUEL=true
AUX_DEB_REPO_PRIORITY = os.environ.get('AUX_DEB_REPO_PRIORITY', 1150)
AUX_RPM_REPO_PRIORITY = os.environ.get('AUX_RPM_REPO_PRIORITY', 15)

# True: replace the default list of repositories in Nailgun
# False: keep original list of repositories in Nailgun
REPLACE_DEFAULT_REPOS = get_var_as_bool('REPLACE_DEFAULT_REPOS', True)

# True: replace the default list of repositories once admin node is installed
# False: replace list of repositories before every cluster creation
REPLACE_DEFAULT_REPOS_ONLY_ONCE = get_var_as_bool(
    'REPLACE_DEFAULT_REPOS_ONLY_ONCE', True)

# Set gateway of 'admin' network as NTPD server for Fuel master node
# , set gateway of 'public' network as NTPD server for new OS clusters
FUEL_USE_LOCAL_NTPD = get_var_as_bool('FUEL_USE_LOCAL_NTPD', True)
# Set gateway of 'public' network as DNS server for new OS clusters
FUEL_USE_LOCAL_DNS = get_var_as_bool('FUEL_USE_LOCAL_DNS', True)

# Path to fuel-agent review repository. Used in ci-gates for fuel-agent
FUEL_AGENT_REPO_PATH = os.environ.get('FUEL_AGENT_REPO_PATH', '')

# Default 'KEYSTONE_PASSWORD' can be changed for keystone on Fuel master node
KEYSTONE_CREDS = {'username': os.environ.get('KEYSTONE_USERNAME', 'admin'),
                  'password': os.environ.get('KEYSTONE_PASSWORD', 'admin'),
                  'tenant_name': os.environ.get('KEYSTONE_TENANT', 'admin')}

# Default SSH password 'ENV_FUEL_PASSWORD' can be changed on Fuel master node
SSH_CREDENTIALS = {
    'login': os.environ.get('ENV_FUEL_LOGIN', 'root'),
    'password': os.environ.get('ENV_FUEL_PASSWORD', 'r00tme')}

SSH_IMAGE_CREDENTIALS = {
    'username': os.environ.get('SSH_IMAGE_CREDENTIALS_LOGIN', "cirros"),
    'password': os.environ.get('SSH_IMAGE_CREDENTIALS_PASSWORD', "cubswin:)")
}

###############################################################################

PATCHING_WEB_DIR = os.environ.get("PATCHING_WEB_DIR", "/var/www/nailgun/")
PATCHING_MIRRORS = os.environ.get("PATCHING_MIRRORS",
                                  CUSTOM_PKGS_MIRROR).split()
PATCHING_MASTER_MIRRORS = os.environ.get("PATCHING_MASTER_MIRRORS", '').split()
PATCHING_BUG_ID = os.environ.get("PATCHING_BUG_ID", None)
PATCHING_PKGS_TESTS = os.environ.get("PATCHING_PKGS_TESTS", "./packages_tests")
PATCHING_APPLY_TESTS = os.environ.get("PATCHING_APPLY_TESTS",
                                      "./patching_tests")
PATCHING_PKGS = os.environ.get("PATCHING_PKGS", None)
PATCHING_SNAPSHOT = os.environ.get("PATCHING_SNAPSHOT", None)
PATCHING_CUSTOM_TEST = os.environ.get("PATCHING_CUSTOM_TEST", None)
PATCHING_DISABLE_UPDATES = get_var_as_bool('PATCHING_DISABLE_UPDATES', False)
PATCHING_RUN_RALLY = get_var_as_bool("PATCHING_RUN_RALLY", False)

DOWNLOAD_LINK = os.environ.get(
    'DOWNLOAD_LINK', 'http://ubuntu1.hti.pl/14.04.4/'
                     'ubuntu-14.04.4-server-amd64.iso')
UPDATE_FUEL = get_var_as_bool('UPDATE_FUEL', False)
UPDATE_FUEL_PATH = os.environ.get('UPDATE_FUEL_PATH', '~/fuel/pkgs/')
UPDATE_FUEL_MIRROR = os.environ.get("UPDATE_FUEL_MIRROR", '').split()

UPDATE_MASTER = get_var_as_bool('UPDATE_MASTER', False)

EMC_PLUGIN_PATH = os.environ.get('EMC_PLUGIN_PATH')
EMC_SP_A_IP = os.environ.get('EMC_SP_A_IP')
EMC_SP_B_IP = os.environ.get('EMC_SP_B_IP')
EMC_USERNAME = os.environ.get('EMC_USERNAME')
EMC_PASSWORD = os.environ.get('EMC_PASSWORD')
EMC_POOL_NAME = os.environ.get('EMC_POOL_NAME', '')

UCA_ENABLED = os.environ.get('UCA_ENABLED', False)
UCA_REPO_TYPE = os.environ.get('UCA_REPO_TYPE', 'uca')
UCA_PIN_HAPROXY = get_var_as_bool('UCA_PIN_HAPROXY', True)
UCA_PIN_RABBITMQ = get_var_as_bool('UCA_PIN_RABBITMQ', True)
UCA_PIN_CEPH = get_var_as_bool('UCA_PIN_CEPH', True)

ALWAYS_CREATE_DIAGNOSTIC_SNAPSHOT = get_var_as_bool(
    'ALWAYS_CREATE_DIAGNOSTIC_SNAPSHOT', False)

RALLY_DOCKER_REPO = os.environ.get('RALLY_DOCKER_REPO',
                                   'docker.io/rallyforge/rally')
RALLY_CONTAINER_NAME = os.environ.get('RALLY_CONTAINER_NAME', 'rally')
RALLY_TAGS = os.environ.get('RALLY_TAGS', 'nova').split(',')

REGENERATE_ENV_IMAGE = get_var_as_bool('REGENERATE_ENV_IMAGE', False)
LATE_ARTIFACTS_JOB_URL = os.environ.get("LATE_ARTIFACTS_JOB_URL", '')

NESSUS_ADDRESS = os.environ.get("NESSUS_ADDRESS", None)
NESSUS_PORT = os.environ.get("NESSUS_PORT", 8834)
NESSUS_USERNAME = os.environ.get("NESSUS_USERNAME")
NESSUS_PASSWORD = os.environ.get("NESSUS_PASSWORD")
NESSUS_SSL_VERIFY = get_var_as_bool("NESSUS_SSL_VERIFY", False)

# is using in stability rabbit test to get
# possibility to change count of repeats failures
REPEAT_COUNT = os.environ.get("REPEAT_COUNT", 2)

# The number of cold restarts
# in the 'repetitive_restart' test group
RESTART_COUNT = os.environ.get("RESTART_COUNT", 10)

# RH-related variables
# Need to update these variables, when image with RH for
# MOS will be available.
EXTRA_COMP_IMAGE = os.environ.get("EXTRA_COMP_IMAGE")
EXTRA_COMP_IMAGE_PATH = os.environ.get("EXTRA_COMP_IMAGE_PATH")
EXTRA_COMP_IMAGE_MD5 = os.environ.get("EXTRA_COMP_IMAGE_MD5")
COMPUTE_BOOT_STRATEGY = os.environ.get("COMPUTE_BOOT_STRATEGY", "system")
EXTRA_COMP_IMAGE_USER = os.environ.get("EXTRA_COMP_IMAGE_USER", "root")
EXTRA_COMP_IMAGE_PASSWORD = os.environ.get("EXTRA_COMP_IMAGE_PASSWORD",
                                           "r00tme")
RH_LICENSE_USERNAME = os.environ.get("RH_LICENSE_USERNAME")
RH_LICENSE_PASSWORD = os.environ.get("RH_LICENSE_PASSWORD")
RH_SERVER_URL = os.environ.get("RH_SERVER_URL")
RH_REGISTERED_ORG_NAME = os.environ.get("RH_REGISTERED_ORG_NAME")
RH_ACTIVATION_KEY = os.environ.get("RH_ACTIVATION_KEY")
RH_RELEASE = os.environ.get("RH_RELEASE")
RH_MAJOR_RELEASE = os.environ.get("RH_MAJOR_RELEASE", "7")
OL_MAJOR_RELEASE = os.environ.get("OL_MAJOR_RELEASE", "7")
CENTOS_DUMMY_DEPLOY = get_var_as_bool("CENTOS_DUMMY_DEPLOY", False)
PERESTROIKA_REPO = os.environ.get("PERESTROIKA_REPO")
RH_POOL_HASH = os.environ.get("RH_POOL_HASH")

# Ironic variables
IRONIC_USER_IMAGE_URL = os.environ.get(
    "IRONIC_USER_IMAGE_URL", "https://cloud-images.ubuntu.com/trusty/current/"
                             "trusty-server-cloudimg-amd64.tar.gz")

NOVA_QUOTAS_ENABLED = get_var_as_bool("NOVA_QUOTAS_ENABLED", False)

DISABLE_OFFLOADING = get_var_as_bool("DISABLE_OFFLOADING", True)

GERRIT_PROJECT = os.environ.get("GERRIT_PROJECT")
GERRIT_BRANCH = os.environ.get("GERRIT_BRANCH")
GERRIT_CHANGE_ID = os.environ.get("GERRIT_CHANGE_ID")
GERRIT_PATCHSET_NUMBER = os.environ.get("GERRIT_PATCHSET_NUMBER")

DOWNLOAD_FACTS = get_var_as_bool("DOWNLOAD_FACTS", False)

TASK_BASED_ENGINE = get_var_as_bool("TASK_BASED_ENGINE", True)

FUEL_RELEASE_PATH = os.environ.get("FUEL_RELEASE_PATH")

MASTER_NODE_EXTRA_PACKAGES = os.environ.get("MASTER_NODE_EXTRA_PACKAGES", "")

LOG_SNAPSHOT_TIMEOUT = int(os.environ.get("LOG_SNAPSHOT_TIMEOUT", 10 * 60))
