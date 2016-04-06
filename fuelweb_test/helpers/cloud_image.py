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

import os
import subprocess

from fuelweb_test import settings
from fuelweb_test.settings import iface_alias


def prepare_steps():
    cloud_image_dir_path = os.path.join(os.path.dirname('__file__'),
                                        '/build_cloudimage_metadata_iso')
    if not os.path.exists(cloud_image_dir_path):
        os.makedirs(cloud_image_dir_path)
    meta_data_path = os.path.join(cloud_image_dir_path,
                                  "meta_data")
    user_data_path = os.path.join(cloud_image_dir_path,
                                  "user_data")
    return cloud_image_dir_path, meta_data_path, user_data_path


def generate_meta_data(d_env, meta_data_path):
    admin_net_object = d_env.get_network(name=d_env.admin_net)
    admin_network = admin_net_object.ip.network
    admin_netmask = admin_net_object.ip.netmask
    admin_ip = str(d_env.nodes(
    ).admin.get_ip_address_by_network_name(d_env.admin_net))

    context = {
        "interface_name": "{}".format(iface_alias("eth0")),
        "address": "{}".format(admin_ip),
        "network": "{}".format(admin_network),
        "netmask": "{}".format(admin_netmask),
        "gateway": "{}".format(d_env.router()),
        "dns": "{}".format(settings.DNS),
        "dns_ext": "{}".format(settings.EXTERNAL_DNS),
        "hostname": "{}".format(settings.FUEL_MASTER_HOSTNAME)
    }

    meta_data_content = (""
                         "instance-id: iid-local1\n"
                         "network-interfaces: |\n"
                         " auto {interface_name}\n"
                         " iface {interface_name} inet static\n"
                         " address {address}\n"
                         " network {network}\n"
                         " netmask {netmask}\n"
                         " gateway {gateway}\n"
                         " dns-nameservers {dns} {dns_ext}\n"
                         "local-hostname: {hostname}")
    with open(meta_data_path, 'a') as f:
        f.write(meta_data_content.format(**context))


def generate_user_data(d_env, user_data_path):
    context = {
        "interface_name": "{}".format(iface_alias("eth0")),
        "gateway": "{}".format(d_env.router()),
        "user": "{}".format(settings.SSH_CREDENTIALS[0]),
        "password": "{}".format(settings.SSH_CREDENTIALS[1])
    }

    user_data_content = (""
                         "#cloud-config\n"
                         "ssh_pwauth: True\n"
                         "chpasswd:\n"
                         "list: |\n"
                         " {user}:{password}\n"
                         "expire: False \n\n"
                         "runcmd:\n"
                         " - sudo ifup {interface_name}\n"
                         " - sudo sed -i -e '/^PermitRootLogin/s/^"
                         ".*$/PermitRootLogin yes/' /etc/ssh/sshd_config\n"
                         " - sudo service ssh restart\n"
                         " - sudo route add default gw "
                         "{gateway} {interface_name}")

    with open(user_data_path, 'a') as f:
        f.write(user_data_content.format(**context))


def generate_cloudimage_iso(cloud_image_dir_path,
                            user_data_path,
                            meta_data_path):
    subprocess.check_call(["genisoimage", "-output {}/cloud_centos.iso",
                           "-volid cidata", "-joliet", "-rock {} {}"],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE).__format__(
        cloud_image_dir_path,
        user_data_path,
        meta_data_path
    )
