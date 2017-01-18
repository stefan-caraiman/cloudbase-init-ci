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

# TODO(dtoncu): Refactoring this module in order to avoid pylint disables.

# pylint: disable=no-value-for-parameter, too-many-lines, protected-access
# pylint: disable=too-many-public-methods

import ntpath
import os
import unittest

try:
    import unittest.mock as mock
except ImportError:
    import mock

import requests

from six.moves import urllib_parse as urlparse

from argus.action_manager import windows as action_manager
from argus import config as argus_config
from argus import exceptions
from argus.introspection.cloud import windows as introspection
from argus.unit_tests import test_utils
from argus import util


CONFIG = argus_config.CONFIG


class WindowsActionManagerTest(unittest.TestCase):
    """Tests for windows action manager class."""

    def setUp(self):
        self._client = mock.MagicMock()
        self._os_type = mock.sentinel.os_type

        self._action_manager = action_manager.WindowsActionManager(
            client=self._client, os_type=self._os_type)

    def test_download_successful(self):
        self._action_manager.download(test_utils.URI, test_utils.LOCATION)

        cmd = ('(New-Object System.Net.WebClient).DownloadFile('
               '"{uri}","{location}")'.format(uri=test_utils.URI,
                                              location=test_utils.LOCATION))

        self._client.run_command_with_retry.assert_called_with(
            cmd, count=CONFIG.argus.retry_count,
            delay=CONFIG.argus.retry_delay,
            command_type=util.POWERSHELL)

    def test_download_exception(self):
        (self._client.run_command_with_retry
         .side_effect) = exceptions.ArgusTimeoutError

        with self.assertRaises(exceptions.ArgusTimeoutError):
            self._action_manager.download(test_utils.URI, test_utils.LOCATION)

    @test_utils.ConfPatcher('resources', test_utils.BASE_RESOURCE, 'argus')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.download')
    def _test_download_resource(self, mock_download, expected_uri, exc=None):
        if exc:
            mock_download.side_effect = exc
            with self.assertRaises(exceptions.ArgusTimeoutError):
                self._action_manager.download_resource(
                    test_utils.RESOURCE_LOCATION, test_utils.LOCATION)
            return

        self._action_manager.download_resource(
            test_utils.RESOURCE_LOCATION, test_utils.LOCATION)
        mock_download.assert_called_once_with(
            expected_uri, test_utils.LOCATION)

    def test_download_resource_exception(self):
        self._test_download_resource(
            expected_uri=None,
            exc=exceptions.ArgusTimeoutError)

    def test_download_resource_base_resource_endswith_slash(self):
        self._test_download_resource(
            expected_uri=urlparse.urljoin(
                test_utils.BASE_RESOURCE, test_utils.RESOURCE_LOCATION))

    @test_utils.ConfPatcher('resources', test_utils.BASE_RESOURCE[:-1],
                            'argus')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.download')
    def test_download_resource_base_resource_not_endswith_slash(
            self, mock_download):
        expected_uri = urlparse.urljoin(
            test_utils.BASE_RESOURCE, test_utils.RESOURCE_LOCATION)

        self._action_manager.download_resource(
            test_utils.RESOURCE_LOCATION, test_utils.LOCATION)
        mock_download.assert_called_once_with(
            expected_uri, test_utils.LOCATION)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.download_resource')
    def _test_execute_resource_script(self, mock_download_resource,
                                      script_type, run_command_exc=None,
                                      download_exc=None):
        if download_exc:
            mock_download_resource.side_effect = download_exc
            with self.assertRaises(download_exc):
                self._action_manager._execute_resource_script(
                    test_utils.PATH, test_utils.PATH_TYPE, script_type)
            return

        self._client.run_command_with_retry = mock.Mock()

        if run_command_exc:
            self._client.run_command_with_retry.side_effect = run_command_exc
            with self.assertRaises(run_command_exc):
                self._action_manager._execute_resource_script(
                    test_utils.PATH, test_utils.PATH_TYPE, script_type)
            return

        instance_location = r"C:\{}".format(
            test_utils.RESOURCE_LOCATION.split('/')[-1])
        cmd = '"{}" {}'.format(instance_location, test_utils.PARAMETERS)

        self._action_manager._execute_resource_script(
            test_utils.RESOURCE_LOCATION, test_utils.PARAMETERS, script_type)

        if script_type == util.BAT_SCRIPT:
            script_type = util.CMD

        mock_download_resource.assert_called_once_with(
            test_utils.RESOURCE_LOCATION, instance_location)
        self._client.run_command_with_retry.assert_called_once_with(
            cmd, count=CONFIG.argus.retry_count,
            delay=CONFIG.argus.retry_delay, command_type=script_type,
            upper_timeout=CONFIG.argus.upper_timeout)

    def test_execute_resource_script_bat_script(self):
        self._test_execute_resource_script(script_type=util.BAT_SCRIPT)

    def test_execute_resource_script_powershell_script(self):
        self._test_execute_resource_script(
            script_type=util.POWERSHELL_SCRIPT_BYPASS)

    def test_execute_resource_script_run_command_exception(self):
        self._test_execute_resource_script(
            script_type=util.BAT_SCRIPT,
            run_command_exc=exceptions.ArgusTimeoutError)

    def test_execute_resource_script_download_resource_exception(self):
        self._test_execute_resource_script(
            script_type=util.POWERSHELL_SCRIPT_BYPASS,
            download_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._execute_resource_script')
    def _test_execute_res_script(self, mock_execute_script, test_method,
                                 script_type, exc=None):

        if exc:
            mock_execute_script.side_effect = exc
            with self.assertRaises(exc):
                test_method(
                    test_utils.RESOURCE_LOCATION, test_utils.PARAMETERS)
            return

        test_method(test_utils.RESOURCE_LOCATION, test_utils.PARAMETERS)
        mock_execute_script.assert_called_once_with(
            resource_location=test_utils.RESOURCE_LOCATION,
            parameters=test_utils.PARAMETERS,
            script_type=script_type,
            upper_timeout=CONFIG.argus.upper_timeout)

    def test_execute_powershell_resource_script_successful(self):
        test_method = self._action_manager.execute_powershell_resource_script
        self._test_execute_res_script(
            test_method=test_method, script_type=util.POWERSHELL_SCRIPT_BYPASS)

    def test_execute_powershell_resource_script_exception(self):
        test_method = self._action_manager.execute_powershell_resource_script
        self._test_execute_res_script(
            test_method=test_method, script_type=util.POWERSHELL_SCRIPT_BYPASS,
            exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.download_resource')
    def _test_get_installation_script(self, mock_download_resource, exc=None):

        if exc:
            mock_download_resource.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager.get_installation_script()
            return

        self._action_manager.get_installation_script()
        mock_download_resource.assert_called_once_with(
            test_utils.CBINIT_RESOURCE_LOCATION, test_utils.CBINIT_LOCATION)

    def test_get_installation_script_successful(self):
        self._test_get_installation_script()

    def test_get_installation_script_exception(self):
        self._test_get_installation_script(exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.wait_boot_completion')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.download_resource')
    def _test_sysprep(self, mock_download_resource, mock_wait_boot_completion,
                      download_exc=None, run_exc=None, wait_exc=None):
        cmd = r"C:\{}".format(
            test_utils.SYSPREP_RESOURCE_LOCATION.split('/')[-1])

        self._client.run_remote_cmd = mock.Mock()

        if download_exc:
            mock_download_resource.side_effect = download_exc
            with self.assertRaises(download_exc):
                self._action_manager.sysprep()
            self._client.run_remote_cmd.assert_not_called()
            return

        if wait_exc:
            mock_wait_boot_completion.side_effect = wait_exc
            with self.assertRaises(wait_exc):
                self._action_manager.sysprep()
            return

        if run_exc:
            self._client.run_remote_cmd.side_effect = run_exc
            with test_utils.LogSnatcher('argus.action_manager.windows.Windows'
                                        'ActionManager.sysprep') as snatcher:
                self.assertIsNone(self._action_manager.sysprep())
            self.assertEqual(snatcher.output[-2:],
                             ['Currently rebooting...',
                              'Wait for the machine to finish rebooting ...'])
        else:
            self.assertIsNone(self._action_manager.sysprep())

        mock_download_resource.assert_called_once_with(
            test_utils.SYSPREP_RESOURCE_LOCATION, cmd)
        mock_wait_boot_completion.assert_called_once_with()

    def test_sysprep_successful(self):
        self._test_sysprep()

    def test_sysprep_download_resource_fail(self):
        self._test_sysprep(download_exc=exceptions.ArgusTimeoutError)

    def test_sysprep_wait_boot_completion_fail(self):
        self._test_sysprep(wait_exc=exceptions.ArgusTimeoutError)

    def test_sysprep_run_remote_cmd_exc(self):
        self._test_sysprep(run_exc=requests.Timeout)

    @mock.patch('argus.action_manager.windows.WindowsActionManager.'
                'exists')
    def test_git_clone_exists(self, mock_exists):
        mock_exists.return_value = True
        self.assertRaises(exceptions.ArgusCLIError,
                          self._action_manager.git_clone,
                          test_utils.URL, test_utils.LOCATION)

    @mock.patch('argus.action_manager.windows.WindowsActionManager.'
                'exists')
    def test_git_clone_could_not_clone(self, mock_exists):
        mock_exists.return_value = False
        res = self._action_manager.git_clone(test_utils.URL,
                                             test_utils.LOCATION,
                                             count=0)
        self.assertFalse(res)

    @mock.patch('argus.action_manager.windows.WindowsActionManager.'
                'exists')
    def test_git_clone_successful(self, mock_exists):
        mock_exists.return_value = False
        self._client.run_command = mock.Mock()
        res = self._action_manager.git_clone(test_utils.URL,
                                             test_utils.LOCATION)
        self.assertTrue(res)

    @mock.patch('time.sleep')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.'
                'rmdir')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.'
                'is_dir')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.'
                'exists')
    def test_git_clone_exception(self, mock_exists, mock_is_dir,
                                 mock_rmdir, mock_time):
        mock_exists.side_effect = [False, True, True]
        mock_is_dir.return_value = True
        mock_rmdir.side_effect = None
        mock_time.return_value = True
        self._client.run_command.side_effect = exceptions.ArgusError
        res = self._action_manager.git_clone(test_utils.URL,
                                             test_utils.LOCATION,
                                             count=2)
        self.assertFalse(res)

    def _test_wait_cbinit_service(self, run_command_exc=None):
        if run_command_exc:
            self._client.run_command_until_condition = mock.Mock(
                side_effect=run_command_exc)
            with self.assertRaises(run_command_exc):
                self._action_manager.wait_cbinit_service()
        else:
            self._client.run_command_until_condition = mock.Mock()
            self.assertIsNone(self._action_manager.wait_cbinit_service())

    def test_wait_cbinit_service_successful(self):
        self._test_wait_cbinit_service()

    def test_wait_cbinit_service_fail(self):
        self._test_wait_cbinit_service(
            run_command_exc=exceptions.ArgusTimeoutError)

    def _test_check_cbinit_service(self, run_command_exc=None):
        if run_command_exc:
            self._client.run_command_until_condition = mock.Mock(
                side_effect=run_command_exc)
            with self.assertRaises(run_command_exc):
                self._action_manager.check_cbinit_service(
                    test_utils.SEARCHED_PATHS)
        else:
            self._client.run_command_until_condition = mock.Mock()
            self.assertIsNone(
                self._action_manager.check_cbinit_service(
                    test_utils.SEARCHED_PATHS))

    def test_check_cbinit_service_successful(self):
        self._test_check_cbinit_service()

    def test_check_cbinit_service_fail(self):
        self._test_check_cbinit_service(
            run_command_exc=exceptions.ArgusTimeoutError)

    def test_check_cbinit_service_fail_clierror(self):
        self._client.run_command_until_condition = mock.Mock(
            side_effect=[None, exceptions.ArgusCLIError, None])

        with self.assertRaises(exceptions.ArgusCLIError):
            self._action_manager.check_cbinit_service(
                test_utils.SEARCHED_PATHS)
        self.assertEqual(
            self._client.run_command_until_condition.call_count, 2)

    @test_utils.ConfPatcher('image_username', test_utils.USERNAME, 'openstack')
    @mock.patch('argus.action_manager.windows.wait_boot_completion')
    def _test_wait_boot_completion(self, mock_wait_boot_completion, exc=None):
        if exc:
            mock_wait_boot_completion.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager.wait_boot_completion()
            return

        self._action_manager.wait_boot_completion()
        mock_wait_boot_completion.assert_called_once_with(
            self._client, test_utils.USERNAME)

    def test_wait_boot_completion_successful(self):
        self._test_wait_boot_completion()

    def test_wait_boot_completion_fail(self):
        self._test_wait_boot_completion(exc=exceptions.ArgusCLIError)

    @test_utils.ConfPatcher('resources', test_utils.BASE_RESOURCE, 'argus')
    def test_specific_prepare(self):
        resource = (test_utils.BASE_RESOURCE +
                    test_utils.ARGUS_AGENT_RESOURCE_LOCATION)
        agent_location = test_utils.ARGUS_AGENT_LOCATION
        expected_logging = [
            "Downloading from {} to {} ".format(resource, agent_location),
            "Prepare something specific for OS Type {}".format(self._os_type)]
        with test_utils.LogSnatcher('argus.action_manager.windows'
                                    '.WindowsActionManager'
                                    '.specific_prepare') as snatcher:
            self.assertIsNone(self._action_manager.specific_prepare())
            self.assertEqual(snatcher.output, expected_logging)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.exists')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.is_file')
    def _test_remove(self, mock_is_file, mock_exists,
                     is_file=True, exists=True,
                     is_file_exc=None, exists_exc=None, run_exc=None):
        cmd = "Remove-Item -Force -Path '{path}'".format(path=test_utils.PATH)

        mock_exists.return_value = exists
        mock_is_file.return_value = is_file

        if not exists or not is_file:
            with self.assertRaises(exceptions.ArgusCLIError):
                self._action_manager.remove(test_utils.PATH)
            return

        if exists_exc:
            mock_exists.side_effect = exists_exc
            with self.assertRaises(exists_exc):
                self._action_manager.remove(test_utils.PATH)
            return

        if is_file_exc:
            mock_exists.side_effect = is_file_exc
            with self.assertRaises(is_file_exc):
                self._action_manager.remove(test_utils.PATH)
            return

        if run_exc:
            self._client.run_command_with_retry.side_effect = run_exc
            with self.assertRaises(run_exc):
                self._action_manager.remove(test_utils.PATH)
            return

        self._action_manager.remove(test_utils.PATH)
        self._client.run_command_with_retry.assert_called_once_with(
            cmd, command_type=util.POWERSHELL)

    def test_remove_successful(self):
        self._test_remove()

    def test_remove_not_exists(self):
        self._test_remove(exists=False)

    def test_remove_is_not_file(self):
        self._test_remove(is_file=False)

    def test_remove_exists_exception(self):
        self._test_remove(exists_exc=exceptions.ArgusTimeoutError)

    def test_remove_is_file_exception(self):
        self._test_remove(is_file_exc=exceptions.ArgusTimeoutError)

    def test_remove_run_command_exception(self):
        self._test_remove(run_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.exists')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.is_dir')
    def _test_rmdir(self, mock_is_dir, mock_exists,
                    is_dir=True, exists=True,
                    is_dir_exc=None, exists_exc=None, run_exc=None):
        cmd = "Remove-Item -Force -Recurse -Path '{path}'".format(
            path=test_utils.PATH)

        mock_exists.return_value = exists
        mock_is_dir.return_value = is_dir

        if not exists or not is_dir:
            with self.assertRaises(exceptions.ArgusCLIError):
                self._action_manager.rmdir(test_utils.PATH)
            return

        if exists_exc:
            mock_exists.side_effect = exists_exc
            with self.assertRaises(exists_exc):
                self._action_manager.rmdir(test_utils.PATH)
            return

        if is_dir_exc:
            mock_exists.side_effect = is_dir_exc
            with self.assertRaises(is_dir_exc):
                self._action_manager.rmdir(test_utils.PATH)
            return

        if run_exc:
            self._client.run_command_with_retry.side_effect = run_exc
            with self.assertRaises(run_exc):
                self._action_manager.rmdir(test_utils.PATH)
            return

        self._action_manager.rmdir(test_utils.PATH)
        self._client.run_command_with_retry.assert_called_once_with(
            cmd, command_type=util.POWERSHELL)

    def test_rmdir_successful(self):
        self._test_rmdir()

    def test_rmdir_not_exists(self):
        self._test_rmdir(exists=False)

    def test_rmdir_is_not_file(self):
        self._test_rmdir(is_dir=False)

    def test_rmdir_exists_exception(self):
        self._test_rmdir(exists_exc=exceptions.ArgusTimeoutError)

    def test_rmdir_is_dir_exception(self):
        self._test_rmdir(is_dir_exc=exceptions.ArgusTimeoutError)

    def test_rmdir_run_command_exception(self):
        self._test_rmdir(run_exc=exceptions.ArgusTimeoutError)

    def _test__exists(self, fail=False, run_command_exc=None):
        cmd = 'Test-Path -PathType {} -Path "{}"'.format(
            test_utils.PATH_TYPE, test_utils.PATH)

        if run_command_exc:
            self._client.run_command_with_retry = mock.Mock(
                side_effect=run_command_exc)
            with self.assertRaises(run_command_exc):
                self._action_manager._exists(
                    test_utils.PATH, test_utils.PATH_TYPE)
            return

        if fail:
            self._client.run_command_with_retry.return_value = (
                "False", "fake-stderr", 0)
            self.assertFalse(self._action_manager._exists(
                test_utils.PATH, test_utils.PATH_TYPE))
        else:
            self._client.run_command_with_retry.return_value = (
                "True", "fake-stderr", 0)
            self.assertTrue(self._action_manager._exists(
                test_utils.PATH, test_utils.PATH_TYPE))

        self._client.run_command_with_retry.assert_called_once_with(
            cmd=cmd, command_type=util.POWERSHELL)

    def test__exists_successful(self):
        self._test__exists()

    def test__exists_fail(self):
        self._test__exists(fail=True)

    def test__exists_fail_exception(self):
        self._test__exists(run_command_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._exists')
    def _test_exists(self, mock_exists, fail=False, exc=None):
        if exc:
            mock_exists.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager.exists(test_utils.PATH)
            return

        if fail:
            mock_exists.return_value = False
            self.assertFalse(self._action_manager.exists(test_utils.PATH))
        else:
            mock_exists.return_value = True
            self.assertTrue(self._action_manager.exists(test_utils.PATH))

        mock_exists.assert_called_once_with(
            test_utils.PATH, self._action_manager.PATH_ANY)

    def test_exists_successful(self):
        self._test_exists()

    def test_exists_fail(self):
        self._test_exists(fail=True)

    def test_exists_fail_exception(self):
        self._test_exists(exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._exists')
    def _test_is_file(self, mock_exists, fail=False, exc=None):
        if exc:
            mock_exists.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager.is_file(test_utils.PATH)
            return

        if fail:
            mock_exists.return_value = False
            self.assertFalse(self._action_manager.is_file(test_utils.PATH))
        else:
            mock_exists.return_value = True
            self.assertTrue(self._action_manager.is_file(test_utils.PATH))

        mock_exists.assert_called_once_with(
            test_utils.PATH, self._action_manager.PATH_LEAF)

    def test_is_file_successful(self):
        self._test_is_file()

    def test_is_file_fail(self):
        self._test_is_file(fail=True)

    def test_is_file_fail_exception(self):
        self._test_is_file(exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._exists')
    def _test_is_dir(self, mock_exists, fail=False, exc=None):
        if exc:
            mock_exists.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager.is_dir(test_utils.PATH)
            return

        if fail:
            mock_exists.return_value = False
            self.assertFalse(self._action_manager.is_dir(test_utils.PATH))
        else:
            mock_exists.return_value = True
            self.assertTrue(self._action_manager.is_dir(test_utils.PATH))

        mock_exists.assert_called_once_with(
            test_utils.PATH, self._action_manager.PATH_CONTAINER)

    def test_is_dir_successful(self):
        self._test_is_dir()

    def test_is_dir_fail(self):
        self._test_is_dir(fail=True)

    def test_is_dir_fail_exception(self):
        self._test_is_dir(exc=exceptions.ArgusTimeoutError)

    def _test_new_item(self, run_command_exc=None):
        cmd = "New-Item -Path '{}' -Type {} -Force".format(
            test_utils.PATH, test_utils.ITEM_TYPE)

        if run_command_exc:
            self._client.run_command_with_retry = mock.Mock(
                side_effect=run_command_exc)
            with self.assertRaises(run_command_exc):
                self._action_manager._new_item(
                    test_utils.PATH, test_utils.ITEM_TYPE)
        else:
            self._client.run_command_with_retry = mock.Mock()
            self.assertIsNone(
                self._action_manager._new_item(
                    test_utils.PATH, test_utils.ITEM_TYPE))
            self._client.run_command_with_retry.assert_called_once_with(
                cmd=cmd, command_type=util.POWERSHELL)

    def test_new_item_successful(self):
        self._test_new_item()

    def test_new_item_fail(self):
        self._test_new_item(run_command_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.exists')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._new_item')
    def _test_mkdir(self, mock_new_item, mock_exists, exists=False,
                    exists_exc=None, new_item_exc=None):
        if exists_exc:
            mock_exists.side_effect = exists_exc
            with self.assertRaises(exists_exc):
                self._action_manager.mkdir(test_utils.PATH)
            return

        mock_exists.return_value = exists

        if exists:
            with self.assertRaises(exceptions.ArgusCLIError):
                self._action_manager.mkdir(test_utils.PATH)
            return

        if new_item_exc:
            mock_new_item.side_effect = new_item_exc
            with self.assertRaises(new_item_exc):
                self._action_manager.mkdir(test_utils.PATH)
            return

        self.assertIsNone(self._action_manager.mkdir(test_utils.PATH))

    def test_mkdir_successful(self):
        self._test_mkdir()

    def test_mkdir_exists_fail(self):
        self._test_mkdir(exists=True)

    def test_mkdir_exists_fail_exception(self):
        self._test_mkdir(exists_exc=exceptions.ArgusTimeoutError)

    def test_mkdir_new_item_fail_exception(self):
        self._test_mkdir(new_item_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.is_file')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.is_dir')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._new_item')
    def _test_mkfile(self, mock_new_item, mock_is_dir, mock_is_file,
                     is_file=False, is_dir=False, is_file_exc=None,
                     is_dir_exc=None, new_item_exc=None, run_command_exc=None):
        self._client.run_command_with_retry = mock.Mock()

        mock_is_file.return_value = is_file
        mock_is_dir.return_value = is_dir

        if is_file and not run_command_exc:
            log = ("File '{}' already exists. LastWriteTime and"
                   " LastAccessTime will be updated.".format(test_utils.PATH))

            with test_utils.LogSnatcher('argus.action_manager.windows.Windows'
                                        'ActionManager.mkfile') as snatcher:
                self.assertIsNone(self._action_manager.mkfile(test_utils.PATH))
            self.assertEqual(snatcher.output, [log])
            self._client.run_command_with_retry.assert_called_once_with(
                "echo $null >> '{}'".format(test_utils.PATH),
                command_type=util.POWERSHELL)
            return

        if is_file_exc:
            mock_is_file.side_effect = is_file_exc
            with self.assertRaises(is_file_exc):
                self._action_manager.mkfile(test_utils.PATH)
            return

        if is_file and run_command_exc:
            self._client.run_command_with_retry.side_effect = run_command_exc
            with self.assertRaises(run_command_exc):
                self._action_manager.mkfile(test_utils.PATH)
            return

        if not is_file and is_dir:
            with self.assertRaises(exceptions.ArgusCLIError):
                self._action_manager.mkfile(test_utils.PATH)
            return

        if not is_file and is_dir_exc:
            mock_is_dir.side_effect = is_dir_exc
            with self.assertRaises(is_dir_exc):
                self._action_manager.mkfile(test_utils.PATH)
            return

        if not is_file and not is_dir and new_item_exc:
            mock_new_item.side_effect = new_item_exc
            with self.assertRaises(new_item_exc):
                self._action_manager.mkfile(test_utils.PATH)
            return

        self._action_manager.mkfile(test_utils.PATH)
        mock_new_item.assert_called_once_with(
            test_utils.PATH, self._action_manager._FILE)

    def test_mkfile_new_item_successful(self):
        self._test_mkfile()

    def test_mkfile_new_item_exception(self):
        self._test_mkfile(new_item_exc=exceptions.ArgusTimeoutError)

    def test_mkfile_is_file_successful(self):
        self._test_mkfile(is_file=True)

    def test_mkfile_is_file_exception(self):
        self._test_mkfile(is_file_exc=exceptions.ArgusTimeoutError)

    def test_mkfile_run_command_exception(self):
        self._test_mkfile(
            is_file=True, run_command_exc=exceptions.ArgusTimeoutError)

    def test_mkfile_is_dir_successful(self):
        self._test_mkfile(is_dir=True)

    def test_mkfile_is_dir_exception(self):
        self._test_mkfile(is_dir_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.is_dir')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.mkfile')
    def _test_touch(self, mock_mkfile, mock_is_dir, is_dir=False,
                    is_dir_exc=None, run_command_exc=None, mkfile_exc=None):
        mock_is_dir.return_value = is_dir

        if is_dir:
            self._client.run_command_with_retry = mock.Mock()

            if run_command_exc:
                (self._client.run_command_with_retry.
                 side_effect) = run_command_exc
                with self.assertRaises(run_command_exc):
                    self._action_manager.touch(test_utils.PATH)
                return

            cmd = ("$datetime = get-date;"
                   "$dir = Get-Item '{}';"
                   "$dir.LastWriteTime = $datetime;"
                   "$dir.LastAccessTime = $datetime;").format(test_utils.PATH)

            self.assertIsNone(self._action_manager.touch(test_utils.PATH))
            self._client.run_command_with_retry.assert_called_once_with(
                cmd, command_type=util.POWERSHELL)
            return

        if is_dir_exc:
            mock_is_dir.side_effect = is_dir_exc
            with self.assertRaises(is_dir_exc):
                self._action_manager.touch(test_utils.PATH)
            return

        if mkfile_exc:
            mock_mkfile.side_effect = mkfile_exc
            with self.assertRaises(mkfile_exc):
                self._action_manager.touch(test_utils.PATH)
            return

        self.assertIsNone(self._action_manager.touch(test_utils.PATH))

    def test_touch_successful(self):
        self._test_touch()

    def test_touch_mkfile_exception(self):
        self._test_touch(mkfile_exc=exceptions.ArgusTimeoutError)

    def test_touch_run_command_exception(self):
        self._test_touch(
            is_dir=True, run_command_exc=exceptions.ArgusTimeoutError)

    def test_touch_is_dir_successful(self):
        self._test_touch(is_dir=True)

    def test_touch_is_dir__exception(self):
        self._test_touch(is_dir_exc=exceptions.ArgusTimeoutError)

    def _test_execute(self, exc=None):
        if exc:
            self._client.run_command_with_retry = mock.Mock(side_effect=exc)
            with self.assertRaises(exc):
                self._action_manager._execute(
                    test_utils.CMD, count=CONFIG.argus.retry_count,
                    delay=CONFIG.argus.retry_delay, command_type=util.CMD)
        else:
            mock_cmd_retry = mock.Mock()
            mock_cmd_retry.return_value = (test_utils.STDOUT,
                                           test_utils.STDERR,
                                           test_utils.EXIT_CODE)
            self._client.run_command_with_retry = mock_cmd_retry
            self.assertEqual(self._action_manager._execute(
                test_utils.CMD, count=CONFIG.argus.retry_count,
                delay=CONFIG.argus.retry_delay,
                command_type=util.CMD), test_utils.STDOUT)
            self._client.run_command_with_retry.assert_called_once_with(
                test_utils.CMD, count=CONFIG.argus.retry_count,
                delay=CONFIG.argus.retry_delay, command_type=util.CMD,
                upper_timeout=CONFIG.argus.upper_timeout)

    def test_execute(self):
        self._test_execute()

    def test_execute_argus_timeout_error(self):
        self._test_execute(exceptions.ArgusTimeoutError)

    def test_execute_argus_error(self):
        self._test_execute(exceptions.ArgusError)

    def _test_check_cbinit_installation(self, get_python_dir_exc=None,
                                        run_remote_cmd_exc=None):
        if get_python_dir_exc:
            introspection.get_python_dir = mock.Mock(
                side_effect=get_python_dir_exc)
            self.assertFalse(self._action_manager.check_cbinit_installation())
            return

        cmd = r'& "{}\python.exe" -c "import cloudbaseinit"'.format(
            test_utils.PYTHON_DIR)
        introspection.get_python_dir = mock.Mock(
            return_value=test_utils.PYTHON_DIR)
        if run_remote_cmd_exc:
            self._client.run_remote_cmd = mock.Mock(
                side_effect=run_remote_cmd_exc)
            self.assertFalse(self._action_manager.check_cbinit_installation())
            self._client.run_remote_cmd.assert_called_once_with(
                cmd=cmd, command_type=util.POWERSHELL)
            return

        self._client.run_remote_cmd = mock.Mock()
        self.assertTrue(self._action_manager.check_cbinit_installation())

    def test_check_cbinit_installation(self):
        self._test_check_cbinit_installation()

    def test_check_cbinit_installation_get_python_dir_exc(self):
        self._test_check_cbinit_installation(
            get_python_dir_exc=exceptions.ArgusError)

    def test_check_cbinit_installation_run_remote_cmd_exc(self):
        self._test_check_cbinit_installation(
            run_remote_cmd_exc=exceptions.ArgusError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager.rmdir')
    def _test_cbinit_cleanup(self, mock_rmdir, get_cbinit_dir_exc=None,
                             rmdir_exc=None):
        if get_cbinit_dir_exc:
            introspection.get_cbinit_dir = mock.Mock(
                side_effect=get_cbinit_dir_exc)
            self.assertFalse(self._action_manager.cbinit_cleanup())
            return

        introspection.get_cbinit_dir = mock.Mock(
            return_value=test_utils.CBINIT_DIR)
        if rmdir_exc:
            mock_rmdir.side_effect = rmdir_exc
            self.assertFalse(self._action_manager.cbinit_cleanup())
            return

        self.assertTrue(self._action_manager.cbinit_cleanup())

    def test_cbinit_cleanup(self):
        self._test_cbinit_cleanup()

    def test_cbinit_cleanup_get_cbinit_dir_exc(self):
        self._test_cbinit_cleanup(get_cbinit_dir_exc=exceptions.ArgusError)

    def test_cbinit_cleanup_rmdir_exc(self):
        self._test_cbinit_cleanup(rmdir_exc=exceptions.ArgusError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.cbinit_cleanup')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.check_cbinit_installation')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._deploy_using_scheduled_task')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._run_installation_script')
    def test_install_cbinit_run_installation_script(
            self, mock_run, mock_deploy, mock_check, mock_cleanup):
        mock_check.side_effect = [True]

        self.assertTrue(self._action_manager.install_cbinit())

        self.assertEqual(mock_run.call_count, 1)
        mock_deploy.assert_not_called()
        mock_cleanup.assert_not_called()

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.cbinit_cleanup')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.check_cbinit_installation')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._deploy_using_scheduled_task')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._run_installation_script')
    def test_install_cbinit_deploy_using_scheduled_task(
            self, mock_run, mock_deploy, mock_check, mock_cleanup):
        mock_check.side_effect = [False, True]

        self.assertTrue(self._action_manager.install_cbinit())

        self.assertEqual(mock_run.call_count, 1)
        self.assertEqual(mock_deploy.call_count, 1)
        self.assertEqual(mock_cleanup.call_count, 1)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.cbinit_cleanup')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.check_cbinit_installation')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._deploy_using_scheduled_task')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._run_installation_script')
    def test_install_cbinit_run_installation_script_exc(
            self, mock_run, mock_deploy, mock_check, mock_cleanup):
        mock_check.side_effect = [False, True]
        mock_deploy.side_effect = exceptions.ArgusTimeoutError

        self.assertTrue(self._action_manager.install_cbinit())

        self.assertEqual(mock_run.call_count, 2)
        self.assertEqual(mock_deploy.call_count, 1)
        self.assertEqual(mock_cleanup.call_count, 2)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.cbinit_cleanup')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.check_cbinit_installation')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._deploy_using_scheduled_task')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._run_installation_script')
    def test_install_cbinit_at_last_try(
            self, mock_run, mock_deploy, mock_check, mock_cleanup):
        mock_check.side_effect = [True]
        retry_count = CONFIG.argus.retry_count
        run_fails = [
            exceptions.ArgusTimeoutError for _ in range(retry_count)]
        deploy_fails = [
            exceptions.ArgusTimeoutError for _ in range(retry_count - 1)]
        deploy_fails.append(None)

        mock_run.side_effect = run_fails
        mock_deploy.side_effect = deploy_fails

        self.assertTrue(self._action_manager.install_cbinit())

        self.assertEqual(mock_run.call_count, CONFIG.argus.retry_count)
        self.assertEqual(mock_deploy.call_count, CONFIG.argus.retry_count)
        self.assertEqual(mock_cleanup.call_count,
                         CONFIG.argus.retry_count * 2 - 1)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.cbinit_cleanup')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.check_cbinit_installation')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._deploy_using_scheduled_task')
    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '._run_installation_script')
    def test_install_cbinit_timeout_fail(
            self, mock_run, mock_deploy, mock_check, mock_cleanup):
        retry_count = CONFIG.argus.retry_count
        mock_check.side_effect = [False for _ in range(2 * retry_count)]

        self.assertFalse(self._action_manager.install_cbinit())

        self.assertEqual(mock_run.call_count, retry_count)
        self.assertEqual(mock_deploy.call_count, retry_count)
        self.assertEqual(mock_cleanup.call_count, 2 * retry_count)

    @test_utils.ConfPatcher(
        'msi_web_location', test_utils.MSI_WEB_LOCATION, 'argus')
    def _test_run_installation_script(self, exc=None):
        mock_run_cmd_with_retry = self._client.run_command_with_retry
        if exc:
            mock_run_cmd_with_retry.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager._run_installation_script(
                    test_utils.INSTALLER)
        else:
            self._action_manager._run_installation_script(test_utils.INSTALLER)
            cmd = r'"{}" -installer {} -MsiWebLocation {}'.format(
                self._action_manager._INSTALL_SCRIPT,
                test_utils.INSTALLER, test_utils.MSI_WEB_LOCATION)
            mock_run_cmd_with_retry.assert_called_once_with(
                cmd, command_type=util.POWERSHELL_SCRIPT_BYPASS)

    def test_run_installation_script(self):
        self._test_run_installation_script()

    def test_run_installation_script_argus_timeout_error(self):
        self._test_run_installation_script(exc=exceptions.ArgusTimeoutError)

    def test_run_installation_script_argus_error(self):
        self._test_run_installation_script(exc=exceptions.ArgusError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.execute_powershell_resource_script')
    def _test_deploy_using_scheduled_task(self, mock_execute_script, exc=None):
        if exc:
            mock_execute_script.side_effect = exc
            with self.assertRaises(exc):
                self._action_manager._deploy_using_scheduled_task(
                    test_utils.INSTALLER)
        else:
            self._action_manager._deploy_using_scheduled_task(
                test_utils.INSTALLER)
            mock_execute_script.assert_called_once_with(
                'windows/schedule_installer.ps1',
                '{}'.format(test_utils.INSTALLER))

    def test_deploy_using_scheduled_task(self):
        self._test_deploy_using_scheduled_task()

    def test_deploy_using_scheduled_task_argus_timeout_error(self):
        self._test_deploy_using_scheduled_task(
            exc=exceptions.ArgusTimeoutError)

    def test_deploy_using_scheduled_task_argus_error(self):
        self._test_deploy_using_scheduled_task(exc=exceptions.ArgusError)

    def test_prepare_config(self):
        with test_utils.LogSnatcher('argus.action_manager.windows'
                                    '.WindowsActionManager'
                                    '.prepare_config') as snatcher:
            self.assertIsNone(self._action_manager.prepare_config(
                mock.Mock(), mock.Mock()))
            self.assertEqual(snatcher.output,
                             ["Config Cloudbase-Init"
                              " for {}".format(self._os_type)])


class WindowsNanoActionManagerTest(unittest.TestCase):
    """Tests for windows nano action manager class."""

    def setUp(self):
        self._client = mock.MagicMock()
        self._os_type = mock.sentinel.os_type

        self._action_manager = action_manager.WindowsNanoActionManager(
            client=self._client, os_type=self._os_type)

    def test_get_resource_path(self):
        os.path.abspath = mock.Mock(return_value=test_utils.PATH)
        resource_path = os.path.normpath(os.path.join(
            test_utils.PATH, "..", "resources", "windows", "nano_server",
            test_utils.RESOURCE))

        self.assertEqual(self._action_manager._get_resource_path(
            test_utils.RESOURCE), resource_path)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.specific_prepare')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.is_dir')
    @mock.patch('argus.action_manager.windows.WindowsActionManager.mkdir')
    @mock.patch('argus.action_manager.windows.WindowsNanoActionManager'
                '._get_resource_path')
    def _test_specific_prepare(self, mock_get_path, mock_mkdir, mock_is_dir,
                               mock_spec_prep, mkdir_exc=None, is_dir_exc=None,
                               spec_prep_exc=None, copy_file_exc=None):
        if spec_prep_exc:
            mock_spec_prep.side_effect = spec_prep_exc
            with self.assertRaises(spec_prep_exc):
                self._action_manager.specific_prepare()
            return

        if is_dir_exc:
            mock_is_dir.side_effect = is_dir_exc
            with self.assertRaises(is_dir_exc):
                self._action_manager.specific_prepare()
            return

        mock_is_dir.return_value = False

        if mkdir_exc:
            mock_mkdir.side_effect = mkdir_exc
            with self.assertRaises(mkdir_exc):
                self._action_manager.specific_prepare()
            return

        mock_get_path.return_value = test_utils.PATH

        if copy_file_exc is None:
            copy_file_exc = [None, None]
        self._client.copy_file.side_effect = copy_file_exc

        if copy_file_exc[0]:
            with self.assertRaises(copy_file_exc[0]):
                self._action_manager.specific_prepare()
            return

        if copy_file_exc[1]:
            with self.assertRaises(copy_file_exc[1]):
                self._action_manager.specific_prepare()
            return

        self._action_manager.specific_prepare()

        self.assertEqual(mock_get_path.call_count, 2)
        mock_get_path.assert_has_calls(
            [mock.call(self._action_manager._COMMON),
             mock.call(self._action_manager._DOWNLOAD_SCRIPT)])

        calls = [
            mock.call(test_utils.PATH, ntpath.join(
                self._action_manager._RESOURCE_DIRECTORY,
                self._action_manager._COMMON)),
            mock.call(test_utils.PATH, ntpath.join(
                self._action_manager._RESOURCE_DIRECTORY,
                self._action_manager._DOWNLOAD_SCRIPT))
        ]

        self.assertEqual(self._client.copy_file.call_count, 2)
        self._client.copy_file.assert_has_calls(calls)

    def test_specific_prepare_successful(self):
        self._test_specific_prepare()

    def test_specific_prepare_spec_prep_exc(self):
        self._test_specific_prepare(spec_prep_exc=exceptions.ArgusError)

    def test_specific_prepare_is_dir_exc(self):
        self._test_specific_prepare(is_dir_exc=exceptions.ArgusTimeoutError)

    def test_specific_prepare_mkdir_exc(self):
        self._test_specific_prepare(mkdir_exc=exceptions.ArgusTimeoutError)

    def test_specific_prepare_copy_file_exc_first_call(self):
        self._test_specific_prepare(
            copy_file_exc=[exceptions.ArgusError, None])

    def test_specific_prepare_copy_file_exc_second_call(self):
        self._test_specific_prepare(
            copy_file_exc=[None, exceptions.ArgusError])

    def _test_download(self, run_command_exc=None):
        if run_command_exc:
            self._client.run_command_with_retry = mock.Mock(
                side_effect=run_command_exc)
            with self.assertRaises(run_command_exc):
                self._action_manager.download(
                    test_utils.URI, test_utils.LOCATION)
        else:
            self._client.run_command_with_retry = mock.Mock()

            resource_path = ntpath.join(
                self._action_manager._RESOURCE_DIRECTORY,
                self._action_manager._DOWNLOAD_SCRIPT)
            cmd = r"{script_path} -Uri {uri} -OutFile '{outfile}'".format(
                script_path=resource_path, uri=test_utils.URI,
                outfile=test_utils.LOCATION)

            self._action_manager.download(test_utils.URI, test_utils.LOCATION)

            self._client.run_command_with_retry.assert_called_once_with(
                cmd, command_type=util.POWERSHELL)

    def test_download_successful(self):
        self._test_download()

    def test_download_exception(self):
        self._test_download(run_command_exc=exceptions.ArgusTimeoutError)

    @mock.patch('argus.action_manager.windows.WindowsActionManager'
                '.prepare_config')
    def _test_prepare_config(self, mock_prep_config, prep_config_exc=None,
                             cbi_conf_set_exc=None, cbi_conf_remove_exc=None,
                             cbi_unatt_conf_remove_exc=None):
        cbinit_conf = mock.MagicMock()
        cbinit_unattend_conf = mock.MagicMock()

        if prep_config_exc:
            mock_prep_config.side_effect = prep_config_exc
            with self.assertRaises(prep_config_exc):
                self._action_manager.prepare_config(
                    cbinit_conf, cbinit_unattend_conf)
            return

        if cbi_conf_set_exc:
            cbinit_conf.set_conf_value.side_effect = cbi_conf_set_exc
            with self.assertRaises(cbi_conf_set_exc):
                self._action_manager.prepare_config(
                    cbinit_conf, cbinit_unattend_conf)
            return

        if cbi_conf_remove_exc:
            cbinit_conf.conf.remove_option.side_effect = cbi_conf_remove_exc
            with self.assertRaises(cbi_conf_remove_exc):
                self._action_manager.prepare_config(
                    cbinit_conf, cbinit_unattend_conf)
            return

        if cbi_unatt_conf_remove_exc:
            (cbinit_unattend_conf.conf.remove_option
             .side_effect) = cbi_unatt_conf_remove_exc
            with self.assertRaises(cbi_unatt_conf_remove_exc):
                self._action_manager.prepare_config(
                    cbinit_conf, cbinit_unattend_conf)
            return

        self._action_manager.prepare_config(cbinit_conf, cbinit_unattend_conf)

        cbinit_conf.set_conf_value.assert_called_once_with(
            "stop_service_on_exit", False)
        cbinit_conf.conf.remove_option.assert_called_once_with(
            "DEFAULT", "logging_serial_port_settings")
        cbinit_unattend_conf.conf.remove_option.assert_called_once_with(
            "DEFAULT", "logging_serial_port_settings")

    def test_prepare_config_successful(self):
        self._test_prepare_config()

    def test_prepare_config_prep_config_exc(self):
        self._test_prepare_config(prep_config_exc=exceptions.ArgusError)

    def test_prepare_config_cbi_conf_set_exc(self):
        self._test_prepare_config(cbi_conf_set_exc=exceptions.ArgusError)

    def test_prepare_config_cbi_conf_remove_exc(self):
        self._test_prepare_config(
            cbi_conf_remove_exc=exceptions.ArgusError)

    def test_prepare_config_cbi_unatt_conf_remove_exc(self):
        self._test_prepare_config(
            cbi_unatt_conf_remove_exc=exceptions.ArgusError)


class ActionManagerTest(unittest.TestCase):
    """Tests for action manager functions."""

    def setUp(self):
        self._client = mock.MagicMock()

    def _test_wait_boot_completion(self, run_command_exc=None):
        if run_command_exc:
            self._client.run_command_until_condition = mock.Mock(
                side_effect=run_command_exc)
            with self.assertRaises(run_command_exc):
                action_manager.wait_boot_completion(
                    self._client, test_utils.USERNAME)
        else:
            self._client.run_command_until_condition = mock.Mock()
            self.assertIsNone(
                action_manager.wait_boot_completion(
                    self._client, test_utils.USERNAME))

    def test_wait_boot_completion_successful(self):
        self._test_wait_boot_completion()

    def test_wait_boot_completion_fail(self):
        self._test_wait_boot_completion(
            run_command_exc=exceptions.ArgusTimeoutError)

    def _test_is_nanoserver(self, run_command_test_exc=None, path_exists=True,
                            run_command_get_exc=None, is_nanoserver=True):
        client = mock.MagicMock()

        if run_command_test_exc:
            client.run_command_with_retry.side_effect = run_command_test_exc
            with self.assertRaises(run_command_test_exc):
                action_manager._is_nanoserver(client)
            return

        if not path_exists:
            client.run_command_with_retry.side_effect = [
                ("False", test_utils.STDERR, test_utils.EXIT_CODE)]
            self.assertFalse(action_manager._is_nanoserver(client))
            return

        client.run_command_with_retry.side_effect = [
            ("True", test_utils.STDERR, test_utils.EXIT_CODE)]

        if run_command_get_exc:
            client.run_command_with_retry.side_effect = run_command_get_exc
            with self.assertRaises(run_command_get_exc):
                action_manager._is_nanoserver(client)
            return

        if is_nanoserver:
            client.run_command_with_retry.side_effect = [
                ("True", test_utils.STDERR, test_utils.EXIT_CODE),
                ("1", test_utils.STDERR, test_utils.EXIT_CODE)]
        else:
            client.run_command_with_retry.side_effect = [
                ("True", test_utils.STDERR, test_utils.EXIT_CODE),
                ("0", test_utils.STDERR, test_utils.EXIT_CODE)]

        action_manager._is_nanoserver(client)

        server_level_key = (r'HKLM:\Software\Microsoft\Windows NT'
                            r'\CurrentVersion\Server\ServerLevels')
        cmd1 = r'Test-Path "{}"'.format(server_level_key)
        cmd2 = r'(Get-ItemProperty "{}").NanoServer'.format(server_level_key)

        calls = [
            mock.call(cmd1, count=CONFIG.argus.retry_count,
                      delay=CONFIG.argus.retry_delay,
                      command_type=util.POWERSHELL),
            mock.call(cmd2, count=CONFIG.argus.retry_count,
                      delay=CONFIG.argus.retry_delay,
                      command_type=util.POWERSHELL)
        ]

        client.run_command_with_retry.assert_has_calls(calls)

    def test_is_nanoserver(self):
        self._test_is_nanoserver()

    def test_is_nanoserver_run_command_test_exc(self):
        self._test_is_nanoserver(
            run_command_test_exc=exceptions.ArgusTimeoutError)

    def test_is_nanoserver_path_not_exists(self):
        self._test_is_nanoserver(path_exists=False)

    def test_is_nanoserver_run_command_get_exc(self):
        self._test_is_nanoserver(
            run_command_get_exc=exceptions.ArgusTimeoutError)

    def test_is_not_nanoserver(self):
        self._test_is_nanoserver(is_nanoserver=False)

    def _test_get_product_type(self, major_version, run_command_exc=None):
        self._client.run_command_with_retry = mock.Mock()

        if run_command_exc:
            self._client.run_command_with_retry.side_effect = run_command_exc
            with self.assertRaises(run_command_exc):
                action_manager._get_product_type(self._client, major_version)
            return

        self._client.run_command_with_retry.side_effect = [
            (test_utils.PRODUCT_TYPE_1, test_utils.STDERR,
             test_utils.EXIT_CODE)
        ]

        cmdlet = action_manager.Windows8ActionManager.WINDOWS_MANAGEMENT_CMDLET
        if major_version == 10:
            cmdlet = (action_manager.Windows10ActionManager
                      .WINDOWS_MANAGEMENT_CMDLET)
        cmd = r"({} -Class Win32_OperatingSystem).producttype".format(cmdlet)

        self.assertEqual(
            action_manager._get_product_type(self._client, major_version),
            int(test_utils.PRODUCT_TYPE_1))
        self._client.run_command_with_retry.assert_called_once_with(
            cmd, count=CONFIG.argus.retry_count,
            delay=CONFIG.argus.retry_delay,
            command_type=util.POWERSHELL)

    def test_get_product_type_major_version_6(self):
        self._test_get_product_type(major_version=test_utils.MAJOR_VERSION_6)

    def test_get_product_type_major_version_10(self):
        self._test_get_product_type(major_version=test_utils.MAJOR_VERSION_10)

    def test_get_product_type_run_command_exc(self):
        self._test_get_product_type(
            major_version=test_utils.MAJOR_VERSION_6,
            run_command_exc=exceptions.ArgusTimeoutError)

    @test_utils.ConfPatcher('image_username', test_utils.IMAGE_USERNAME,
                            'openstack')
    @mock.patch('argus.action_manager.windows.wait_boot_completion')
    @mock.patch('argus.action_manager.windows._get_product_type')
    @mock.patch('argus.action_manager.windows._is_nanoserver')
    def _test_get_windows_action_manager(
            self, mock_is_nanoserver, mock_get_product_type,
            mock_wait_boot_completion, major_version, minor_version,
            product_type, is_nanoserver=False, is_nanoserver_exc=None,
            get_product_type_exc=None, get_os_version_exc=None,
            wait_boot_completion_exc=None):

        if wait_boot_completion_exc:
            mock_wait_boot_completion.side_effect = wait_boot_completion_exc
            with self.assertRaises(wait_boot_completion_exc):
                action_manager.get_windows_action_manager(self._client)
            return

        if get_os_version_exc is None:
            get_os_version_exc = [None, None]
        introspection.get_os_version = mock.Mock(
            side_effect=get_os_version_exc)

        if get_os_version_exc[0]:
            with self.assertRaises(get_os_version_exc[0]):
                action_manager.get_windows_action_manager(self._client)
            return

        if get_os_version_exc[1]:
            with self.assertRaises(get_os_version_exc[1]):
                action_manager.get_windows_action_manager(self._client)
            return

        introspection.get_os_version.side_effect = [major_version,
                                                    minor_version]

        if get_product_type_exc:
            mock_get_product_type.side_effect = get_product_type_exc
            with self.assertRaises(get_product_type_exc):
                action_manager.get_windows_action_manager(self._client)
            return

        mock_get_product_type.return_value = product_type

        windows_type = util.WINDOWS_VERSION.get(
            (major_version, minor_version, product_type), util.WINDOWS)

        if is_nanoserver_exc:
            mock_is_nanoserver.side_effect = is_nanoserver_exc
            with self.assertRaises(is_nanoserver_exc):
                action_manager.get_windows_action_manager(self._client)
            return

        mock_is_nanoserver.return_value = is_nanoserver

        if isinstance(windows_type, dict):
            windows_type = windows_type[is_nanoserver]

        log_message_booting = ("Waiting for boot completion in order to "
                               "select an Action Manager ...")

        log_message_action_manager_type = (
            "We got the OS type {} because we have the major "
            "Version : {}, the minor version {}, the product Type"
            " : {}, and IsNanoserver: {}").format(windows_type, major_version,
                                                  minor_version, product_type,
                                                  is_nanoserver)

        log_message_log_update = ("Update the logger with the following OS"
                                  " version: {}").format(windows_type)
        with test_utils.LogSnatcher('argus.action_manager.windows'
                                    '.get_windows_action_manager') as snatcher:
            self.assertTrue(isinstance(
                action_manager.get_windows_action_manager(self._client),
                action_manager.WindowsActionManagers[windows_type]))
            self.assertEqual(snatcher.output,
                             [log_message_booting,
                              log_message_action_manager_type,
                              log_message_log_update])

    def test_get_windows_action_manager_wait_boot_completion_exc(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_1),
            wait_boot_completion_exc=exceptions.ArgusTimeoutError)

    def test_get_windows_action_manager_get_major_version_exc(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_1),
            get_os_version_exc=[exceptions.ArgusTimeoutError, None])

    def test_get_windows_action_manager_get_minor_version_exc(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_1),
            get_os_version_exc=[None, exceptions.ArgusTimeoutError])

    def test_get_windows_action_manager_get_product_type_exc(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_1),
            get_product_type_exc=exceptions.ArgusTimeoutError)

    def test_get_windows_action_manager_is_nanoserver_exc(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_1),
            is_nanoserver_exc=exceptions.ArgusTimeoutError)

    def test_get_windows_10_action_manager(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_1))

    def test_get_windows_nano_action_manager(self):
        self._test_get_windows_action_manager(
            major_version=int(test_utils.MAJOR_VERSION_10),
            minor_version=int(test_utils.MINOR_VERSION_0),
            product_type=int(test_utils.PRODUCT_TYPE_3),
            is_nanoserver=True)
