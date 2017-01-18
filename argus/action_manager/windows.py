# Copyright 2016 Cloudbase Solutions Srl
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

import ntpath
import os
import socket
import time

import requests

from six.moves import urllib_parse as urlparse
from winrm import exceptions as winrm_exceptions

from argus.action_manager import base
from argus import config as argus_config
from argus import exceptions
from argus.introspection.cloud import windows as introspection
from argus import log as argus_log
from argus import util

LOG = argus_log.LOG
CONFIG = argus_config.CONFIG


def wait_boot_completion(client, username):
    wait_cmd = ("echo '{}'".format(username))
    client.run_command_until_condition(
        wait_cmd,
        lambda stdout: stdout.strip() == username,
        retry_count=CONFIG.argus.retry_count, delay=CONFIG.argus.retry_delay,
        command_type=util.POWERSHELL)


class WindowsActionManager(base.BaseActionManager):
    PATH_ANY = "Any"
    PATH_LEAF = "Leaf"
    PATH_CONTAINER = "Container"

    _DIRECTORY = "Directory"
    _FILE = "File"

    WINDOWS_MANAGEMENT_CMDLET = "Get-WmiObject"
    _INSTALL_SCRIPT = r"C:\installCBinit.ps1"
    _ARGUS_AGENT_SCRIPT = r"C:\argusagent.py"

    def __init__(self, client, os_type=util.WINDOWS):
        super(WindowsActionManager, self).__init__(client, os_type)

    def get_agent_command(self, agent_action,
                          agent_path=None, **kwargs):
        """Command builder for the argus utilitary agent.

        Returns a command string formed by the given action and its
        required arguments.
        """
        agent_path = agent_path or self._ARGUS_AGENT_SCRIPT
        python_dir = introspection.get_python_dir(self._execute)
        cmd = (r'& "{pydir}\python.exe" {agent_path} --{agent_action} '
               ' "{source}" "{location}"'.format(
                   pydir=python_dir, agent_path=agent_path,
                   agent_action=agent_action,
                   source=kwargs.get('source', ''),
                   location=kwargs.get('location', '')))
        return cmd

    def archive_file(self, file_path, destination_path):
        """Archives a given file_path to the destination_path."""
        LOG.info("Archiving %s to %s.", file_path, destination_path)
        archive_cmd = self.get_agent_command(agent_action="archive",
                                             source=file_path,
                                             location=destination_path)
        try:
            self._client.run_remote_cmd(cmd=archive_cmd,
                                        command_type=util.POWERSHELL)
        except exceptions.ArgusError as exc:
            LOG.debug("Could not archive %s: %s", file_path, exc)
            return file_path

    def encode_file_to_base64_str(self, file_path):
        """Returns a base64 encoded string resulted from the given file."""
        LOG.debug("Encoding %s to base64.", file_path)
        encode_cmd = self.get_agent_command(agent_action="encode",
                                            source=file_path)
        try:
            return self._client.run_remote_cmd(cmd=encode_cmd,
                                               command_type=util.POWERSHELL)
        except exceptions.ArgusError as exc:
            LOG.debug("Could not encode %s: %s", file_path, exc)

    def download(self, uri, location):
        """Download the resource located at a specific URI in the location.

        :param uri:
            Remote URL where the data is found.

        :param location:
            Path from the instance in which we should download the
            remote resource.
        """
        LOG.debug("Downloading from %s to %s ", uri, location)
        cmd = ('(New-Object System.Net.WebClient).DownloadFile('
               '"{uri}","{location}")'.format(uri=uri, location=location))
        self._client.run_command_with_retry(cmd,
                                            count=CONFIG.argus.retry_count,
                                            delay=CONFIG.argus.retry_delay,
                                            command_type=util.POWERSHELL)

    def download_resource(self, resource_location, location):
        """Download the resource in the specified location

        :param resource_script:
            Is relative to the /argus/resources/ directory.
        :param location:
            The location on the instance.
        """
        base_resource = CONFIG.argus.resources
        if not base_resource.endswith("/"):
            base_resource = urlparse.urljoin(CONFIG.argus.resources,
                                             "resources/")
        uri = urlparse.urljoin(base_resource, resource_location)
        self.download(uri, location)

    def _execute_resource_script(self, resource_location, parameters,
                                 script_type,
                                 upper_timeout=CONFIG.argus.upper_timeout):
        """Run a resource script with with the specific parameters."""
        LOG.debug("Executing resource script %s with this parameters %s",
                  resource_location, parameters)

        if script_type == util.BAT_SCRIPT:
            script_type = util.CMD

        instance_location = r"C:\{}".format(resource_location.split('/')[-1])
        self.download_resource(resource_location, instance_location)
        cmd = '"{}" {}'.format(instance_location, parameters)
        self._client.run_command_with_retry(
            cmd, count=CONFIG.argus.retry_count,
            delay=CONFIG.argus.retry_delay,
            command_type=script_type, upper_timeout=upper_timeout)

    def execute_powershell_resource_script(
            self, resource_location, parameters="",
            upper_timeout=CONFIG.argus.upper_timeout):
        """Execute a powershell resource script."""
        self._execute_resource_script(
            resource_location=resource_location, parameters=parameters,
            script_type=util.POWERSHELL_SCRIPT_BYPASS,
            upper_timeout=upper_timeout)

    def get_installation_script(self):
        """Get installation script for Cloudbase-Init."""
        LOG.info("Retrieve an installation script for Cloudbase-Init.")
        self.download_resource("windows/installCBinit.ps1",
                               self._INSTALL_SCRIPT)

    def _execute(self, cmd, count=CONFIG.argus.retry_count,
                 delay=CONFIG.argus.retry_delay, command_type=util.CMD,
                 upper_timeout=CONFIG.argus.upper_timeout):
        """Execute until succeeds and return only the standard output."""
        stdout, _, _ = self._client.run_command_with_retry(
            cmd, count=count, delay=delay, command_type=command_type,
            upper_timeout=upper_timeout)
        return stdout

    def check_cbinit_installation(self):
        """Check if Cloudbase-Init was installed successfully."""
        LOG.info("Checking Cloudbase-Init installation.")

        try:
            python_dir = introspection.get_python_dir(self._execute)
        except exceptions.ArgusError as exc:
            LOG.warning("Could not check Cloudbase-Init installation: %s", exc)
            return False

        check_cmd = r'& "{}\python.exe" -c "import cloudbaseinit"'.format(
            python_dir)
        try:
            self._client.run_remote_cmd(
                cmd=check_cmd, command_type=util.POWERSHELL)
        except exceptions.ArgusError as exc:
            LOG.debug("Cloudbase-Init installation failed: %s", exc)
            return False

        LOG.info("Cloudbase-Init was successfully installed!")
        return True

    def cbinit_cleanup(self):
        """Cleans up Cloudbase-Init if the installation failed."""
        LOG.debug("Cleaning up Cloudbase-Init from the instance.")
        try:
            cbinit_dir = introspection.get_cbinit_dir(self._execute)
            self.rmdir(ntpath.dirname(cbinit_dir))
        except exceptions.ArgusError as exc:
            LOG.warning("Could not cleanup Cloudbase-Init: %s", exc)
            return False
        else:
            return True

    @staticmethod
    def _get_installer_name():
        """Get Cloudbase-Init installer name."""
        return "CloudbaseInitSetup_{build}_{arch}.msi".format(
            build=CONFIG.argus.build, arch=CONFIG.argus.arch)

    def install_cbinit(self):
        """Install Cloudbase-Init on the underlying instance."""
        LOG.info("Trying to install Cloudbase-Init.")
        installer = self._get_installer_name()

        for _ in range(CONFIG.argus.retry_count):
            for install_method in (self._run_installation_script,
                                   self._deploy_using_scheduled_task):
                try:
                    install_method(installer)
                except exceptions.ArgusError as exc:
                    LOG.debug("Could not install Cloudbase-Init: %s", exc)
                else:
                    if self.check_cbinit_installation():
                        return True
                self.cbinit_cleanup()

        return False

    def _run_installation_script(self, installer):
        """Run the installation script for Cloudbase-Init."""
        LOG.info("Running the installation script for Cloudbase-Init.")

        cmd = r'"{}" -installer {} -MsiWebLocation {}'.format(
            self._INSTALL_SCRIPT, installer, CONFIG.argus.msi_web_location)
        self._client.run_command_with_retry(
            cmd, command_type=util.POWERSHELL_SCRIPT_BYPASS)

    def _deploy_using_scheduled_task(self, installer):
        """Deploy Cloudbase-Init using a scheduled task."""
        LOG.info("Deploying Cloudbase-Init using a scheduled task.")
        resource_script = 'windows/schedule_installer.ps1'
        self.execute_powershell_resource_script(resource_script, installer)

    def sysprep(self):
        resource_location = "windows/sysprep.ps1"

        cmd = r"C:\{}".format(resource_location.split('/')[-1])
        self.download_resource(resource_location, cmd)
        LOG.debug("Running %s ", cmd)
        try:
            self._client.run_remote_cmd(
                cmd, command_type=util.POWERSHELL_SCRIPT_BYPASS,
                upper_timeout=CONFIG.argus.io_upper_timeout)
        except (socket.error, winrm_exceptions.WinRMTransportError,
                winrm_exceptions.InvalidCredentialsError,
                requests.ConnectionError, requests.Timeout):
            # After executing sysprep.ps1 the instance will reboot and
            # it is normal to have connectivity issues during that time.
            # Knowing these we have to except this kind of errors.
            # This fixes errors that stops scenarios from getting
            # created on different windows images.
            LOG.debug("Currently rebooting...")
        LOG.info("Wait for the machine to finish rebooting ...")
        self.wait_boot_completion()

    def git_clone(self, repo_url, location, count=CONFIG.argus.retry_count,
                  delay=CONFIG.argus.retry_delay):
        """Clone from a remote repository to a specified location.

        :param repo_url: The remote repository URL.
        :param location: The target location for where to clone the repository.
        :param count:
            The number of tries that should be attempted in case it fails.
        :param delay: The time delay before retrying.
        :returns: True if the clone was successful, False if not.
        :raises: ArgusCLIError if the path is not valid.
        :rtype: bool
        """
        if self.exists(location):
            raise exceptions.ArgusCLIError("Destination path '{}' already "
                                           "exists.".format(location))
        LOG.info("Cloning from %s to %s", repo_url, location)
        cmd = "git clone '{repo}' '{location}'".format(repo=repo_url,
                                                       location=location)

        while count > 0:
            try:
                self._client.run_command(cmd)
            except exceptions.ArgusError as exc:
                LOG.debug("Cloning failed with %r.", exc)
                if self.exists(location):
                    rem = self.rmdir if self.is_dir(location) else self.remove
                    rem(location)
                count -= 1
                if count:
                    LOG.debug('Retrying...')
                    time.sleep(delay)
            else:
                return True

        LOG.debug('Could not clone %s', repo_url)
        return False

    def wait_cbinit_service(self):
        """Wait if the Cloudbase-Init Service to stop."""
        wait_cmd = ('(Get-Service | where {$_.Name '
                    '-match "cloudbase-init"}).Status')
        self._client.run_command_until_condition(
            wait_cmd,
            lambda out: out.strip() == 'Stopped',
            retry_count=CONFIG.argus.retry_count,
            delay=CONFIG.argus.retry_delay,
            command_type=util.POWERSHELL)

    def check_cbinit_service(self, searched_paths=None):
        """Check if the Cloudbase-Init service started.

        :param searched_paths:
            Paths to files that should exist if the heartbeat patch is
            applied.
        """
        test_cmd = 'Test-Path "{}"'
        check_cmds = [test_cmd.format(path) for path in searched_paths or []]
        for check_cmd in check_cmds:
            self._client.run_command_until_condition(
                check_cmd,
                lambda out: out.strip() == 'True',
                retry_count=CONFIG.argus.retry_count,
                delay=CONFIG.argus.retry_delay,
                command_type=util.POWERSHELL)

    def wait_boot_completion(self):
        """Wait for a reasonable amount of time the instance to boot."""
        LOG.info("Waiting for boot completion...")
        username = CONFIG.openstack.image_username
        wait_boot_completion(self._client, username)

    def specific_prepare(self):
        """Prepare some OS specific resources."""
        self.download_resource("windows/argusagent.py",
                               self._ARGUS_AGENT_SCRIPT)
        LOG.debug("Prepare something specific for OS Type %s", self._os_type)

    def copy_file(self, path, new_file):
        """Copy a file to the destination"""
        if not self.exists(path):
            raise exceptions.ArgusCLIError("Invalid Path '{}'.".format(path))

        LOG.debug("Copy file from %s to %s", path, new_file)
        cmd = ("Copy-Item -Force -Path '{path}' "
               "-Destination '{newname}'".format(path=path, newname=new_file))
        self._client.run_command_with_retry(cmd, command_type=util.POWERSHELL)

    def remove(self, path):
        """Remove a file."""
        if not self.exists(path) or not self.is_file(path):
            raise exceptions.ArgusCLIError("Invalid Path '{}'.".format(path))

        LOG.debug("Remove file %s", path)
        cmd = "Remove-Item -Force -Path '{path}'".format(path=path)
        self._client.run_command_with_retry(cmd, command_type=util.POWERSHELL)

    def rmdir(self, path):
        """Remove a directory."""
        if not self.exists(path) or not self.is_dir(path):
            raise exceptions.ArgusCLIError("Invalid Path '{}'.".format(path))

        LOG.debug("Remove directory  %s", path)
        cmd = "Remove-Item -Force -Recurse -Path '{path}'".format(path=path)
        self._client.run_command_with_retry(cmd, command_type=util.POWERSHELL)

    def _exists(self, path, path_type):
        """Check if the path exists and it has the specified type.

        :param path:
            Path to check if it exists.
        :param path_type:
            This can be 'Leaf' or 'Container'
        """
        cmd = 'Test-Path -PathType {} -Path "{}"'.format(path_type, path)
        stdout, _, _ = self._client.run_command_with_retry(
            cmd=cmd, command_type=util.POWERSHELL)

        return stdout.strip() == "True"

    def exists(self, path):
        """Check if the path exists.

        :param path:
            Path to check if it exists.
        """
        return self._exists(path, self.PATH_ANY)

    def is_file(self, path):
        """Check if the file exists.

        :param path:
            Path to check if it exists and if it's a file.
        """
        return self._exists(path, self.PATH_LEAF)

    def is_dir(self, path):
        """Check if the directory exists.

        :param path:
            Path to check if it exists and it's a directory.
        """
        return self._exists(path, self.PATH_CONTAINER)

    def _new_item(self, path, item_type):
        """Create a directory or a file.

        :param path:
            Instance path of the new item.
        :param item_type:
            It can be `Directory` or `File`
        """
        cmd = "New-Item -Path '{}' -Type {} -Force".format(path, item_type)
        self._client.run_command_with_retry(cmd=cmd,
                                            command_type=util.POWERSHELL)

    def mkdir(self, path):
        """Create a directory in the instance if the path is valid.

        :param path:
            Remote path where the new directory should be created.
        """
        if self.exists(path):
            raise exceptions.ArgusCLIError(
                "Cannot create directory {} . It already exists.".format(
                    path))
        else:
            self._new_item(path, self._DIRECTORY)

    def mkfile(self, path):
        """Create a file in the instance if the path is valid.

        :param path:
            Remote path where the new file should be created.
        """
        if self.is_file(path):
            LOG.warning("File '%s' already exists. LastWriteTime and"
                        " LastAccessTime will be updated.", path)
            self._client.run_command_with_retry(
                "echo $null >> '{}'".format(path),
                command_type=util.POWERSHELL)
        elif self.is_dir(path):
            raise exceptions.ArgusCLIError(
                "Path '{}' leads to a"
                " directory.".format(path))
        self._new_item(path, self._FILE)

    def touch(self, path):
        """Update the access and modification time.

        If the file doesn't exist, an empty file will be created
        as side effect.
        """
        if self.is_dir(path):
            cmd = ("$datetime = get-date;"
                   "$dir = Get-Item '{}';"
                   "$dir.LastWriteTime = $datetime;"
                   "$dir.LastAccessTime = $datetime;").format(path)
            self._client.run_command_with_retry(
                cmd, command_type=util.POWERSHELL)
        else:
            self.mkfile(path)

    # pylint: disable=unused-argument
    def prepare_config(self, cbinit_conf, cbinit_unattend_conf):
        """Prepare Cloudbase-Init config for every OS.

        :param cbinit_config:
            Cloudbase-Init config file.
        :param cbinit_unattend_conf:
            Cloudbase-Init Unattend config file.
        """
        LOG.info("Config Cloudbase-Init for %s", self._os_type)


class Windows8ActionManager(WindowsActionManager):
    def __init__(self, client, os_type=util.WINDOWS8):
        super(Windows8ActionManager, self).__init__(client, os_type)


class WindowsServer2008ActionManager(WindowsActionManager):
    def __init__(self, client, os_type=util.WINDOWS_SERVER_2008):
        super(WindowsServer2008ActionManager, self).__init__(client, os_type)


class Windows7ActionManager(WindowsServer2008ActionManager):
    def __init__(self, client, os_type=util.WINDOWS7):
        super(Windows7ActionManager, self).__init__(client, os_type)


class WindowsSever2012ActionManager(Windows8ActionManager):
    def __init__(self, client, os_type=util.WINDOWS_SERVER_2012):
        super(WindowsSever2012ActionManager, self).__init__(client,
                                                            os_type)


class WindowsSever2012R2ActionManager(Windows8ActionManager):
    def __init__(self, client, os_type=util.WINDOWS_SERVER_2012_R2):
        super(WindowsSever2012R2ActionManager, self).__init__(client,
                                                              os_type)


class Windows10ActionManager(WindowsActionManager):

    WINDOWS_MANAGEMENT_CMDLET = "Get-CimInstance"

    def __init__(self, client, os_type=util.WINDOWS10):
        super(Windows10ActionManager, self).__init__(client, os_type)


class WindowsSever2016ActionManager(Windows10ActionManager):
    def __init__(self, client, os_type=util.WINDOWS_SERVER_2016):
        super(WindowsSever2016ActionManager, self).__init__(client,
                                                            os_type)


class WindowsNanoActionManager(WindowsSever2016ActionManager):
    _DOWNLOAD_SCRIPT = "FastWebRequest.ps1"
    _COMMON = "common.psm1"
    _RESOURCE_DIRECTORY = r"C:\nano_server"
    _CBINIT_URL = "https://www.cloudbase.it/downloads/"
    _BASE_DIR = r"C:\Program Files\Cloudbase Solutions\Cloudbase-Init"
    _INSTALLATION_LOG_FILE = r"C:\installation.log"

    WINDOWS_MANAGEMENT_CMDLET = "Get-CimInstance"

    def __init__(self, client, os_type=util.WINDOWS_NANO):
        super(WindowsNanoActionManager, self).__init__(client, os_type)

    @staticmethod
    def _get_resource_path(resource):
        """Get resource path from argus resources."""
        resource_path = os.path.join(
            os.path.abspath(os.path.dirname(__file__)),
            "..", "resources", "windows", "nano_server",
            resource)
        return os.path.normpath(resource_path)

    def specific_prepare(self):
        if not self.is_dir(self._RESOURCE_DIRECTORY):
            self.mkdir(self._RESOURCE_DIRECTORY)

        resource_path = self._get_resource_path(self._COMMON)
        self._client.copy_file(
            resource_path, ntpath.join(self._RESOURCE_DIRECTORY,
                                       self._COMMON))

        LOG.info("Copy Download script for Windows NanoServer.")
        resource_path = self._get_resource_path(self._DOWNLOAD_SCRIPT)
        self._client.copy_file(
            resource_path, ntpath.join(self._RESOURCE_DIRECTORY,
                                       self._DOWNLOAD_SCRIPT))

        super(WindowsNanoActionManager, self).specific_prepare()

    def download(self, uri, location):
        resource_path = ntpath.join(self._RESOURCE_DIRECTORY,
                                    self._DOWNLOAD_SCRIPT)
        cmd = r"{script_path} -Uri {uri} -OutFile '{outfile}'".format(
            script_path=resource_path, uri=uri, outfile=location)
        self._client.run_command_with_retry(
            cmd, command_type=util.POWERSHELL)

    def prepare_config(self, cbinit_conf, cbinit_unattend_conf):
        """Prepare Cloudbase-Init config for every OS.

        :param cbinit_config:
            Cloudbase-Init config file.
        :param cbinit_unattend_conf:
            Cloudbase-Init Unattend config file.
        """
        super(WindowsNanoActionManager, self).prepare_config(
            cbinit_conf, cbinit_unattend_conf)
        for conf in (cbinit_conf, cbinit_unattend_conf):
            conf.conf.remove_option("DEFAULT", "logging_serial_port_settings")
            conf.set_conf_value("stop_service_on_exit", False)

    def get_installation_script(self):
        """Get instalation script for CloudbaseInit."""
        self.download_resource("windows/nano_server/installCBinit.ps1",
                               self._INSTALL_SCRIPT)

    def _unzip(self, zip_file, out_file, force=False):
        """Unzip the file.

        :param zip_file:
            Path to zip file.
        :param out_file:
            Path to output file from unzipping process.
        :param force:
            If we should override the output file or not.
        """
        exists = self.exists(out_file)
        if exists and not force:
            raise exceptions.ArgusCLIError("Output file path already exists.")
        elif exists:
            (self.rmdir if self.is_dir(out_file) else self.remove)(out_file)

        cmd = ("[System.IO.Compression.ZipFile]"
               "::ExtractToDirectory('{}', '{}')").format(zip_file, out_file)

        self._client.run_command_with_retry(
            cmd, command_type=util.POWERSHELL)

    @staticmethod
    def _get_installer_name():
        """Get Cloudbase-Init installer name."""
        if CONFIG.argus.build == "Beta":
            # NOTE(mmicu): This is a temporary fix.
            # There is no Beta url for the Cloudbase-Init zip.
            return "CloudbaseInitSetup_{arch}.zip".format(
                arch=CONFIG.argus.arch)
        else:
            return "CloudbaseInitSetup_{build}_{arch}.zip".format(
                build=CONFIG.argus.build, arch=CONFIG.argus.arch)

    def _get_useful_paths(self, installer):
        """Get useful paths for installing Cloudbase-Init.

        :param installer: Name of the Cloudbase-Init installer.
        :type installer: str

        :return: A tuple containing the `url` for the Cloudbase-Init
                 installer and the `zip_path` where we should download
                 the installer.

        :rtype: tuple
        """
        installer = self._get_installer_name()
        url = urlparse.urljoin(self._CBINIT_URL, installer)
        zip_path = ntpath.join("C:\\", installer)

        return url, zip_path

    def cbinit_cleanup(self):
        """Cleans up Cloudbase-Init if the installation failed."""
        LOG.debug("Cleaning up Cloudbase-Init from the instance.")
        base_cleanup = super(WindowsNanoActionManager, self).cbinit_cleanup()

        to_be_removed = [self._INSTALL_SCRIPT]
        _, zip_path = self._get_useful_paths(self._get_installer_name())
        to_be_removed.extend(zip_path)

        for path in to_be_removed:
            (self.rmdir if self.is_dir(path) else self.remove)(path)

        return base_cleanup

    def _run_installation_script(self, installer):
        """Run the installation script for Cloudbase-Init."""
        LOG.info("Running the installation script for Cloudbase-Init.")
        LOG.info("Run the downloaded installation script "
                 "using the installer %r.", installer)

        url, zip_path = self._get_useful_paths(installer)
        self.download(url, zip_path)

        LOG.info("Unzipping at %s", self._BASE_DIR)
        self._unzip(zip_path, self._BASE_DIR)

        cmd = "{install_script} *>> {log_file}".format(
            install_script=self._INSTALL_SCRIPT,
            log_file=self._INSTALLATION_LOG_FILE)

        self._client.run_command_with_retry(
            cmd, command_type=util.POWERSHELL)

    def _deploy_using_scheduled_task(self, installer):
        """Deploy Cloudbase-Init using a scheduled task."""
        LOG.info("Deploying Cloudbase-Init using a scheduled task is not"
                 " supported for Windows Nano.")

    def sysprep(self):
        """Run the Cloudbase-Init."""
        # TODO(mmicu): Restructure this method to have a more explicit name
        # that works for Windows Nano too
        exe_path = ntpath.join(self._BASE_DIR, "Python", "Scripts",
                               "cloudbase-init.exe")
        config_unattend_path = ntpath.join(
            self._BASE_DIR, "conf", "cloudbase-init-unattend.conf")
        cmd = (r"& '{exe_path}' --config-file '{config_unattend}'").format(
            exe_path=exe_path, config_unattend=config_unattend_path)

        try:
            # Unattend phase
            self._client.run_remote_cmd(cmd, util.POWERSHELL)
        except exceptions.ArgusError as ex:
            LOG.debug("Exception in Unattend phase %s", ex)

        try:
            self._client.run_remote_cmd("Restart-Computer", util.POWERSHELL)
        except (IOError, winrm_exceptions.WinRMTransportError,
                winrm_exceptions.InvalidCredentialsError):
            # NOTE(mmicu): When we reboot the machine it is possible to
            # have connectivity issues.
            # This fixes errors that stop scenarios from getting
            # created on different windows images.
            LOG.debug("Currently rebooting...")
        LOG.info("Wait for the machine to finish rebooting ...")
        self.wait_boot_completion()

    def _execute_resource_script(self, resource_location, parameters,
                                 script_type,
                                 upper_timeout=CONFIG.argus.upper_timeout):
        """Run a resource script with the specific parameters."""
        LOG.debug("Executing resource script %s with this parameters %s",
                  resource_location, parameters)

        # TODO(mmicu): refactor this or find an OS agnostic way
        if script_type == util.BAT_SCRIPT:
            super(WindowsNanoActionManager, self)._execute_resource_script(
                resource_location, parameters, script_type)
        else:
            instance_location = r"C:\{}".format(
                resource_location.split('/')[-1])
            self.download_resource(resource_location, instance_location)
            cmd = '& "{}" {}'.format(instance_location, parameters)
            self._client.run_command_with_retry(
                cmd, count=CONFIG.argus.retry_count,
                delay=CONFIG.argus.retry_delay,
                command_type=util.POWERSHELL, upper_timeout=upper_timeout)


WindowsActionManagers = {
    util.WINDOWS: WindowsNanoActionManager,
    util.WINDOWS7: Windows7ActionManager,
    util.WINDOWS8: Windows8ActionManager,
    util.WINDOWS10: Windows10ActionManager,
    util.WINDOWS_SERVER_2008: WindowsServer2008ActionManager,
    util.WINDOWS_SERVER_2008_R2: WindowsServer2008ActionManager,
    util.WINDOWS_SERVER_2012: WindowsSever2012ActionManager,
    util.WINDOWS_SERVER_2012_R2: WindowsSever2012R2ActionManager,
    util.WINDOWS_SERVER_2016: WindowsSever2016ActionManager,
    util.WINDOWS_NANO: WindowsNanoActionManager
}


def _is_nanoserver(client):
    """Returns True if the client is connected to a NanoServer machine.

       Using the powershell code from here: https://goo.gl/UD27SK
    """
    server_level_key = (r'HKLM:\Software\Microsoft\Windows NT\CurrentVersion'
                        r'\Server\ServerLevels')

    cmd = r'Test-Path "{}"'.format(server_level_key)
    path_exists, _, _ = client.run_command_with_retry(
        cmd, count=CONFIG.argus.retry_count, delay=CONFIG.argus.retry_delay,
        command_type=util.POWERSHELL)

    if path_exists == "False":
        return False

    cmd = r'(Get-ItemProperty "{}").NanoServer'.format(server_level_key)
    nanoserver_property, _, _ = client.run_command_with_retry(
        cmd, count=CONFIG.argus.retry_count, delay=CONFIG.argus.retry_delay,
        command_type=util.POWERSHELL)

    return len(nanoserver_property) > 0 and nanoserver_property[0] == "1"


def _get_product_type(client, major_version):
    """Return the minor version of the OS.

    :param client:
        A Windows Client.
    :param  major_version:
        Windows Major version according to
        https://msdn.microsoft.com/en-us/library/aa394239(v=vs.85).aspx
    """
    # NOTE(mmicu): For Windows 10, Windows Server 2016 and Windows Nano
    # we use Common Information Model (Cim) and for the others we use
    # Windows Management Instrumentation (Wmi)
    cmdlet = Windows8ActionManager.WINDOWS_MANAGEMENT_CMDLET
    if major_version == 10:
        cmdlet = Windows10ActionManager.WINDOWS_MANAGEMENT_CMDLET
    cmd = r"({} -Class Win32_OperatingSystem).producttype".format(cmdlet)

    product_type, _, _ = client.run_command_with_retry(
        cmd, count=CONFIG.argus.retry_count, delay=CONFIG.argus.retry_delay,
        command_type=util.POWERSHELL)
    return util.get_int_from_str(product_type.strip())


def get_windows_action_manager(client):
    """Get the OS specific Action Manager."""
    LOG.info("Waiting for boot completion in order to select an "
             "Action Manager ...")

    username = CONFIG.openstack.image_username
    wait_boot_completion(client, username)

    # get OS type
    major_version = introspection.get_os_version(client, 'Major')
    minor_version = introspection.get_os_version(client, 'Minor')
    product_type = _get_product_type(client, major_version)
    windows_type = util.WINDOWS_VERSION.get((major_version, minor_version,
                                             product_type), util.WINDOWS)
    is_nanoserver = _is_nanoserver(client)

    if isinstance(windows_type, dict):
        windows_type = windows_type[is_nanoserver]
    LOG.debug(("We got the OS type %s because we have the major Version : %d,"
               " the minor version %d, the product Type : %d, and"
               " IsNanoserver: %s"), windows_type, major_version,
              minor_version, product_type, is_nanoserver)

    action_manager = WindowsActionManagers[windows_type]
    return action_manager(client=client)
