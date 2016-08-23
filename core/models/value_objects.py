class FuelAccessParams(object):
    """Value object to represent and map yaml file values of fuel master node
    access to openrc file.
    Should not use any api."""

    def __init__(self,
                 tls_service_enabled=False,
                 tls_keystone_enabled=False):
        # pylint: disable=too-many-instance-attributes
        self.__username = None  # type: str
        self.__password = None  # type: str
        self.__project = None  # type: str
        self.__service_address = None  # type: str
        self.__service_port = None  # type: str
        self.__keystone_address = None  # type: str
        self.__keystone_port = None  # type: str
        self.__tls_service_enabled = tls_service_enabled  # type: bool
        self.__tls_keystone_enabled = tls_keystone_enabled  # type: bool
        # pylint: enable=too-many-instance-attributes

    @property
    def username(self):
        return self.__username

    @username.setter
    def username(self, value):
        """Set up username

        :type value: str
        """
        self.__username = value

    @property
    def password(self):
        return self.__password

    @password.setter
    def password(self, value):
        """Set up password

        :type value: str
        """
        self.__password = value

    @property
    def project(self):
        return self.__project

    @project.setter
    def project(self, value):
        """Set up project

        :type value: str
        """
        self.__project = value

    @property
    def service_address(self):
        return self.__service_address

    @service_address.setter
    def service_address(self, value):
        """Set up service address

        :type value: str
        """
        self.__service_address = value

    @property
    def service_port(self):
        return self.__service_port

    @service_port.setter
    def service_port(self, value):
        """Set up service port

        :type value: str
        """
        self.__service_port = value

    @property
    def keystone_address(self):
        address = self.service_address
        if self.__keystone_address:
            address = self.__keystone_address
        return address

    @keystone_address.setter
    def keystone_address(self, value):
        """Set up keystone address

        :type value: str
        """
        self.__keystone_address = value

    @property
    def keystone_port(self):
        return self.__keystone_port

    @keystone_port.setter
    def keystone_port(self, value):
        """Set up keystone port

        :type value: str
        """
        self.__keystone_port = value

    @property
    def os_auth_url(self):
        """Get url of authentication endpoint

        :rtype: str
        :return: The url of os auth endpoint
        """
        protocol = 'http'
        if self.__tls_keystone_enabled:
            protocol = 'https'
        return "{protocol}://{keystone_address}:{keystone_port}".format(
            protocol=protocol,
            keystone_address=self.keystone_address,
            keystone_port=self.keystone_port
        )

    @property
    def service_url(self):
        """Get url of nailgun service endpoint

        :rtype: str
        :return: The url of nailgun endpoint
        """
        protocol = 'http'
        if self.__tls_service_enabled:
            protocol = 'https'
        return "{protocol}://{service_address}:{service_port}".format(
            protocol=protocol,
            service_address=self.service_address,
            service_port=self.service_port
        )

    def to_openrc_content(self):
        """Method to represent access credentials in openrc format.

        :rtype: str
        :return: string content for openrc file
        """
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

    @classmethod
    def from_yaml_params(cls,
                         yaml_content,
                         tls_service_enabled=False,
                         tls_keystone_enabled=False):
        """The method to initialize value object from parsed yaml from
        master node.

        :type yaml_content: dict[str]
        :type tls_service_enabled: boolean
        :type tls_keystone_enabled: boolean
        :rtype: FuelAccessParams
        :return: instance, which can be used
        """
        access_params = cls(
            tls_service_enabled=tls_service_enabled,
            tls_keystone_enabled=tls_keystone_enabled)
        access_params.username = yaml_content['OS_USERNAME']
        access_params.password = yaml_content['OS_PASSWORD']
        access_params.project = yaml_content['OS_TENANT_NAME']
        access_params.service_address = yaml_content['SERVER_ADDRESS']
        access_params.service_port = yaml_content['SERVER_PORT']
        access_params.keystone_port = yaml_content['KEYSTONE_PORT']

        return access_params
