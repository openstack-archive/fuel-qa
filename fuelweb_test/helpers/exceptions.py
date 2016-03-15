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


class UnexpectedExitCode(Exception):
    def __init__(self, command, ec, expected_ec, stdout=None, stderr=None):
        self.ec = ec
        self.expected_ec = expected_ec
        self.cmd = command
        self.stdout = stdout
        self.stderr = stderr

    def __str__(self):
        message = "Command '{cmd:s}' returned unexpected exit code {code:d}," \
                  " while waiting for {exp!s}".format(cmd=self.cmd,
                                                      code=self.ec,
                                                      exp=self.expected_ec)
        if self.stdout:
            message += "stdout: {}\n".format(self.stdout)
        if self.stderr:
            message += "stderr: {}\n".format(self.stderr)
        return message
