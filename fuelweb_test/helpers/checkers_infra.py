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

import subprocess

from fuelweb_test import logger

# For invocation from https://review.openstack.org/#/c/285952
def get_bridge_netfilters_status():
    """Check if the iptables enabled for bridges on the host
    :return: int
        1: if net.bridge.bridge-nf-call-ip6tables = 1
              net.bridge.bridge-nf-call-iptables = 1
              net.bridge.bridge-nf-call-arptables = 1
        0: if net.bridge.bridge-nf-call-ip6tables = 0
              net.bridge.bridge-nf-call-iptables = 0
              net.bridge.bridge-nf-call-arptables = 0
              (this is most required config for system tests)
        -1: if some of the options above are enabled and some are disabled.
    """
    results = []
    for table in ("ip6tables", "iptables", "arptables"):
        cmd = "cat /proc/sys/net/bridge/bridge-nf-call-{0}".format(table)
        stdout = subprocess.check_output(cmd, shell=True)
        results.append(int(stdout))
        logger.debug("CMD: '{0}' RESULT: '{1}'".format(cmd, stdout))
    if all([x == 1 for x in results]):
        return 1
    elif all([x == 0 for x in results]):
        return 0
    else:
        return -1


def check_host_settings(bridge_netfilters=0):
    """Check most common settings on the host

    :param bridge_netfilters: int, expected value of netfilters on the host.

    :rtype: None or Exception (should be changed to InfraFailed exception type)
    """
    if get_bridge_netfilters_status() != bridge_netfilters:
        raise Exception(
            "Some of network filters for bridges are not in the"
            " expected state. Please check the following settings:\n"
            "  /proc/sys/net/bridge/bridge-nf-call-ip6tables\n"
            "  /proc/sys/net/bridge/bridge-nf-call-iptables\n"
            "  /proc/sys/net/bridge/bridge-nf-call-arptables\n"
            ", values should be '{0}'".format(bridge_netfilters))
