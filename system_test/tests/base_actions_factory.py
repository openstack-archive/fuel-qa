#    Copyright 2015 Mirantis, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE_2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import functools

from proboscis import test
from proboscis import after_class
from proboscis import before_class

from fuelweb_test.tests import base_test_case
from fuelweb_test.helpers.utils import TimeStat

from system_test.helpers import utils
from system_test import logger


def step_start_stop(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with TimeStat(func) as timer:
            step_name = getattr(func, '_step_name')
            start_step = '[ START {} ]'.format(step_name)
            header = "<<< {:-^142} >>>".format(start_step)
            logger.info("\n{header}\n".format(header=header))
            result = func(*args, **kwargs)
            spent_time = timer.spent_time
            minutes = int(round(spent_time)) / 60
            seconds = int(round(spent_time)) % 60
            finish_step = "[ FINISH {} STEP TOOK {} min {} sec ]".format(
                step_name, minutes, seconds)
            footer = "<<< {:-^142} >>>".format(finish_step)
            logger.info("\n{footer}\n".format(footer=footer))
        return result
    return wrapper


class BaseActionsFactory(base_test_case.TestBasic):

    @classmethod
    def get_actions(cls):
        """Return all action methods"""
        return {m: getattr(cls, m) for m in
                dir(cls) if
                getattr(getattr(cls, m), '_action_method_', False) or
                getattr(getattr(cls, m), '_nested_action_method_', False)}

    @classmethod
    def get_actions_order(cls):
        """Get order of actions"""
        if getattr(cls, 'actions_order', None) is None:
            raise LookupError("Actions order doesn't exist")

        actions_method = cls.get_actions()
        linear_order = []
        for action in cls.actions_order:
            try:
                action_method = actions_method[action]
            except KeyError:
                import inspect
                source = inspect.getsourcelines(inspect.getmodule(cls))[0]
                counted_data = [n for n in enumerate(source)]
                line_num = [n for (n, l) in counted_data if 'ddd' in l][0]
                cutted = counted_data[line_num - 4:line_num + 4]
                cutted = [(n, l[:-1] + " " * 20 + "<====\n"
                          if n == line_num else l)
                          for (n, l) in cutted]
                cutted = ["Line {line_num:04d}: {line}".format(
                              line_num=n, line=l)
                          for (n, l) in cutted]
                raise LookupError("Class {} orders to run '{}' action as {} "
                                  "step,\n\tbut action method doesn't exist "
                                  "in class.\nLook at '{}':\n\n{}".format(
                                      cls, action,
                                      cls.actions_order.index(action),
                                      inspect.getsourcefile(cls),
                                      ''.join(cutted)))
            if getattr(action_method,
                       '_nested_action_method_', None):
                linear_order.extend(action_method())
            else:
                linear_order.append(action)

        steps = [{"action": step, "method": actions_method[step]} for
                 step in linear_order]

        return steps

    @classmethod
    def caseclass_factory(cls, case_group):
        """Create new cloned cls class contains only action methods"""
        test_steps, scenario = {}, []

        #  Generate human readable class_name, if was method docstring not
        #  described, use generated name
        class_name = "Case_{}__Config_{}".format(cls.__name__, case_group)

        #  Make methods for new testcase class, following by order
        scenario.append("    Scenario:")
        for step, action in enumerate(cls.get_actions_order()):
            n_action = action['action'].replace("_action_", "")
            #  Generate human readable method name, if was method docstring not
            #  described, use generated name. Used when method failed
            step_method_name = "{}.Step{:03d}_{}".format(class_name,
                                                         step,
                                                         n_action)

            method = utils.copy_func(action['method'], step_method_name)
            _step_name = getattr(action['method'],
                                 "__doc__").splitlines()[0]
            setattr(method, "_step_name", "Step {:03d}. {}".format(step,
                                                                   _step_name))
            setattr(method, "_step_num", step)
            setattr(method, "_base_class", cls.__name__)
            setattr(method, "_config_case_group", case_group)

            #  Add step to scenario
            scenario.append("        {}. {}".format(step, _step_name))

            #  Add decorator to cloned method
            for deco in getattr(method, '_deferred_decorator_', []):
                method = deco(method)

            #  if not first step make dependency
            if step > 0:
                prev_step_name = "{}.Step{:03d}_{}".format(
                    class_name,
                    step - 1,
                    cls.get_actions_order()[step - 1]['action'].replace(
                        "_action_", ""))
                depends = [test_steps[prev_step_name]]
            else:
                depends = None

            #  Add start-stop step decorator for measuring time and print
            #  start and finish info
            method = step_start_stop(method)

            test_steps[step_method_name] = test(
                method,
                depends_on=depends)

        #  Create before case methods, start case and setup
        start_method = utils.copy_func(
            getattr(cls, "_start_case"),
            "{}.StartCase".format(class_name))
        test_steps["{}.StartCase".format(class_name)] = before_class(
            start_method)

        if hasattr(cls, 'case_setup'):
            setup_method = utils.copy_func(
                getattr(cls, "case_setup"),
                "{}.CaseSetup".format(class_name))
            setattr(setup_method, "_step_name", "CaseSetup")
            test_steps["{}.CaseSetup".format(class_name)] = before_class(
                step_start_stop(setup_method), runs_after=[start_method])

        if hasattr(cls, 'case_teardown'):
            teardown_method = utils.copy_func(
                getattr(cls, "case_teardown"),
                "{}.CaseTeardown".format(class_name))
            setattr(teardown_method, "_step_name", "CaseTeardown")
            test_steps["{}.CaseTeardown".format(class_name)] = after_class(
                step_start_stop(teardown_method), always_run=True)
        else:
            teardown_method = None

        #  Create case methods, teardown and finish case
        finish_method = utils.copy_func(
            getattr(cls, "_finish_case"),
            "{}.FinishCase".format(class_name))
        test_steps["{}.FinishCase".format(class_name)] = after_class(
            finish_method, always_run=True,
            runs_after=[teardown_method] if teardown_method else [])

        # Generate test case groups
        groups = ['{}({})'.format(g, case_group) for g in cls._base_groups]
        groups = cls._base_groups + groups

        # Generate test case docstring
        test_steps["__doc__"] = "{}\n\n{}\n\nDuration {}".format(
            cls.__doc__.splitlines()[0],
            '\n'.join(scenario),
            getattr(cls, 'est_duration', '180m') or '180m')
        ret = test(
            type(class_name, (cls,), test_steps),
            groups=groups)
        return ret
