import pytest_yamlcase.actions


class FuelBaseAction(pytest_yamlcase.actions.BaseAction):
    """Base action representation."""

    pass
    # action_name = None

    # def __init__(self, parent, action):
    #     # self.action = action
    #     # name = "{} {}".format(self.action_name,
    #     #                       self.action['environment']['name'])
    #     super(FuelBaseAction, self).__init__(parent=parent, action=action)

    # def runtest(self):
    #     return self.run_and_wait(self.action)

    # def run_and_wait(self, action):
    #     raise NotImplementedError()

    # def reportinfo(self):
    #     return self.fspath, None, self.name


class CreateEnvironmentAction(FuelBaseAction):
    """Create Environment Action"""

    action_name = "create-environment"

    def run_action(self, action):
        print self.action_name
        assert 1


class AddNodesAction(FuelBaseAction):

    action_name = "add-nodes"

    def run_action(self, action):
        print self.action_name
        assert 1


class NetworkCheckAction(FuelBaseAction):

    action_name = "network-check"

    def run_action(self, action):
        print self.action_name
        assert 1


class DeployEnvironmentAction(FuelBaseAction):

    action_name = "deploy-environment"

    def run_action(self, action):
        print self.action_name
        assert 1


class StopProvisioningAction(FuelBaseAction):

    action_name = "stop-provisioning"

    def run_action(self, action):
        print self.action_name
        assert 1


class StopDeploymentAction(FuelBaseAction):

    action_name = "stop-deployment"

    def run_action(self, action):
        print self.action_name
        assert 1


class HealthCheckAction(FuelBaseAction):

    action_name = "health-check"

    def run_action(self, action):
        print self.action_name
        assert 1


class DeleteEnvironmentAction(FuelBaseAction):

    action_name = "delete-environment"

    def run_action(self, action):
        print self.action_name
        assert 1


def actions_discover():
    return {
        "create-environment": CreateEnvironmentAction,
        "add-nodes": AddNodesAction,
        "network-check": NetworkCheckAction,
        "deploy-environment": DeployEnvironmentAction,
        "stop-provisioning": StopProvisioningAction,
        "stop-deployment": StopDeploymentAction,
        "health-check": HealthCheckAction,
        "delete-environment": DeleteEnvironmentAction
    }
