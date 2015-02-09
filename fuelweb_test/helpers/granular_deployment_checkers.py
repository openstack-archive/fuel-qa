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


from proboscis.asserts import assert_equal
from proboscis.asserts import assert_true

from fuelweb_test import logger


def check_hiera_resources(remote, file_name=None):
    cmd_sh = 'if [ -d /etc/hiera ] ; then echo "fine" ;  fi'
    output = ''.join(remote.execute(cmd_sh)['stdout'])
    assert_true('fine' in output, output)
    if not file_name:
        output_f = ''.join(remote.execute(
            'if [ -r /etc/hiera.yaml ] ; then echo "passed" ;  fi')[
            'stdout'])
        assert_true('passed' in output_f, output_f)
    else:
        output_f = ''.join(remote.execute(
            'if [ -r /etc/%s ] ; then echo "passed" ;  fi' % file_name)[
            'stdout'])
        assert_true('passed' in output_f,
                    'Can not find passed result in '
                    'output {0}'.format(output_f))


def get_hiera_data(remote, data):
    cmd = 'hiera {}'.format(data)
    res = remote.execute(cmd)['stdout']
    return res


def check_interface_status(remote, iname):
    cmd = 'ethtools {0}| grep "Link detected"'.format(iname)
    result = remote.execute(cmd)
    assert_equal(0, result['exit_code'],
                 "Non-zero exit code sderr {0}, "
                 "stdout {1}".format(result['stderr'], result['stdout']))

    assert_true('yes' in ''.join(result['stdout']),
                "No link detected for interface {0},"
                " Actual stdout {1}".format(iname, result['stdout']))


def ping_remote_net(remote, ip):
    cmd = "ping -q -c1 -w10 {0}".format(ip)
    res = remote.execute(cmd)
    logger.debug('Current res from ping is {0}'.format(res))
    assert_equal(
        res['exit_code'], 0,
        "Ping of {0} ended with non zero exit-code. "
        "Stdout is {1}, sderr {2}".format(
            ip, ''.join(res['stdout']), ''.join(res['stderr'])))


def check_logging_task(remote, conf_name):
    cmd_sh = 'if [ -r /rsyslog.d/{0}] ; then echo "fine" ;  fi'.format(
        conf_name)
    output = ''.join(remote.execute(cmd_sh)['stdout'])
    assert_true('fine' in output, output)


def check_tools_task(remote, tool_name):
    cmd_sh = 'pgrep {0}'.format(tool_name)
    output = remote.execute(cmd_sh)
    assert_equal(
        0, output['exit_code'],
        "Command {0} failed with non zero exit code, current output is:"
        " stdout {1}, sdterr: {2} ".format(
            cmd_sh, ''.join(output['stdout']), ''.join(output['stderr'])))


def run_check_from_task(remote, path):
    res = remote.execute('{0}'.format(path))
    try:
        assert_equal(
            0, res['exit_code'],
            "Check {0} finishes with non zero exit code, stderr is {1}, "
            "stdout is {2} on remote".format(
                path, res['stderr'], res['stdout']))
    except AssertionError:
        time.sleep(60)
        logger.info('remoote is {0}'.format(remote))
        res = remote.execute('{0}'.format(path))
        assert_equal(
            0, res['exit_code'],
            "Check {0} finishes with non zero exit code, stderr is {1}, "
            "stdout is {2} on remote".format(
                path, res['stderr'], res['stdout']))
