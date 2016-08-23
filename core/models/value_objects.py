class FuelAccessParams(object):
    """Value object to represent and map yaml file values of fuel master node
    access to openrc file.
    Should not use any api."""

    def __init__(self,
                 tls_service_enabled=False,
                 tls_keystone_enabled=False):
        self._username = None
        self._password = None
        self._project = None
        self._service_address = None
        self._service_port = None
        self._keystone_address = None
        self._keystone_port = None
        self._tls_service_enabled = tls_service_enabled
        self._tls_keystone_enabled = tls_keystone_enabled

    @property
    def username(self):
        # type: () -> str
        return self._username

    @username.setter
    def username(self, value):
        # type: (str) -> str
        self._username = value

    @property
    def password(self):
        # type: () -> str
        return self._password

    @password.setter
    def password(self, value):
        # type: (str) -> str
        self._password = value

    @property
    def project(self):
        # type: () -> str
        return self._project

    @project.setter
    def project(self, value):
        # type: (str) -> str
        self._project = value

    @property
    def service_address(self):
        # type: () -> str
        return self._service_address

    @service_address.setter
    def service_address(self, value):
        # type: (str) -> str
        self._service_address = value

    @property
    def service_port(self):
        # type: () -> str
        return self._service_port

    @service_port.setter
    def service_port(self, value):
        # type: (str) -> str
        self._service_port = value

    @property
    def keystone_address(self):
        # type: () -> str
        address = self.service_address
        if self._keystone_address:
            address = self._keystone_address
        return address

    @keystone_address.setter
    def keystone_address(self, value):
        # type: (str) -> str
        self._keystone_address = value

    @property
    def keystone_port(self):
        # type: () -> str
        return self._keystone_port

    @keystone_port.setter
    def keystone_port(self, value):
        # type: (str) -> str
        self._keystone_port = value

    @property
    def os_auth_url(self):
        # type: () -> str
        protocol = 'http'
        if self._tls_keystone_enabled:
            protocol = 'https'
        return "{protocol}://{keystone_address}:{keystone_port}".format(
            protocol=protocol,
            keystone_address=self.keystone_address,
            keystone_port=self.keystone_port
        )

    @property
    def service_url(self):
        # type: () -> str
        protocol = 'http'
        if self._tls_service_enabled:
            protocol = 'https'
        return "{protocol}://{service_address}:{service_port}".format(
            protocol=protocol,
            service_address=self.service_address,
            service_port=self.service_port
        )

    @property
    def to_openrc_content(self):
        """Method to represent access credentials in openrc format.

        :return: string content for openrc file
        """
        # type: () -> str
        env_template = ('export OS_USERNAME="{username}"\n'
                        'export OS_PASSWORD="{password}"\n'
                        'export OS_TENANT_NAME="{project}"\n'
                        'export SERVICE_URL="{service_url}"\n'
                        'export OS_AUTH_URL="{os_auth_url}"\n')

        return env_template.format(
            username=self.username,
            password=self.username,
            project=self.project,
            service_url=self.service_url,
            os_auth_url=self.os_auth_url,
        )

    @staticmethod
    def from_yaml_params(yaml_content,
                         tls_service_enabled=False,
                         tls_keystone_enabled=False):
        # type: (dict, bool, bool) -> FuelAccessParams
        """The method to initialize value object from parsed yaml from
        master node.

        :param yaml_content: dict from yaml to parse
        :param tls_service_enabled: boolean
        :param tls_keystone_enabled: boolean
        :return: FuelAccessParams instance to work with
        """
        access_params = FuelAccessParams(
            tls_service_enabled=tls_service_enabled,
            tls_keystone_enabled=tls_keystone_enabled)
        access_params.username = yaml_content['OS_USERNAME']
        access_params.password = yaml_content['OS_PASSWORD']
        access_params.project = yaml_content['OS_TENANT_NAME']
        access_params.service_address = yaml_content['SERVER_ADDRESS']
        access_params.service_port = yaml_content['SERVER_PORT']
        access_params.keystone_port = yaml_content['KEYSTONE_PORT']

        return access_params
