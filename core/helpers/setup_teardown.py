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

import functools
import inspect

import six

# Setup/Teardown decorators, which is missing in Proboscis.
# Usage: like in Nose.


# pylint: disable=no-member
def __getcallargs(func, *positional, **named):
    """get real function call arguments without calling function

    :rtype: dict
    """
    # noinspection PyUnresolvedReferences
    if six.PY2:
        return inspect.getcallargs(func, *positional, **named)
    sig = inspect.signature(func).bind(*positional, **named)
    sig.apply_defaults()  # after bind we doesn't have defaults
    return sig.arguments


def __get_arg_names(func):
    """get argument names for function

    :param func: func
    :return: list of function argnames
    :rtype: list

    >>> def tst_1():
    ...     pass

    >>> __get_arg_names(tst_1)
    []

    >>> def tst_2(arg):
    ...     pass

    >>> __get_arg_names(tst_2)
    ['arg']
    """
    # noinspection PyUnresolvedReferences
    return (
        [arg for arg in inspect.getargspec(func=func).args] if six.PY2 else
        list(inspect.signature(obj=func).parameters.keys())
    )
# pylint:enable=no-member


def __call_in_context(func, context_args):
    """call function with substitute arguments from dict

    :param func: function or None
    :param context_args: dict
    :type context_args: dict
    :return: function call results

    >>> __call_in_context(None, {})

    >>> def print_print():
    ...     print ('print')

    >>> __call_in_context(print_print, {})
    print

    >>> __call_in_context(print_print, {'val': 1})
    print

    >>> def print_val(val):
    ...     print(val)

    >>> __call_in_context(print_val, {'val': 1})
    1
    """
    if func is None:
        return

    func_args = __get_arg_names(func)
    if not func_args:
        return func()

    if inspect.ismethod(func) and 'cls' in func_args:
        func_args.remove('cls')
        # cls if used in @classmethod and could not be posted
        # via args or kwargs, so classmethod decorators always has access
        # to it's own class only, except direct class argument
    elif 'self' in context_args:
        context_args.setdefault('cls', context_args['self'].__class__)
    try:
        arg_values = [context_args[k] for k in func_args]
    except KeyError as e:
        raise ValueError("Argument '{}' is missing".format(str(e)))

    return func(*arg_values)


def setup_teardown(setup=None, teardown=None):
    """Add setup and teardown for functions and methods.

    :param setup: function
    :param teardown: function
    :return:

    >>> def setup_func():
    ...     print('setup_func called')

    >>> def teardown_func():
    ...     print('teardown_func called')

    >>> @setup_teardown(setup=setup_func, teardown=teardown_func)
    ... def positive_example(arg):
    ...     print(arg)

    >>> positive_example(arg=1)
    setup_func called
    1
    teardown_func called

    >>> def print_call(text):
    ...     print (text)

    >>> @setup_teardown(
    ...     setup=lambda: print_call('setup lambda'),
    ...     teardown=lambda: print_call('teardown lambda'))
    ... def positive_example_lambda(arg):
    ...     print(arg)

    >>> positive_example_lambda(arg=1)
    setup lambda
    1
    teardown lambda

    >>> def setup_with_self(self):
    ...     print(
    ...         'setup_with_self: '
    ...         'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...             cls_val=self.cls_val, val=self.val))

    >>> def teardown_with_self(self):
    ...     print(
    ...         'teardown_with_self: '
    ...         'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...             cls_val=self.cls_val, val=self.val))

    >>> def setup_with_cls(cls):
    ...     print(
    ...         'setup_with_cls: cls.cls_val = {cls_val!s}'.format(
    ...             cls_val=cls.cls_val))

    >>> def teardown_with_cls(cls):
    ...     print('teardown_with_cls: cls.cls_val = {cls_val!s}'.format(
    ...             cls_val=cls.cls_val))

    >>> class HelpersBase(object):
    ...     cls_val = None
    ...     def __init__(self):
    ...         self.val = None
    ...     @classmethod
    ...     def cls_setup(cls):
    ...         print(
    ...             'cls_setup: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls.cls_val))
    ...     @classmethod
    ...     def cls_teardown(cls):
    ...         print(
    ...             'cls_teardown: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls.cls_val))
    ...     def self_setup(self):
    ...         print(
    ...             'self_setup: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=self.cls_val, val=self.val))
    ...     def self_teardown(self):
    ...         print(
    ...             'self_teardown: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=self.cls_val, val=self.val))

    >>> class Test(HelpersBase):
    ...     @setup_teardown(
    ...         setup=HelpersBase.self_setup,
    ...         teardown=HelpersBase.self_teardown)
    ...     def test_self_self(self, cls_val=0, val=0):
    ...         print(
    ...             'test_self_self: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=HelpersBase.cls_setup,
    ...         teardown=HelpersBase.cls_teardown)
    ...     def test_self_cls(self, cls_val=1, val=1):
    ...         print(
    ...             'test_self_cls: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=setup_func,
    ...         teardown=teardown_func)
    ...     def test_self_none(self, cls_val=2, val=2):
    ...         print(
    ...             'test_self_cls: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=setup_with_self,
    ...         teardown=teardown_with_self)
    ...     def test_self_ext_self(self, cls_val=-1, val=-1):
    ...         print(
    ...             'test_self_ext_self: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @setup_teardown(
    ...         setup=setup_with_cls,
    ...         teardown=teardown_with_cls)
    ...     def test_self_ext_cls(self, cls_val=-2, val=-2):
    ...         print(
    ...             'test_self_ext_cls: '
    ...             'self.cls_val = {cls_val!s}, self.val = {val!s}'.format(
    ...                 cls_val=cls_val, val=val))
    ...         self.val = val
    ...         self.cls_val = cls_val
    ...     @classmethod
    ...     @setup_teardown(
    ...         setup=HelpersBase.cls_setup,
    ...         teardown=HelpersBase.cls_teardown)
    ...     def test_cls_cls(cls, cls_val=3):
    ...         print(
    ...             'test_cls_cls: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls_val))
    ...         cls.cls_val = cls_val
    ...     @classmethod
    ...     @setup_teardown(
    ...         setup=setup_func,
    ...         teardown=teardown_func)
    ...     def test_cls_none(cls, cls_val=4):
    ...         print(
    ...             'test_cls_none: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls_val))
    ...         cls.cls_val = cls_val
    ...     @classmethod
    ...     @setup_teardown(
    ...         setup=setup_with_cls,
    ...         teardown=teardown_with_cls)
    ...     def test_cls_ext_cls(cls, cls_val=-3):
    ...         print(
    ...             'test_self_ext_cls: cls.cls_val = {cls_val!s}'.format(
    ...                 cls_val=cls_val))
    ...         cls.cls_val = cls_val
    ...     @staticmethod
    ...     @setup_teardown(setup=setup_func, teardown=teardown_func)
    ...     def test_none_none():
    ...         print('test')

    >>> test = Test()

    >>> test.test_self_self()
    self_setup: self.cls_val = None, self.val = None
    test_self_self: self.cls_val = 0, self.val = 0
    self_teardown: self.cls_val = 0, self.val = 0

    >>> test.test_self_cls()
    cls_setup: cls.cls_val = None
    test_self_cls: self.cls_val = 1, self.val = 1
    cls_teardown: cls.cls_val = None

    >>> test.test_self_none()
    setup_func called
    test_self_cls: self.cls_val = 2, self.val = 2
    teardown_func called

    >>> test.test_self_ext_self()
    setup_with_self: self.cls_val = 2, self.val = 2
    test_self_ext_self: self.cls_val = -1, self.val = -1
    teardown_with_self: self.cls_val = -1, self.val = -1

    >>> test.test_self_ext_cls()
    setup_with_cls: cls.cls_val = None
    test_self_ext_cls: self.cls_val = -2, self.val = -2
    teardown_with_cls: cls.cls_val = None

    >>> test.test_cls_cls()
    cls_setup: cls.cls_val = None
    test_cls_cls: cls.cls_val = 3
    cls_teardown: cls.cls_val = None

    >>> test.test_cls_none()
    setup_func called
    test_cls_none: cls.cls_val = 4
    teardown_func called

    >>> test.test_cls_ext_cls()
    setup_with_cls: cls.cls_val = 4
    test_self_ext_cls: cls.cls_val = -3
    teardown_with_cls: cls.cls_val = -3

    >>> test.test_none_none()
    setup_func called
    test
    teardown_func called
    """
    def real_decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            real_args = __getcallargs(func, *args, **kwargs)
            __call_in_context(setup, real_args)
            try:
                result = func(*args, **kwargs)
            finally:
                __call_in_context(teardown, real_args)
            return result
        return wrapper
    return real_decorator
