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

from __future__ import unicode_literals

import logging.config
import os
import warnings

from core.helpers.log_helpers import logwrap
from core.helpers.log_helpers import QuietLogger

from fuelweb_test.settings import LOGS_DIR

if not os.path.exists(LOGS_DIR):
    os.makedirs(LOGS_DIR)

_log_config = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'default': {
            'format': '%(asctime)s - %(levelname)s %(filename)s:'
                      '%(lineno)d -- %(message)s',
            'datefmt': '%Y-%m-%d %H:%M:%S'
        },
    },
    'handlers': {
        'console': {
            'level': 'INFO',
            'class': 'logging.StreamHandler',
            'formatter': 'default'
        },
        'tests_log': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'formatter': 'default',
            'filename': os.path.join(LOGS_DIR, 'sys_test.log'),
            'mode': 'w',
            'encoding': 'utf8',
        },
        'devops_log': {
            'level': 'DEBUG',
            'class': 'logging.FileHandler',
            'formatter': 'default',
            'filename': os.path.join(LOGS_DIR, 'devops.log'),
            'mode': 'w',
            'encoding': 'utf8',
        },
        'null': {
            'level': 'CRITICAL',
            'class': 'logging.NullHandler',
        },
    },
    'loggers': {
        # Log all to log file , but by default only warnings.
        '': {
            'handlers': ['tests_log'],
            'level': 'WARNING',
        },
        'fuel-qa': {
            'handlers': ['console'],
            'level': 'DEBUG',
            'propagate': True
        },
        'devops': {
            'handlers': ['console', 'devops_log'],
            'level': 'DEBUG',
            'propagate': True  # Test log too
        },
        # py.warnings is changed by Django -> do not propagate
        'py.warnings': {
            'handlers': ['console', 'tests_log'],
            'level': 'WARNING',
            'propagate': False
        },
        'paramiko': {'level': 'WARNING'},
        'iso8601': {'level': 'WARNING'},
        'keystoneauth': {'level': 'WARNING'},
    }
}

logging.config.dictConfig(_log_config)
logging.captureWarnings(True)  # Log warnings
# Filter deprecation warnings: log only when deletion announced
warnings.filterwarnings(
    'default',
    message=r'.*(drop|remove)+.*',
    category=DeprecationWarning)

logger = logging.getLogger('fuel-qa.{}'.format(__name__))

__all__ = ['QuietLogger', 'logwrap', 'logger']
