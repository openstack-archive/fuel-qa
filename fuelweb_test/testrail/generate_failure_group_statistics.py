#!/usr/bin/env python
#
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


from __future__ import division
import argparse
import hashlib
import json
import os
import re
import sys
from logging import CRITICAL
from logging import DEBUG

import jenkins
from launchpadlib.launchpad import Launchpad
import requests
import tablib
import xmltodict
from fuelweb_test.testrail.settings import JENKINS
from fuelweb_test.testrail.settings import LaunchpadSettings
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail import testrail


def get_sha(input_string):
    """get sha hash

    :param input_string: str - input string
    :return: sha hash string
    """

    return hashlib.sha256(input_string).hexdigest()


def make_cleanup(input_string):
    """clean up string: remove IP/IP6/Mac/etc... by using regexp

    :param input_string: str - input string
    :return: s after regexp and clean up
    """

    # let's try to find all IP, IP6, MAC
    ip4re = re.compile(r'\b(?:[0-9]{1,3}\.){3}[0-9]{1,3}\b')
    ip6re = re.compile(r'\b(?:[a-fA-F0-9]{4}[:|\-]?){8}\b')
    macre = re.compile(r'\b[a-fA-F0-9]{2}[:][a-fA-F0-9]{2}[:]'
                       r'[a-fA-F0-9]{2}[:][a-fA-F0-9]{2}[:]'
                       r'[a-fA-F0-9]{2}[:][a-fA-F0-9]{2}\b')
    digitre = re.compile(r'\b(?:[0-9]{1,3}){1,50}\b')
    hexre = re.compile(r'\b(?:[0-9a-fA-F]{1,8}){1,50}\b')
    # punctuation = re.compile(r'["\'!,?.:;\(\)\{\}\[\]\/\\\<\>]+')

    def ismatch(match):
        """
        :param match: string
        :return: value or ''
        """

        value = match.group()
        return " " if value else value

    stmp = ip4re.sub(ismatch, input_string)
    stmp = ip6re.sub(ismatch, stmp)
    stmp = macre.sub(ismatch, stmp)
    # stmp = punctuation.sub(ismatch, stmp)
    stmp = digitre.sub('x', stmp)
    listhex = hexre.findall(stmp)
    if listhex:
        for i in listhex:
            stmp = hexre.sub('x' * len(i), stmp)
    return stmp


def distance(astr, bstr):
    """Calculates the Levenshtein distance between a and b

    :param astr: str - input string
    :param bstr: str - input string
    :return: distance: int - distance between astr and bstr
    """

    alen, blen = len(astr), len(bstr)
    if alen > blen:
        astr, bstr = bstr, astr
        alen, blen = blen, alen
    current_row = list(range(alen + 1))  # Keep current and previous row
    for i in range(1, blen + 1):
        previous_row, current_row = current_row, [i] + [0] * alen
        for j in range(1, alen + 1):
            add = previous_row[j] + 1
            delete = current_row[j - 1] + 1
            change = previous_row[j - 1]
            if astr[j - 1] != bstr[i - 1]:
                change += 1
            current_row[j] = min(add, delete, change)
    return current_row[alen]


def get_launchpad_bugs(subbuilds):
    """Get all bugs per each failed test name

    :param sub_builds: list of dict per each subbuild
    :return: bugs: dict - Launchpad bugs which belong to those failed tests
    """

    cachedir = "/tmp/launchpad"
    if not os.path.isdir(cachedir):
        os.makedirs(cachedir)
    launchpad = Launchpad.login_anonymously('fuel-qa-client', 'production',
                                            cachedir, version='devel')
    project = launchpad.projects[LaunchpadSettings.project]
    milestone = project.getMilestone(name=LaunchpadSettings.milestone)
    all_bugs = [i.bug for i in milestone.searchTasks(
                status=LaunchpadSettings.open_statuses)]
    all_launchpad_bugs = [{i.id: i.title} for i in all_bugs]
    total_bugs = {}
    for i in subbuilds:
        for j in i.get('failure_reasons', []):
            launchpad_bugs = [bug for bug in all_bugs
                              if bug.title.find(j.get('test')) > 0]
            bugs = [{'id': bug.id,
                     'title': bug.title,
                     'url': bug.web_link,
                     'description': bug.description}
                    for bug in launchpad_bugs]
            if not total_bugs.get(j.get('test')):
                total_bugs[j.get('test')] = bugs
            else:
                total_bugs[j.get('test')].extend(bugs)
    return total_bugs, all_launchpad_bugs


def get_bugs(subbuilds, testraildata):
    """Get all bugs per each failed test name

    :param sub_builds: list of dict per each subbuild
    :param testraildata: list test results for testrail run
    :return: bugs: dict - bugs extracted from testrail
                          and they are belong to those failed tests
    """

    if not testraildata.get('tests'):
        return {}
    total_bugs = ({str(j.get('test')): []
                  for i in subbuilds
                  for j in i.get('failure_reasons', [])})
    tests = [(i, j.get('id')) for i in total_bugs.keys()
             for j in testraildata.get('tests')
             if i == j.get('custom_test_group')]
    bugs = [(t, iid,
             rid.get('custom_launchpad_bug'),
             rid.get('status_id'))
            for (t, iid) in tests
            for rid in testraildata.get('results')
            if iid == rid.get('test_id')]
    for i in bugs:
        if i[2] and i[2].find('bugs.launchpad.net') > 0:
            iid = get_bug_id(i[2])
            title = get_bug_title(i[2]) or str(iid)
            label = get_label(i[3], testraildata.get('statuses'))
            color = get_color(i[3], testraildata.get('statuses'))
            item = {'id': iid,
                    'url': i[2],
                    'title': title,
                    'label': label,
                    'color': color}
            total_bugs[i[0]].append(item)
    return total_bugs


def get_bug_id(bugurl):
    """ Get bugid

    :param bugurl: str - launchpad bugurl
    :return: bug id - int
    """

    return bugurl[bugurl.rfind('/') + 1:]


def get_bug_title(bugurl):
    """ Get bug title

    :param bugurl: str - launchpad bugurl
    :return: bug title - str
    """

    req = requests.get(bugurl)
    title = None
    if 200 <= req.status_code <= 299:
        html = req.text.encode('ascii', 'ignore')
        if html:
            index = html.find('<h1 id="edit-title"')
            rindex = html[index:].find('</span>')
            tmp = html[index: index + rindex]
            lindex = tmp.rfind('>')
            title = tmp[lindex + 1:].strip()
    return title


def get_color(stat_id, statuses):
    """ Get color for test result

    :param stat_id: int - status id
    :param statuses: list - statuses info extracted from TestRail
    :return: color - str
    """
    for stat in statuses:
        if stat_id == stat.get('id'):
            color = str(hex(stat.get('color_dark', 0)))[2:]
            return "#" + color


def get_label(stat_id, statuses):
    """ Get label for test result

    :param stat_id: int - status id
    :param statuses: list - statuses info extracted from TestRail
    :return: label - str
    """
    for stat in statuses:
        if stat_id == stat.get('id'):
            return stat.get('label', 'None')


def get_latest_build_number(job_name=JENKINS.get('job_name'),
                            jenkins_url=JENKINS.get('url'),):
    """ Get latest build number by using jenkins python lib
    Note: More information can be found here:
    http://python-jenkins.readthedocs.org/en/latest/examples.html

    :param jenkins_url: str - Jenkins http url
    :param job_name: str - Jenkins job_name
    :return: build number: int - build number or None otherwise
    """
    server = jenkins.Jenkins(jenkins_url, timeout=30)
    latest_build_number = server.get_job_info(job_name).\
        get('lastCompletedBuild', {}).\
        get('number')
    logger.info('Latest build number is {}'.format(latest_build_number))
    return latest_build_number


def get_build_info(build_number, job_name=JENKINS.get('job_name'),
                   jenkins_url=JENKINS.get('url')):
    """ Get build info by using jenkins python lib
    Note: More information can be found here:
    http://python-jenkins.readthedocs.org/en/latest/examples.html

    :param build_number: int - Jenkins build number
    :param jenkins_url: str - Jenkins http url
    :param job_name: str - Jenkins job_name
    :return: buildinfo: dict - build info or None otherwise
    """

    server = jenkins.Jenkins(jenkins_url, timeout=30)
    buildinfo = server.get_build_info(job_name, build_number)
    return buildinfo


def send_testrail_request(request):
    """ send request to test rail
    Note: More information can be found here:
    http://docs.gurock.com/testrail-api2/bindings-python

    :param request: string - TestRail api request
    :return: value
    """

    client = testrail.APIClient(TestRailSettings.url)
    client.user = TestRailSettings.user
    client.password = TestRailSettings.password
    return client.send_get(request)


def get_testrail_data():
    """ Get test rail info

    :param None
    :return: dict
    """

    projects = send_testrail_request('get_projects')
    prgs = [i for i in projects
            if i.get('name') == TestRailSettings.project]
    if not prgs:
        logger.error('Test Rail Project has not been found')
        return {}
    project = prgs[0]
    milestones = send_testrail_request('get_milestones/{}'.
                                       format(project.get('id')))
    milestone = [i for i in milestones
                 if i.get('name') == TestRailSettings.milestone][0]
    statuses = send_testrail_request('get_statuses')
    return {'project': project, 'milestone': milestone, 'statuses': statuses}


def get_testrail_testdata(subbuilds):
    """ Get test rail plan and run by Swarm Jenkins job

    :param sub_builds: list of dict per each subbuild
    :return: plan, run: tuple - TestRail plan and run dicts
    """

    description = subbuilds[0].get('description')
    if not description:
        for i in subbuilds:
            buildinfo = get_build_info(i.get('buildNumber'),
                                       job_name=i.get('jobName'))
            description = buildinfo.get('description')
            if not description:
                continue
            break
    jname = description.split(' on ')[1]
    planname = jname.replace('-', ' iso #', 1)
    runname = "".join(['[', jname.split('-')[0], ']', ' Swarm'])
    testrail_data = get_testrail_data()
    prid = testrail_data.get('project', {}).get('id')
    miid = testrail_data.get('milestone', {}).get('id')
    statuses = testrail_data.get('statuses', {})
    plans = send_testrail_request('get_plans/{}&milestone_id={}'.
                                  format(prid, miid))
    for i in plans:
        plan = None
        run = None
        if i.get('name') == planname:
            plan = send_testrail_request('get_plan/{}'.format(i.get('id')))
            for j in plan.get('entries'):
                for k in j.get('runs'):
                    if k.get('name') == runname:
                        run = send_testrail_request('get_run/{}'.
                                                    format(k.get('id')))
                        break
                if run:
                    break
        if plan and run:
            break
    if plan and run:
        tests = send_testrail_request('get_tests/{}'.
                                      format(run.get('id')))
        results = send_testrail_request('get_results_for_run/{}'.
                                        format(run.get('id')))
        return {'plan': plan, 'run': run, 'statuses': statuses,
                'tests': tests, 'results': results}
    return {}


def get_testrail_test_urls(tests, test_name):
    """ Get test case url and test result url

    :param tests: list - TestRail tests gathered by run_id
    :param test_name: string - TestRail custom_test_group field
    :return: test case and test result urls - dict
            {} otherwise return back
    """

    if tests.get('tests'):
        for j in tests.get('tests'):
            if j.get('custom_test_group') == test_name:
                testcase_url = "".join([TestRailSettings.url,
                                        '/index.php?/cases/view/',
                                        str(j.get('case_id'))])
                testresult_url = "".join([TestRailSettings.url,
                                          '/index.php?/tests/view/',
                                          str(j.get('id'))])
                testresult_status = get_label(j.get('status_id'),
                                              tests.get('statuses'))
                testresult_status_color = get_color(j.get('status_id'),
                                                    tests.get('statuses'))
                return {'testcase_url': testcase_url,
                        'testresult_url': testresult_url,
                        'testresult_status': testresult_status,
                        'testresult_status_color': testresult_status_color}
    return {}


def get_build_test_data(build_number, job_name,
                        jenkins_url=JENKINS.get('url')):
    """ Get build test data from Jenkins from nosetests.xml

    :param build_number: int - Jenkins build number
    :param job_name: str - Jenkins job_name
    :param jenkins_url: str - Jenkins http url
    :return: test_data: dict - build info or None otherwise
    """

    test_data = None
    buildinfo = get_build_info(build_number, job_name=job_name)
    if buildinfo:
        artifact_paths = [v for i in buildinfo.get('artifacts')
                          for k, v in i.items() if k == 'relativePath' and
                          v == JENKINS.get('xml_testresult_file_name')]
        if artifact_paths:
            full_url = "/".join([jenkins_url, 'job', job_name,
                                 str(build_number), 'artifact',
                                 artifact_paths[0]])
            req = requests.get(full_url)
            if 200 <= req.status_code <= 299:
                try:
                    test_data = xmltodict.parse(req.text, xml_attribs=True)
                    test_data.update({'build_number': build_number,
                                      'job_name': job_name,
                                      'job_url': buildinfo.get('url'),
                                      'job_description':
                                          buildinfo.get('description'),
                                      'job_status': buildinfo.get('result')})
                except:
                    test_data = None
    return test_data


def get_build_failure_reasons(test_data):
    """ Gather all failure reasons across all tests

    :param test_data: dict - test data which were extracted from Jenkins
    :return: test_data: list of dicts
             {failure, test, build_number, job_name, url, test_url}
              where:
              failure(type and message were exctracted from nosetests.xml)-str
              test(@classname was exctracted from nosetests.xml)-str
              build_number(number which exctracted from build_info early)-int
              job_name(Jenkins job name extracted from build_info early)-str
              url(Jenkins job name full URL) - str
              test_url(Jenkins test result URL) - str
             [] otherwise
    """
    failure_reasons = []
    for test in test_data.get('testsuite').get('testcase'):
        failure_reason = None
        if test.get('error'):
            failure_reason = "___".join(['error',
                                         'type',
                                         test.get('error').get('@type'),
                                         'message',
                                         test.get('error').get('@message')])
        elif test.get('failure'):
            failure_reason = "___".join(['failure',
                                         'type',
                                         test.get('failure').get('@type'),
                                         'message',
                                         test.get('failure').get('@message')])
        elif test.get('skipped'):
            failure_reason = "___".join(['skipped',
                                         'type',
                                         test.get('skipped').get('@type'),
                                         'message',
                                         test.get('skipped').get('@message')])
        if failure_reason:
            failure_reason_cleanup = make_cleanup(failure_reason)
            failure_reasons.append({'failure': failure_reason_cleanup,
                                    'failure_origin': failure_reason,
                                    'test': test.get('@classname'),
                                    'build_number':
                                        test_data.get('build_number'),
                                    'job_name': test_data.get('job_name'),
                                    'job_url': test_data.get('job_url'),
                                    'job_status': test_data.get('job_status'),
                                    'test_fail_url': "".
                                        join([test_data.get('job_url'),
                                              'testReport/(root)/',
                                              test.get('@classname'),
                                              '/', test.get('@name')])
                                    })
    return failure_reasons


def get_sub_builds(build_number, job_name=JENKINS.get('job_name'),
                   jenkins_url=JENKINS.get('url')):
    """ Gather all sub build info into subbuild list

    :param build_number: int - Jenkins build number
    :param job_name: str - Jenkins job_name
    :param jenkins_url: str - Jenkins http url
    :return: sub_builds: list of dicts or None otherwise
             {build_info, test_data, failure_reasons}
              where:
              build_info(sub build specific info got from Jenkins)-dict
              test_data(test data per one sub build)-dict
              failure_reasons(failures per one sub build)-list
    """

    parent_build_info = get_build_info(build_number, job_name, jenkins_url)
    sub_builds = None
    if parent_build_info:
        sub_builds = [i for i in parent_build_info.get('subBuilds')]
    if sub_builds:
        for i in sub_builds:
            test_data = get_build_test_data(i.get('buildNumber'),
                                            i.get('jobName'),
                                            jenkins_url)
            if test_data:
                i.update({'test_data': test_data})
                i.update({'description': test_data.get('job_description')})
                i.update({'failure_reasons':
                          get_build_failure_reasons(test_data)})
    return sub_builds


def get_global_failure_group_list(sub_builds, threshold=0.04):
    """ Filter out and grouping of all failure reasons across all tests

    :param sub_builds: list of dict per each subbuild
    :param threshold: float -threshold
    :return: (failure_group_dict, failure_reasons): tuple or () otherwise
              where:
              failure_group_dict(all failure groups and
              associated failed test info per each failure group) - dict
              failure_reasons(all failures across all subbuild) - list
    """
    # let's find all failures in all builds
    failure_reasons = []
    failure_group_dict = {}
    failure_group_list = []
    for build in sub_builds:
        if build.get('failure_reasons'):
            for failure in build.get('failure_reasons'):
                failure_reasons.append(failure)
                failure_group_list.append(failure.get('failure'))
    # let's truncate list
    failure_group_list = list(set(failure_group_list))
    # let's update failure_group_dict
    for failure in failure_reasons:
        if failure.get('failure') in failure_group_list:
            key = failure.get('failure')
            if not failure_group_dict.get(key):
                failure_group_dict[key] = []
            failure_group_dict[key].append(failure)
    # let's find Levenshtein distance and update failure_group_dict
    for num1, key1 in enumerate(failure_group_dict.keys()):
        for key2 in failure_group_dict.keys()[num1 + 1:]:
            # let's skip grouping if len are different more 10%
            if key1 == key2 or abs(float(len(key1) / len(key2))) > 0.1:
                continue
            # let's find other failures which can be grouped
            # if normalized Levenshtein distance less threshold
            llen = distance(key1, key2)
            cal_threshold = float(llen) / max(len(key1), len(key2))
            if cal_threshold < threshold:
                # seems we shall combine those groups to one
                failure_group_dict[key1].extend(failure_group_dict[key2])
                logger.info("Those groups are going to be combined"
                            " due to Levenshtein distance\n"
                            " {}\n{}".format(key1, key2))
                del failure_group_dict[key2]
    return failure_group_dict, failure_reasons


def update_subbuilds_failuregroup(sub_builds, failure_group_dict,
                                  testrail_testdata, bugs):
    """ update subbuilds by TestRail and Launchpad info

    :param sub_builds: dict of subbuilds
    :param failure_group_dict: dict of failures
    :param testrail_testdata: dict - data extracted from TestRail
    :param bugs: dict - data extracted from launchpad
    :return: None
    """

    failure_reasons_builds = [i for j in sub_builds
                              for i in j.get('failure_reasons', {})]
    if failure_reasons_builds:
        for fail in failure_reasons_builds:
            fail.update(get_testrail_test_urls(testrail_testdata,
                                               fail.get('test')))
            fail.update({'bugs': bugs.get(fail.get('test'))})
        for fgroup, flist in failure_group_dict.items():
            for fail in failure_reasons_builds:
                for ffail in flist:
                    if not fail.get('failure_group')\
                       and fail.get('failure') == ffail.get('failure'):
                        fail.update({'failure_group': fgroup})
                    if fail.get('test') == ffail.get('test'):
                        ffail.update({'testresult_status':
                                      fail.get('testresult_status'),
                                      'testresult_status_color':
                                      fail.get('testresult_status_color'),
                                      'testcase_url':
                                      fail.get('testcase_url'),
                                      'testresult_url':
                                      fail.get('testresult_url'),
                                      'bugs': fail.get('bugs')})


def get_statistics(failure_group_dict, format_out=None):
    """ Generate statistics for all failure reasons across all tests

    Note: non hml format is going to be flat
    :param failure_group_dict: dict of failures
    :param testrail_tests: list of test cases extracted from TestRail
    :param format_output: html, json, xls, xlsx, csv, yam
    :return: statistics
            each row contains test specific info and failure reason group
            whom test is belong
    """

    if format_out != 'html':
        return failure_group_dict
    html_statistics = {}
    for failure, tests in failure_group_dict.items():
        # let's through list of tests
        ftype = failure.split('___message___')[0]
        skipped = (ftype.find('skipped___type___') == 0)
        if not skipped:
            if not html_statistics.get(ftype):
                html_statistics[ftype] = {}
            if not html_statistics[ftype].get(failure):
                html_statistics[ftype][failure] = []
            for test in tests:
                html_statistics[ftype][failure].append(test)
    return html_statistics


def dump_statistics(statistics, format_output=None, file_output=None):
    """ Save statistics info to file according to requested format
    Note: Please, follow tablib python lib supported formats
    http://docs.python-tablib.org/en/latest/

    non hml format is going to be flat
    html format shall use rowspan for tests under one failure group

    :param statistics: list
    :param format_output: html, json, xls, xlsx, csv, yam
    :param file_output: output file path
    :return: None
    """

    filename = None
    data = tablib.Dataset()
    html_header = "<table border=1><tr><th>FailureType</th>" \
                  "<th>FailureGroup</th><th>Test</th><th>Bug</th></tr>"
    html_buttom = "</table>"
    html = ""
    if format_output and file_output:
        filename = ".".join([file_output, format_output])
    if format_output != 'html':
        data.json = json.dumps(statistics)
    else:
        html_body = ""
        for failure_type in statistics.keys():
            rowspan_failure_type = len([j for i in statistics.
                                        get(failure_type).keys()
                                        for j in statistics.
                                        get(failure_type).get(i)])
            failure_groups = sorted(statistics.get(failure_type).keys())
            rowspan_failure_group = len([j for j in statistics.
                                         get(failure_type).
                                         get(failure_groups[0])])
            tests = statistics.get(failure_type).get(failure_groups[0])
            failure_message = ": ".join(failure_groups[0].
                                        split('___type___')[1].
                                        split('___message___'))
            failure_message = re.sub('\t', '&nbsp;&nbsp;&nbsp;&nbsp;',
                                     failure_message)
            failure_message = '<br>'.join(failure_message.splitlines())

            html_bugs = "<br>". \
                join(['<a href={}>#{}</a>: {}'.
                     format(bug.get('url'),
                            bug.get('id'),
                            bug.get('title'))
                      for bug in tests[0].get('bugs')])
            html_tr = '<tr>' \
                      '<td rowspan="{}">count groups:{} / ' \
                      'count tests:{}<br>{}</td>' \
                      '<td rowspan="{}">count tests: {}<br>{}</td>' \
                      '<td><font color={}>{}</font>' \
                      '<br><a href={}>{}</a>' \
                      '<br><a href={}>[job]</a></td>' \
                      '<td>{}</td>'\
                      '</tr>'.format(rowspan_failure_type,
                                     len(failure_groups),
                                     rowspan_failure_type,
                                     failure_type,
                                     rowspan_failure_group,
                                     rowspan_failure_group,
                                     failure_message,
                                     tests[0].get('testresult_status_color'),
                                     tests[0].get('testresult_status'),
                                     tests[0].get('testresult_url'),
                                     tests[0].get('test'),
                                     tests[0].get('test_fail_url'),
                                     html_bugs)
            html_body += html_tr
            if len(tests) > 1:
                for i in tests[1:]:
                    html_bugs = "<br>".\
                        join(['<a href={}>#{}</a>: {}'.
                             format(bug.get('url'),
                                    bug.get('id'),
                                    bug.get('title'))
                             for bug in i.get('bugs')])
                    html_tr = "".join(["<tr>",
                                       "<td><font color={}>{}</font>"
                                       "<br><a href={}>{}</a>"
                                       "<br><a href={}>[job]</a></td>\
                                       <td>{}</td>".
                                       format(i.get('testresult_status_color'),
                                              i.get('testresult_status'),
                                              i.get('testresult_url'),
                                              i.get('test'),
                                              i.get('test_fail_url'),
                                              html_bugs),
                                       "</tr>"])
                    html_body += html_tr
            for fgroup in failure_groups[1:]:
                tstat = statistics.get(failure_type).get(fgroup)
                rowspan_fg = len(tstat)
                failure_message = ": ".join(fgroup.
                                            split('___type___')[1].
                                            split('___message___'))
                failure_message = re.sub('\t', '&nbsp;&nbsp;&nbsp;&nbsp;',
                                         failure_message)
                failure_message = '<br>'.join(failure_message.splitlines())
                html_bugs = "<br>". \
                    join(['<a href={}>#{}</a>: {}'.
                         format(bug.get('url'),
                                bug.get('id'),
                                bug.get('title'))
                          for bug in tstat[0].get('bugs')])
                html_tr = '<tr>' \
                          '<td rowspan="{}">{}<br>{}</td>' \
                          '<td><font color={}>{}</font>' \
                          '<br><a href={}>{}</a>' \
                          '<br><a href={}>[job]</a></td>' \
                          '<td>{}</td>' \
                          '</tr>'.format(rowspan_fg, rowspan_fg,
                                         failure_message,
                                         tstat[0].
                                         get('testresult_status_color'),
                                         tstat[0].get('testresult_status'),
                                         tstat[0].get('testresult_url'),
                                         tstat[0].get('test'),
                                         tstat[0].get('test_fail_url'),
                                         html_bugs)
                html_body += html_tr
                if len(tstat) > 1:
                    for i in tstat[1:]:
                        html_bugs = "<br>". \
                            join(['<a href={}>#{}</a>: {}'.
                                 format(bug.get('url'),
                                        bug.get('id'),
                                        bug.get('title'))
                                  for bug in i.get('bugs')])
                        color = i.get('testresult_status_color')
                        html_tr = "".join(["<tr>",
                                           "<td><font color={}>{}</font>"
                                           "<br><a href={}>{}</a>"
                                           "<br><a href={}>[job]</a></td>\
                                           <td>{}</td>".
                                          format(color,
                                                 i.get('testresult_status'),
                                                 i.get('testresult_url'),
                                                 i.get('test'),
                                                 i.get('test_fail_url'),
                                                 html_bugs),
                                           "</tr>"])
                        html_body += html_tr
        html += html_header
        html += html_body
        html += html_buttom
    if filename:
        with open(filename, 'w') as fileoutput:
            if format_output not in ['html']:
                mdata = getattr(data, format_output)
                fileoutput.write(mdata)
            else:
                fileoutput.write(html)


def publish_statistics(stat):
    """ Publish statistics info to TestRail
    Note: Please, follow tablib python lib supported formats

    :param statistics: list.
        Each item contains test specific info and failure reason group
    :return: True/False
    """

    dump_statistics(stat, format_output='html',
                    file_output='/tmp/failure_groups_statistics')
    # We've got file and it shall be uploaded to TestRail to custom field
    # but TestRail shall be extended at first. Waiting...
    return True


def main():
    """
    :param argv: command line arguments
    :return: None
    """

    parser = argparse.ArgumentParser(description='Get downstream build info'
                                     ' for Jenkins swarm.runner build.'
                                     ' Generate matrix statisctics:'
                                     ' (failure group -> builds & tests).'
                                     ' Publish matrix to Testrail'
                                     ' if necessary.')
    parser.add_argument('-n', '--build-number', type=int, required=False,
                        dest='build_number', help='Jenkins job build number')
    parser.add_argument('-j', '--job-name', type=str,
                        dest='job_name', default='9.0.swarm.runner',
                        help='Name of Jenkins job which runs tests (runner)')
    parser.add_argument('-f', '--format', type=str, dest='formatfile',
                        default='html',
                        help='format statistics: html,json,table')
    parser.add_argument('-o', '--out', type=str, dest="fileoutput",
                        default='failure_groups_statistics',
                        help='Save statistics to file')
    parser.add_argument('-t', '--track', action="store_true",
                        help='Publish statistics to TestPlan description')
    parser.add_argument('-q', '--quiet', action="store_true",
                        help='Be quiet (disable logging except critical) '
                             'Overrides "--verbose" option.')
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable debug logging.")
    args = parser.parse_args()

    if args.verbose:
        logger.setLevel(DEBUG)
    if args.quiet:
        logger.setLevel(CRITICAL)
    if args.formatfile and\
       args.formatfile not in ['json', 'html', 'xls', 'xlsx', 'yaml', 'csv']:
        logger.info('Not supported format output. Exit')
        return 2
    if not args.build_number:
        args.build_number = get_latest_build_number()

    logger.info('Getting subbuilds for {} {}'.format(args.job_name,
                                                     args.build_number))
    subbuildsfilename = "-".join(['subbuilds', args.job_name,
                                  str(args.build_number), '.json'])
    if not os.path.exists(subbuildsfilename):
        subbuilds = get_sub_builds(args.build_number)
        json.dump(subbuilds, open(subbuildsfilename, 'w'))
    else:
        subbuilds = json.load(open(subbuildsfilename))
    if not subbuilds:
        logger.error('Necessary subbuilds info are absent. Exit')
        return 3
    logger.info('{} Subbuilds have been found'.format(len(subbuilds)))

    logger.info('Calculating failure groups')
    failure_gdfilename = "-".join(['failure_groups', args.job_name,
                                   str(args.build_number), '.json'])
    if not os.path.exists(failure_gdfilename):
        failure_gd = get_global_failure_group_list(subbuilds)[0]
        json.dump(failure_gd, open(failure_gdfilename, 'w'))
    else:
        failure_gd = json.load(open(failure_gdfilename))
    if not failure_gd:
        logger.error('Necessary failure grpoup info are absent. Exit')
        return 4
    logger.info('{} Failure groups have been found'.format(len(failure_gd)))

    logger.info('Getting TestRail data')
    testrail_testdata_filename = "-".join(['testrail_data', args.job_name,
                                           str(args.build_number), '.json'])
    if not os.path.exists(testrail_testdata_filename):
        testrail_testdata = get_testrail_testdata(subbuilds)
        json.dump(testrail_testdata, open(testrail_testdata_filename, 'w'))
    else:
        testrail_testdata = json.load(open(testrail_testdata_filename))
    if not testrail_testdata:
        logger.error('Necessary testrail info are absent. Exit')
        return 5
    logger.info('TestRail data have been downloaded')

    logger.info('Getting TestRail bugs')
    testrail_bugs = get_bugs(subbuilds, testrail_testdata)
    if not testrail_bugs:
        logger.error('Necessary testrail bugs info are absent. Exit')
        return 6
    logger.info('TestRail bugs have been got')

    logger.info('Update subbuilds data')
    update_subbuilds_failuregroup(subbuilds, failure_gd,
                                  testrail_testdata,
                                  testrail_bugs)
    logger.info('Subbuilds data have been updated')

    logger.info('Generating statistics across all failure groups')
    statistics = get_statistics(failure_gd, format_out=args.formatfile)
    if not statistics:
        logger.error('Necessary statistics info are absent. Exit')
        return 7
    logger.info('Statistics have been generated')

    if args.fileoutput and args.formatfile:
        logger.info('Save statistics')
        dump_statistics(statistics, args.formatfile, args.fileoutput)
        logger.info('Statistics have been saved')
    if args.track:
        logger.info('Publish statistics to TestRail')
        if publish_statistics(statistics):
            logger.info('Statistics have been published')
        else:
            logger.info('Statistics have not been published'
                        'due to internal issue')

if __name__ == '__main__':
    sys.exit(main())
