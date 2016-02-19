#    Copyright 2013 Mirantis, Inc.
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

import functools
import traceback
import sys
import hashlib

from proboscis import SkipTest

from fuelweb_test.helpers.utils import pull_out_logs_via_ssh
from fuelweb_test.helpers.decorators import create_diagnostic_snapshot

from system_test import logger


def make_snapshot_if_step_fail(func):
    """Generate diagnostic snapshot if step fail.

      - Show test case method name and scenario from docstring.
      - Create a diagnostic snapshot of environment in cases:
            - if the test case passed;
            - if error occurred in the test case.
      - Fetch logs from master node if creating the diagnostic
        snapshot has failed.
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            result = func(*args, **kwargs)
        except SkipTest:
            raise SkipTest()
        except Exception as test_exception:
            exc_trace = sys.exc_traceback
            name = 'error_%s' % func.__name__
            case_name = getattr(func, '_base_class', None)
            step_num = getattr(func, '_step_num', None)
            config_name = getattr(func, '_config_case_group', None)
            description = "Failed in method '%s'." % func.__name__
            if args[0].env is not None:
                try:
                    create_diagnostic_snapshot(args[0].env,
                                               "fail", name)
                except:
                    logger.error("Fetching of diagnostic snapshot failed: {0}".
                                 format(traceback.format_exc()))
                    try:
                        with args[0].env.d_env.get_admin_remote()\
                                as admin_remote:
                            pull_out_logs_via_ssh(admin_remote, name)
                    except:
                        logger.error("Fetching of raw logs failed: {0}".
                                     format(traceback.format_exc()))
                finally:
                    logger.debug(args)
                    try:
                        if all([case_name, step_num, config_name]):
                            _hash = hashlib.sha256(config_name)
                            _hash = _hash.hexdigest()[:8]
                            snapshot_name = "{case}_{config}_{step}".format(
                                case=case_name,
                                config=_hash,
                                step="Step{:03d}".format(step_num)
                            )
                        else:
                            snapshot_name = name[-50:]
                        args[0].env.make_snapshot(snapshot_name=snapshot_name,
                                                  description=description,
                                                  is_make=True)
                    except:
                        logger.error("Error making the environment snapshot:"
                                     " {0}".format(traceback.format_exc()))
            raise test_exception, None, exc_trace
        return result
    return wrapper

