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

from core.helpers.log_helpers import logwrap

from fuelweb_test.helpers.ssh_manager import SSHManager


ssh_manager = SSHManager()


@logwrap
def change_config(ip, umm=True, reboot_count=2, counter_reset_time=10):
    umm_string = 'yes' if umm else 'no'
    cmd = ("echo -e 'UMM={0}\n"
           "REBOOT_COUNT={1}\n"
           "COUNTER_RESET_TIME={2}' > /etc/umm.conf".format(umm_string,
                                                            reboot_count,
                                                            counter_reset_time)
           )
    result = ssh_manager.execute(
        ip=ip,
        cmd=cmd
    )
    return result


def check_available_mode(ip):
    command = ('umm status | grep runlevel &>/dev/null && echo "True" '
               '|| echo "False"')
    if ssh_manager.execute(ip, command)['exit_code'] == 0:
        return ''.join(ssh_manager.execute(ip, command)['stdout']).strip()
    else:
        return ''.join(ssh_manager.execute(ip, command)['stderr']).strip()


def check_auto_mode(ip):
    command = ('umm status | grep umm &>/dev/null && echo "True" '
               '|| echo "False"')
    if ssh_manager.execute(ip, command)['exit_code'] == 0:
        return ''.join(ssh_manager.execute(ip, command)['stdout']).strip()
    else:
        return ''.join(ssh_manager.execute(ip, command)['stderr']).strip()
