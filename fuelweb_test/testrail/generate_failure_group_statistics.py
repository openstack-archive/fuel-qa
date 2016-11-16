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
import re
import sys
from logging import CRITICAL
from logging import DEBUG

import tablib
import xmltodict
from fuelweb_test.testrail.builds import Build
from fuelweb_test.testrail.builds import get_build_artifact
from fuelweb_test.testrail.launchpad_client import LaunchpadBug
from fuelweb_test.testrail.report import get_version
from fuelweb_test.testrail.settings import FAILURE_GROUPING
from fuelweb_test.testrail.settings import JENKINS
from fuelweb_test.testrail.settings import logger
from fuelweb_test.testrail.settings import TestRailSettings
from fuelweb_test.testrail.testrail_client import TestRailProject


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
    macre = re.compile(r'\b[a-fA-F0-9]{2}[:]{5}[a-fA-F0-9]{2}\b')
    digitre = re.compile(r'\b(?:[0-9]{1,3}){1,50}\b')
    hexre = re.compile(r'\b(?:[0-9a-fA-F]{1,8}){1,50}\b')

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


def get_bugs(subbuilds, testraildata):
    """Get bugs of failed tests

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
            iid = int(re.search(r'.*bugs?/(\d+)/?', i[2]).group(1))
            title = get_bug_title(iid) or str(iid)
            label = get_label(i[3], testraildata.get('statuses'))
            color = get_color(i[3], testraildata.get('statuses'))
            item = {'id': iid,
                    'url': i[2],
                    'title': title,
                    'label': label,
                    'color': color}
            total_bugs[i[0]].append(item)
    return total_bugs


def get_bug_title(bugid):
    """ Get bug title

    :param bugid: int - launchpad bugid
    :return: bug title - str
    """

    targets = LaunchpadBug(bugid).targets
    return targets[0].get('title', '')


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


def get_testrail():
    """ Get test rail instance """
    logger.info('Initializing TestRail Project configuration...')
    return TestRailProject(url=TestRailSettings.url,
                           user=TestRailSettings.user,
                           password=TestRailSettings.password,
                           project=TestRailSettings.project)


def generate_test_plan_name(job_name, build_number):
    """ Generate name of TestPlan basing on iso image name
        taken from Jenkins job build parameters"""
    runner_build = Build(job_name, build_number)
    milestone, iso_number, prefix = get_version(runner_build.build_data)
    return ' '.join(filter(lambda x: bool(x),
                           (milestone, prefix, 'iso', '#' + str(iso_number))))


def generate_test_run_name(job_name, build_number):
    """ Generate name of TestRun basing on iso image name
        taken from Jenkins job build parameters"""
    runner_build = Build(job_name, build_number)
    milestone = get_version(runner_build.build_data)[0]
    return ''.join(filter(lambda x: bool(x),
                          ('[', milestone, ']', ' Swarm')))


def get_runid_by_testplan(testplan, runname):
    """ Get test rail plan and run by Swarm Jenkins job

    :param testplan: testreil testplan
    :param runname: testreil runname
    :return: id: testrail run id
    """

    for j in testplan.get('entries'):
        for k in j.get('runs'):
            if k.get('name') == runname:
                return k.get('id')
    return None


def get_testrail_testdata(job_name, build_number):
    """ Get test rail plan and run by Swarm Jenkins job

    :param sub_builds: list of dict per each subbuild
    :return: plan, run: tuple - TestRail plan and run dicts
    """

    planname = generate_test_plan_name(job_name,
                                       build_number)
    runname = generate_test_run_name(job_name,
                                     build_number)
    testrail_project = get_testrail()
    project = testrail_project.project
    plan = testrail_project.get_plan_by_name(planname)
    runid = get_runid_by_testplan(plan, runname)
    if not runid:
        return {}
    run = testrail_project.get_run(runid)
    milestone = testrail_project.get_milestone_by_name(
        TestRailSettings.milestone)
    statuses = testrail_project.get_statuses()
    tests = testrail_project.get_tests(run.get('id'))
    results = testrail_project.get_results_for_run(run.get('id'))
    return {'project': project,
            'plan': plan,
            'run': run,
            'milestone': milestone,
            'statuses': statuses,
            'tests': tests,
            'results': results}


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
    logger.info('Getting subbuild {} {}'.format(job_name,
                                                build_number))
    runner_build = Build(job_name, build_number)
    buildinfo = runner_build.get_build_data(depth=0)
    if not buildinfo:
        logger.error('Getting subbuilds info is failed. '
                     'Job={} Build={}'.format(job_name, build_number))
        return test_data
    try:
        artifact_paths = [v for i in buildinfo.get('artifacts')
                          for k, v in i.items() if k == 'relativePath' and
                          v == JENKINS.get('xml_testresult_file_name')][0]
        artifact_url = "/".join([jenkins_url, 'job', job_name,
                                 str(build_number)])
        xdata = get_build_artifact(artifact_url, artifact_paths)
        test_data = xmltodict.parse(xdata, xml_attribs=True)
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

    runner_build = Build(job_name, build_number)
    parent_build_info = runner_build.get_build_data(depth=0)
    sub_builds = None
    if parent_build_info:
        sub_builds = parent_build_info.get('subBuilds')
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
    return sub_builds, parent_build_info


def get_global_failure_group_list(
        sub_builds, threshold=FAILURE_GROUPING.get('threshold')):
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
    for num1, key1 in enumerate(failure_group_dict):
        # pylint: disable=C0201
        for key2 in failure_group_dict.keys()[num1 + 1:]:
            # let's skip grouping if len are different more 10%
            if key1 == key2 or abs(float(len(key1) / len(key2))) >\
                    FAILURE_GROUPING.get('max_len_diff'):
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
    :return:    statistics
    """

    if format_out != 'html':
        return failure_group_dict
    html_statistics = {}
    failure_type_count = 0
    failure_group_count = 0
    ctests = list()
    cbugs = list()
    for failure, tests in failure_group_dict.items():
        # let's through list of tests
        ftype = failure.split('___message___')[0]
        skipped = (ftype.find('skipped___type___') == 0)
        if not skipped:
            if not html_statistics.get(ftype):
                html_statistics[ftype] = {}
                failure_type_count += 1
            if not html_statistics[ftype].get(failure):
                html_statistics[ftype][failure] = []
                failure_group_count += 1
            for test in tests:
                html_statistics[ftype][failure].append(test)
                ctests.append(test.get('test'))
                for bug in test.get('bugs', {}):
                    cbugs.append(bug.get('id'))
    return {'html_statistics': html_statistics,
            'failure_type_count': failure_type_count,
            'failure_group_count': failure_group_count,
            'test_count': len(set(ctests)),
            'bug_count': len(set(cbugs))}


def dump_statistics(statistics, build_number, job_name,
                    format_output=None, file_output=None):
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
    html_statistics = statistics.get('html_statistics')
    data = tablib.Dataset()
    html_top = "<html><body>"
    html_total_count = "<table border=1><tr>" \
                       "<th>Build</th>" \
                       "<th>Job</th>" \
                       "<th>FailureTypeCount</th>" \
                       "<th>FailureGroupCount</th>" \
                       "<th>TestCount</th>" \
                       "<th>BugCount</th></tr>"\
                       "<tr><td><font color='#ff0000'>{}</font>" \
                       "</td><td>{}</td>" \
                       "<td>{}</td>" \
                       "<td><font color='#00ff00'>{}</font></td>" \
                       "<td>{}</td>" \
                       "<td><font color='#0000ff'>{}</font></td>" \
                       "</tr></table>".\
        format(build_number,
               job_name,
               statistics.get('failure_type_count'),
               statistics.get('failure_group_count'),
               statistics.get('test_count'),
               statistics.get('bug_count'))

    html_failurestat_header = "<table border=1><tr><th>FailureType</th>" \
                              "<th>FailureGroup</th>" \
                              "<th>Test</th><th>Bug</th></tr>"
    html_buttom = "</table></body></html>"
    html = ""
    if format_output and file_output:
        filename = ".".join([file_output, format_output])
    if format_output != 'html':
        data.json = json.dumps(html_statistics)
    else:
        html_body = ""
        for failure_type in html_statistics.keys():
            rowspan_failure_type = len([j for i in html_statistics.
                                        get(failure_type).keys()
                                        for j in html_statistics.
                                        get(failure_type).get(i)])
            failure_groups = sorted(html_statistics.get(failure_type).keys())
            rowspan_failure_group = len([j for j in html_statistics.
                                         get(failure_type).
                                         get(failure_groups[0])])
            tests = html_statistics.get(failure_type).get(failure_groups[0])
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
                tstat = html_statistics.get(failure_type).get(fgroup)
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
        html += html_top
        html += html_total_count
        html += html_failurestat_header
        html += html_body
        html += html_buttom
    if filename:
        with open(filename, 'w') as fileoutput:
            if format_output not in ['html']:
                mdata = getattr(data, format_output)
                fileoutput.write(mdata)
            else:
                fileoutput.write(html)


def publish_statistics(stat, build_number, job_name):
    """ Publish statistics info to TestRail
    Note: Please, follow tablib python lib supported formats

    :param statistics: list.
        Each item contains test specific info and failure reason group
    :return: True/False
    """

    dump_statistics(stat, build_number, job_name,
                    format_output='html',
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
                                     ' Generate matrix statistics:'
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
        runner_build = Build(args.job_name, 'latest')
        logger.info('Latest build number is {}. Job is {}'.
                    format(runner_build.number, args.job_name))
        args.build_number = runner_build.number

    logger.info('Getting subbuilds for {} {}'.format(args.job_name,
                                                     args.build_number))
    subbuilds, swarm_jenkins_info = get_sub_builds(args.build_number)
    if not subbuilds or not swarm_jenkins_info:
        logger.error('Necessary subbuilds info are absent. Exit')
        return 3
    logger.info('{} Subbuilds have been found'.format(len(subbuilds)))

    logger.info('Calculating failure groups')
    failure_gd = get_global_failure_group_list(subbuilds)[0]
    if not failure_gd:
        logger.error('Necessary failure grpoup info are absent. Exit')
        return 4
    logger.info('{} Failure groups have been found'.format(len(failure_gd)))

    logger.info('Getting TestRail data')
    testrail_testdata = get_testrail_testdata(args.job_name,
                                              args.build_number)
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
        dump_statistics(statistics, args.build_number, args.job_name,
                        args.formatfile, args.fileoutput)
        logger.info('Statistics have been saved')
    if args.track:
        logger.info('Publish statistics to TestRail')
        if publish_statistics(statistics, args.build_number, args.job_name):
            logger.info('Statistics have been published')
        else:
            logger.info('Statistics have not been published'
                        'due to internal issue')


if __name__ == '__main__':
    sys.exit(main())
