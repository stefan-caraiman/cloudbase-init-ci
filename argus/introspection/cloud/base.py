# Copyright 2015 Cloudbase Solutions Srl
# All Rights Reserved.
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

import abc

import six

from argus.introspection import base


@six.add_metaclass(abc.ABCMeta)
class CloudInstanceIntrospection(base.BaseInstanceIntrospection):
    """Introspection class for testing Cloudbase-Init."""

    @abc.abstractmethod
    def get_disk_size(self):
        """Return the disk size from the instance."""

    @abc.abstractmethod
    def username_exists(self, username):
        """Check if the given username exists in the instance."""

    @abc.abstractmethod
    def get_instance_hostname(self):
        """Get the hostname of the instance."""

    @abc.abstractmethod
    def get_instance_ntp_peers(self):
        """Get the NTP peers from the instance."""

    @abc.abstractmethod
    def get_instance_keys_path(self):
        """Return the authorized_keys file path from the instance."""

    @abc.abstractmethod
    def get_instance_file_content(self, filepath):
        """Return the content of the given file from the instance."""

    @abc.abstractmethod
    def get_userdata_executed_plugins(self):
        """Get the count of user-data executed plugins."""

    @abc.abstractmethod
    def get_instance_mtu(self):
        """Get the MTU value from the instance."""

    @abc.abstractmethod
    def get_cloudbaseinit_traceback(self):
        """Return the traceback, if any, from the Cloudbase-Init logs."""

    @abc.abstractmethod
    def get_group_members(self, group):
        """Get the members of the local group given."""

    @abc.abstractmethod
    def list_location(self, location):
        """Return the list of files and folder from the given location."""

    @abc.abstractmethod
    def get_cloudconfig_executed_plugins(self):
        """Get a dictionary of files, created by the cloud-config plugin.

        The values are the actual file content.
        """

    @abc.abstractmethod
    def get_timezone(self):
        """Get the timezone of the instance."""

    @abc.abstractmethod
    def get_network_interfaces(self):
        """Get IP available instance network adapters."""

    @abc.abstractmethod
    def get_swap_status(self, expected_swap_status):
        """Get whether the swap memory is enabled or not.

        :returns: True if swap memory is enabled, False if not.
        :arg expected_swap_status: The expected swap status of the memory
        :rtype: bool
        """
