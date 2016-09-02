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
from __future__ import print_function

import unittest

# pylint: disable=import-error
from mock import call
from mock import patch
# pylint: enable=import-error

from core.helpers import setup_teardown


# Get helpers names (python will try to mangle it inside classes)
get_arg_names = setup_teardown.__get_arg_names
getcallargs = setup_teardown.__getcallargs
call_in_context = setup_teardown.__call_in_context


class TestWrappers(unittest.TestCase):
    def test_get_arg_names(self):
        def func_no_args():
            pass

        def func_arg(single):
            pass

        def func_args(first, last):
            pass

        self.assertEqual(
            get_arg_names(func_no_args),
            []
        )

        self.assertEqual(
            get_arg_names(func_arg),
            ['single']
        )

        self.assertEqual(
            get_arg_names(func_args),
            ['first', 'last']
        )

    def test_getcallargs(self):
        def func_no_def(arg1, arg2):
            pass

        def func_def(arg1, arg2='arg2'):
            pass

        self.assertEqual(
            dict(getcallargs(func_no_def, *['arg1', 'arg2'], **{})),
            {'arg1': 'arg1', 'arg2': 'arg2'}
        )

        self.assertEqual(
            dict(getcallargs(func_no_def, *['arg1'], **{'arg2': 'arg2'})),
            {'arg1': 'arg1', 'arg2': 'arg2'}
        )

        self.assertEqual(
            dict(getcallargs(
                func_no_def, *[], **{'arg1': 'arg1', 'arg2': 'arg2'})),
            {'arg1': 'arg1', 'arg2': 'arg2'}
        )

        self.assertEqual(
            dict(getcallargs(func_def, *['arg1'], **{})),
            {'arg1': 'arg1', 'arg2': 'arg2'}
        )

        self.assertEqual(
            dict(getcallargs(func_def, *[], **{'arg1': 'arg1'})),
            {'arg1': 'arg1', 'arg2': 'arg2'}
        )

        self.assertEqual(
            dict(getcallargs(
                func_def, *[], **{'arg1': 'arg1', 'arg2': 2})),
            {'arg1': 'arg1', 'arg2': 2}
        )

    def test_call_in_context(self):
        def func_no_args():
            return None

        def func_args(first='first', last='last'):
            return first, last

        def func_self_arg(self):
            return self

        def func_cls_arg(cls):
            return cls

        class Tst(object):
            @classmethod
            def tst(cls):
                return cls

        self.assertIsNone(
            call_in_context(
                func=func_no_args,
                context_args={}
            )
        )

        self.assertIsNone(
            call_in_context(
                func=func_no_args,
                context_args={'test': 'val'}
            )
        )

        self.assertEqual(
            call_in_context(
                func=func_args,
                context_args={'first': 0, 'last': -1}
            ),
            (0, -1)
        )

        with self.assertRaises(ValueError):
            call_in_context(
                func=func_args,
                context_args={}
            )

        self.assertEqual(
            call_in_context(
                func=func_self_arg,
                context_args={'self': self}
            ),
            self
        )

        self.assertEqual(
            call_in_context(
                func=func_cls_arg,
                context_args={'cls': self.__class__}
            ),
            self.__class__
        )

        self.assertEqual(
            call_in_context(
                func=func_cls_arg,
                context_args={'self': self}
            ),
            self.__class__
        )

        self.assertEqual(
            call_in_context(
                func=Tst.tst,
                context_args={'cls': self.__class__}
            ),
            Tst,
            'cls was not filtered from @classmethod!'
        )

        # Allow to replace function by None in special cases
        self.assertIsNone(
            call_in_context(None, {'test_arg': 'test_val'})
        )


@patch('core.helpers.setup_teardown.__getcallargs', return_value={'arg': True})
@patch('core.helpers.setup_teardown.__call_in_context')
class TestSetupTeardown(unittest.TestCase):
    def test_basic(self, call_in, getargs):
        arg = True

        @setup_teardown.setup_teardown()
        def positive_example(arg):
            return arg

        self.assertEqual(positive_example(arg), arg)

        # Real function is under decorator, so we could not make full check
        getargs.assert_called_once()

        call_in.assert_has_calls((
            call(None, {'arg': arg}),
            call(None, {'arg': arg}),
        ))

    def test_applied(self, call_in, getargs):
        arg = True

        def setup_func():
            pass

        def teardown_func():
            pass

        @setup_teardown.setup_teardown(
            setup=setup_func,
            teardown=teardown_func
        )
        def positive_example(arg):
            return arg

        self.assertEqual(positive_example(arg), arg)

        # Real function is under decorator, so we could not make full check
        getargs.assert_called_once()

        call_in.assert_has_calls((
            call(setup_func, {'arg': arg}),
            call(teardown_func, {'arg': arg}),
        ))

    def test_exception_applied(self, call_in, getargs):
        arg = True

        def setup_func():
            pass

        def teardown_func():
            pass

        @setup_teardown.setup_teardown(
            setup=setup_func,
            teardown=teardown_func
        )
        def positive_example(arg):
            raise ValueError(arg)

        with self.assertRaises(ValueError):
            positive_example(arg)

        # Real function is under decorator, so we could not make full check
        getargs.assert_called_once()

        call_in.assert_has_calls((
            call(setup_func, {'arg': arg}),
            call(teardown_func, {'arg': arg}),
        ))
