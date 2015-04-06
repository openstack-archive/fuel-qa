#    Copyright 2015 Mirantis, Inc.
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

import time

from devops.error import TimeoutError
from devops.helpers.helpers import wait
from proboscis.asserts import assert_true

from fuelweb_test import logger
from fuelweb_test import logwrap


class NtpSync(object):
    """ Synchronize a group of nodes """
    ntps = []

    def __init__(self, env=None, nailgun_nodes=[]):
        """ env - EnvironmentModel, to create remote connections
            nailgun_nodes - list of Nailgun node objects
        """
        # 1. Create a list of 'Ntp' connections to the nodes
        self.ntps = [Ntp().new(env.d_env.get_ssh_to_remote(node['ip']),
                               'node-{0}'.format(node['id']))
                     for node in nailgun_nodes]

    def do_sync_time(self, ntps=[]):
        # 0. 'ntps' can be filled by __init__() or outside the class
        if not ntps:
            ntps = self.ntps

        # 1. Set actual time on all nodes via 'ntpdate'
        [ntp.set_actual_time() for ntp in ntps]
        assert_true(all([ntp.is_synchronized for ntp in ntps]),
                    "Time on some nodes was not synchronized: \n{0}"
                    .format(["{0}, {1}".format(ntp.node_name, ntp.date())
                             for ntp in ntps if not ntp.is_synchronized]))

        # 2. Restart NTPD service
        [ntp.stop() for ntp in ntps]
        [ntp.start() for ntp in ntps]

        # 3. Wait for established peers
        [ntp.wait_peer() for ntp in ntps]
        assert_true(all([ntp.is_connected for ntp in ntps]),
                    "Time on some nodes was not synchronized: \n{0}"
                    .format(["{0}, {1}".format(ntp.node_name, ntp.peers)
                            for ntp in ntps if not ntp.is_connected]))

        # 4. Report time on nodes
        for ntp in ntps:
            logger.info("Time on {0} = {1}".format(ntp.node_name, ntp.date()))


class Ntp(object):
    """ Common methods to work with ntpd service """

    @logwrap
    def new(self, remote, node_name=''):

        # Detect how NTPD is managed - by init script or by pacemaker.
        cmd = "ps acx | grep pacemakerd"
        if remote.execute(cmd)['exit_code'] == 0:
            # Pacemaker service found
            cls = NtpPacemaker()
        else:
            # Pacemaker not found, using native ntpd
            cls = NtpInitscript()

        cls.is_synchronized = False
        cls.is_connected = False
        cls.remote = remote
        cls.node_name = node_name
        cls.peers = []

        # Get IP of a server from which the time will be syncronized.
        cmd = "awk '/^server/ && $2 !~ /127.*/ {print $2}' /etc/ntp.conf"
        cls.server = remote.execute(cmd)['stdout'][0]

        cmd = "find /etc/init.d/ -regex '/etc/init.d/ntp.?'"
        cls.service = remote.execute(cmd)['stdout'][0].strip()

        return cls

    @logwrap
    def set_actual_time(self, timeout=600):
        # Waiting for parent server until it starts providing the time
        cmd = "ntpdate -p 4 -t 0.2 -bu {0}".format(self.server)
        self.is_synchronized = False
        try:
            wait(lambda: not self.remote.execute(cmd)['exit_code'], timeout)
            self.is_synchronized = True
            self.remote.execute('hwclock -w')
        except TimeoutError:
            pass

        return self.is_synchronized

    @logwrap
    def wait_peer(self, interval=8, timeout=600):
        self.is_connected = False

        start_time = time.time()
        while start_time + timeout > time.time():
            # peer = `ntpq -pn`
            self.peers = self.get_peers()[2:]  # skip the header
            logger.debug("Node: {0}, ntpd peers: {1}".format(
                self.node_name, self.peers))

            for peer in self.peers:
                p = peer.split()
                remote = str(p[0])
                reach = int(p[6], 8)   # From octal to int
                offset = float(p[8])
                jitter = float(p[9])

                # 1. offset and jitter should not be higher than 500
                # Otherwise, time should be re-set.
                if (abs(offset) > 500) or (abs(jitter) > 500):
                    return self.is_connected

                # 2. remote should be marked whith tally  '*'
                if remote[0] != '*':
                    continue

                # 3. reachability bit array should have '1' at least in
                # two lower bits as the last two sussesful checks
                if reach & 3 == 3:
                    self.is_connected = True
                    return self.is_connected

            time.sleep(interval)
        return self.is_connected

    def date(self):
        return self.remote.execute("date")['stdout']


class NtpInitscript(Ntp):

    @logwrap
    def start(self):
        self.is_connected = False
        self.remote.execute("{0} start".format(self.service))

    @logwrap
    def stop(self):
        self.is_connected = False
        self.remote.execute("{0} stop".format(self.service))

    @logwrap
    def get_peers(self):
        return self.remote.execute('ntpq -pn')['stdout']


class NtpPacemaker(Ntp):

    @logwrap
    def start(self):
        self.is_connected = False
        self.remote.execute('crm resource start p_ntp')

    @logwrap
    def stop(self):
        self.is_connected = False
        self.remote.execute('crm resource stop p_ntp; killall ntpd')

    @logwrap
    def get_peers(self):
        return self.remote.execute(
            'ip netns exec vrouter ntpq -pn')['stdout']
