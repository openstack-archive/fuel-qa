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


MINUTE = 60
HOUR = MINUTE ** 2
DAY = HOUR * 8
WEEK = DAY * 5


def duration_to_testrail_estimate(duration):
    """Converts duration in minutes to testrail estimate format
    """
    seconds = duration * MINUTE
    week = seconds // WEEK
    days = seconds % WEEK // DAY
    hours = seconds % DAY // HOUR
    minutes = seconds % HOUR // MINUTE
    estimate = ''
    for val, char in ((week, 'w'), (days, 'd'), (hours, 'h'), (minutes, 'm')):
        if val:
            estimate = ' '.join([estimate, '{0}{1}'.format(val, char)])
    return estimate.lstrip()
