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

import json


def check_status_code(code):
    def outer_wrap(f):
        def inner_wrap(*args, **kwargs):
            r = f(*args, **kwargs)
            if r.status_code != code:
                raise Exception("Unexpected status code. "
                                "Wanted status code: {0}. "
                                "Got status code: {1}"
                                .format(code, r.status_code))
            return r
        return inner_wrap
    return outer_wrap


def json_to_dict(data):
    return dict(json.loads(data))


def filter_gerrit_response_separator(data):
    return data.replace(")]}\'", "")


def filter_newlines(data):
    return data.replace('\n', '')


def filter_response_text(data):
    data = filter_gerrit_response_separator(data)
    data = filter_newlines(data)
    return data
