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

from proboscis import test
from proboscis import after_class
from proboscis import before_class

from fuelweb_test.tests import base_test_case

from system_test.helpers import utils
from system_test.helpers.decorators import step_start_stop


class BaseActionsFactory(base_test_case.TestBasic):

    @classmethod
    def get_actions(cls):
        """Return all action methods"""
        return {m: getattr(cls, m) for m in
                dir(cls) if m.startswith('_action_')}

    @classmethod
    def get_actions_order(cls):
        """Get order of actions"""
        if cls.actions_order is None:
            raise LookupError
        return cls.actions_order

    @classmethod
    def caseclass_factory(cls, case_group):
        """Create new clonned cls class contains only action methods"""
        test_steps, scenario = {}, []
        actions_method = cls.get_actions()

        #  Generate human readeble class_name, if was method docstring not
        #  described, use generated name
        class_name = "Case_{}__Config_{}".format(cls.__name__, case_group)

        #  Make methods for new testcase class, folowing by order
        scenario.append("    Scenario:")
        for step, action in enumerate(cls.get_actions_order()):
            n_action = action.replace("_action_", "")
            #  Generate human readeble method name, if was method docstring not
            #  described, use generated name. Used when metod failed
            step_method_name = "{}.Step{:03d}_{}".format(class_name,
                                                         step,
                                                         n_action)
            method = utils.copy_func(actions_method[action], step_method_name)
            _step_name = getattr(actions_method[action],
                                 "__doc__").splitlines()[0]
            setattr(method, "_step_name", "Step {:03d}. {}".format(step,
                                                                   _step_name))

            #  Add step to scenario
            scenario.append("        {}. {}".format(step, _step_name))

            #  Add decorator to colonned method
            for deco in getattr(method, '_deferred_decorator_', []):
                method = deco(method)

            #  if not first step make dependency
            if step > 0:
                prev_step_name = "{}.Step{:03d}_{}".format(
                    class_name,
                    step - 1,
                    cls.get_actions_order()[step - 1].replace("_action_", ""))
                depends = [test_steps[prev_step_name]]
            else:
                depends = None

            #  Add start-stop step decorator for measuring time and print
            #  start and finish info
            method = step_start_stop(method)

            test_steps[step_method_name] = test(
                method,
                depends_on=depends)

        #  Create before and after case methods
        start_method = utils.copy_func(
            getattr(cls, "_start_case"),
            "{}.StartCase".format(class_name))
        test_steps["{}.StartCase".format(class_name)] = before_class(
            start_method)
        finish_method = utils.copy_func(
            getattr(cls, "_finish_case"),
            "{}.FinishCase".format(class_name))
        test_steps["{}.FinishCase".format(class_name)] = after_class(
            finish_method)

        # Generate test case groups
        groups = ['{}.{}'.format(g, case_group) for g in cls.base_group]
        groups = cls.base_group + groups

        # Generate test case docstring
        test_steps["__doc__"] = "{}\n{}".format(cls.__doc__.splitlines()[0],
                                                '\n'.join(scenario))
        ret = test(
            type(class_name, (cls,), test_steps),
            groups=groups)
        return ret
