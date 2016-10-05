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

from __future__ import absolute_import
from __future__ import unicode_literals

import logging
import unittest

# pylint: disable=import-error
import mock
from mock import call
from mock import Mock
from mock import patch
# pylint: enable=import-error

from core.helpers import log_helpers

# pylint: disable=no-self-use


@mock.patch('core.helpers.log_helpers.logger', autospec=True)
class TestLogWrap(unittest.TestCase):
    def test_no_args(self, logger):
        @log_helpers.logwrap
        def func():
            return 'No args'

        result = func()
        self.assertEqual(result, 'No args')
        logger.assert_has_calls((
            mock.call.log(
                level=logging.DEBUG,
                msg="Calling: \n'func'()"
            ),
            mock.call.log(
                level=logging.DEBUG,
                msg="Done: 'func' with result:\n{}".format(repr(result))
            ),
        ))

    def test_args_simple(self, logger):
        arg = 'test arg'

        @log_helpers.logwrap
        def func(tst):
            return tst

        result = func(arg)
        self.assertEqual(result, arg)
        logger.assert_has_calls((
            mock.call.log(
                level=logging.DEBUG,
                msg="Calling: \n'func'(\n    'tst'={},\n)".format(
                    log_helpers.pretty_repr(
                        arg, indent=8, no_indent_start=True)
                )
            ),
            mock.call.log(
                level=logging.DEBUG,
                msg="Done: 'func' with result:\n{}".format(repr(result))
            ),
        ))

    def test_args_defaults(self, logger):
        arg = 'test arg'

        @log_helpers.logwrap
        def func(tst=arg):
            return tst

        result = func()
        self.assertEqual(result, arg)
        logger.assert_has_calls((
            mock.call.log(
                level=logging.DEBUG,
                msg="Calling: \n'func'(\n    'tst'={},\n)".format(
                    log_helpers.pretty_repr(
                        arg, indent=8, no_indent_start=True))
            ),
            mock.call.log(
                level=logging.DEBUG,
                msg="Done: 'func' with result:\n{}".format(repr(result))
            ),
        ))

    def test_args_complex(self, logger):
        string = 'string'
        dictionary = {'key': 'dictionary'}

        @log_helpers.logwrap
        def func(param_string, param_dictionary):
            return param_string, param_dictionary

        result = func(string, dictionary)
        self.assertEqual(result, (string, dictionary))
        # raise ValueError(logger.mock_calls)
        logger.assert_has_calls((
            mock.call.log(
                level=logging.DEBUG,
                msg="Calling: \n'func'("
                    "\n    'param_string'={string},"
                    "\n    'param_dictionary'={dictionary},\n)".format(
                        string=log_helpers.pretty_repr(
                            string,
                            indent=8, no_indent_start=True),
                        dictionary=log_helpers.pretty_repr(
                            dictionary,
                            indent=8, no_indent_start=True)
                    )
            ),
            mock.call.log(
                level=logging.DEBUG,
                msg="Done: 'func' with result:\n{}".format(
                    log_helpers.pretty_repr(result))
            ),
        ))

    def test_args_kwargs(self, logger):
        targs = ['string1', 'string2']
        tkwargs = {'key': 'tkwargs'}

        @log_helpers.logwrap
        def func(*args, **kwargs):
            return tuple(args), kwargs

        result = func(*targs, **tkwargs)
        self.assertEqual(result, (tuple(targs), tkwargs))
        # raise ValueError(logger.mock_calls)
        logger.assert_has_calls((
            mock.call.log(
                level=logging.DEBUG,
                msg="Calling: \n'func'("
                    "\n    'args'={args},"
                    "\n    'kwargs'={kwargs},\n)".format(
                        args=log_helpers.pretty_repr(
                            tuple(targs),
                            indent=8, no_indent_start=True),
                        kwargs=log_helpers.pretty_repr(
                            tkwargs,
                            indent=8, no_indent_start=True)
                    )
            ),
            mock.call.log(
                level=logging.DEBUG,
                msg="Done: 'func' with result:\n{}".format(
                    log_helpers.pretty_repr(result))
            ),
        ))

    def test_negative(self, logger):
        @log_helpers.logwrap
        def func():
            raise ValueError('as expected')

        with self.assertRaises(ValueError):
            func()

        logger.assert_has_calls((
            mock.call.log(
                level=logging.DEBUG,
                msg="Calling: \n'func'()"
            ),
            mock.call.log(
                level=logging.ERROR,
                msg="Failed: \n'func'()",
                exc_info=True
            ),
        ))

    def test_negative_substitutions(self, logger):
        new_logger = mock.Mock(spec='logging.Logger', name='logger')
        log = mock.Mock(name='log')
        new_logger.attach_mock(log, 'log')

        @log_helpers.logwrap(
            log=new_logger,
            log_level=logging.INFO,
            exc_level=logging.WARNING
        )
        def func():
            raise ValueError('as expected')

        with self.assertRaises(ValueError):
            func()

        self.assertEqual(len(logger.mock_calls), 0)
        log.assert_has_calls((
            mock.call(
                level=logging.INFO,
                msg="Calling: \n'func'()"
            ),
            mock.call(
                level=logging.WARNING,
                msg="Failed: \n'func'()",
                exc_info=True
            ),
        ))


@patch('logging.StreamHandler')
@patch('core.helpers.log_helpers.logger', autospec=True)
class TestQuietLogger(unittest.TestCase):
    def test_default(self, logger_obj, handler_cls):
        handler = Mock()
        handler.configure_mock(level=logging.INFO)
        handler_cls.return_value = handler

        with log_helpers.QuietLogger():
            log_helpers.logger.warning('Test')

        handler.assert_has_calls((
            call.setLevel(logging.INFO + 1),
            call.setLevel(logging.INFO)
        ))

        logger_obj.assert_has_calls((call.warning('Test'), ))

    def test_upper_level(self, logger_obj, handler_cls):
        handler = Mock()
        handler.configure_mock(level=logging.INFO)
        handler_cls.return_value = handler

        with log_helpers.QuietLogger(logging.WARNING):
            log_helpers.logger.warning('Test')

        handler.assert_has_calls((
            call.setLevel(logging.WARNING + 1),
            call.setLevel(logging.INFO)
        ))

        logger_obj.assert_has_calls((call.warning('Test'), ))

    def test_lower_level(self, logger_obj, handler_cls):
        handler = Mock()
        handler.configure_mock(level=logging.INFO)
        handler_cls.return_value = handler

        with log_helpers.QuietLogger(logging.DEBUG):
            log_helpers.logger.warning('Test')

        handler.assert_has_calls((
            call.setLevel(logging.INFO),
        ))

        logger_obj.assert_has_calls((
            call.debug(
                'QuietLogger requested lower level, than is already set. '
                'Not changing level'),
            call.warning('Test'),
        ))
