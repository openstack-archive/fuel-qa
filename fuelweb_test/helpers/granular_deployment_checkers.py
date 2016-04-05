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
            'if [ -r /etc/hiera.yaml ] ; then echo "passed" ;  fi')['stdout'])
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
                 "Non-zero exit code stderr {0}, "
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
        "Stdout is {1}, stderr {2}".format(
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
        " stdout {1}, stderr: {2} ".format(
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
        logger.info('remote is {0}'.format(remote))
        res = remote.execute('{0}'.format(path))
        assert_equal(
            0, res['exit_code'],
            "Check {0} finishes with non zero exit code, stderr is {1}, "
            "stdout is {2} on remote".format(
                path, res['stderr'], res['stdout']))


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

    for cluster_id, task in deployment_tasks.items():
        not_ready_jobs = {}
        if task['status'] not in allowed_statuses:
            if task['node_id'] not in not_ready_jobs:
                not_ready_jobs[task['node_id']] = []
                not_ready_jobs[task['node_id']].append(task)
        if not_ready_jobs:
            not_ready_deploy[cluster_id] = not_ready_jobs

    if len(not_ready_deploy) > 0:
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
                for cluster, records in sorted(not_ready_deploy.items())
            ))
        logger.error(failure_text)
        assert_true(len(not_ready_deploy) == 0, failure_text)

    return not_ready_deploy
