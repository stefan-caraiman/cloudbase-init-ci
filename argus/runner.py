# Copyright 2014 Cloudbase Solutions Srl
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

import json
import os
import sys
import time
import unittest

from argus import exceptions
from argus import util


CONF = util.get_config()


class _WritelnDecorator(object):
    """Used to decorate file-like objects with a handy 'writeln' method"""
    def __init__(self, stream):
        self.stream = stream

    def __getattr__(self, attr):
        if attr in ('stream', '__getstate__'):
            raise AttributeError(attr)
        return getattr(self.stream, attr)

    def writeln(self, arg=None):
        if arg:
            self.write(arg)
        self.write('\n')  # text-mode streams translate to \r\n if needed


class Runner(object):
    """Scenarios runner class.

    Given a list of scenarios, this class iterates through each
    one and calls its underlying tests.
    """

    def __init__(self, scenarios, stream=None):
        self._scenarios = scenarios
        self._stream = _WritelnDecorator(stream or sys.stderr)

    def run(self):
        start_time = time.time()
        tests_run = 0
        expected_failures = unexpected_successes = skipped = 0
        failures = errors = 0

        # pylint: disable=redefined-outer-name
        for my_scenario in self._scenarios:
            result = my_scenario.run()
            result.printErrors()
            tests_run += result.testsRun
            expected_failures += len(result.expectedFailures)
            unexpected_successes += len(result.unexpectedSuccesses)
            skipped += len(result.skipped)
            failures += len(result.failures)
            errors += len(result.errors)

        time_taken = time.time() - start_time

        self._stream.writeln("Ran %d test%s in %.3fs" %
                             (tests_run,
                              tests_run != 1 and "s" or "", time_taken))
        self._stream.writeln()

        if failures or errors:
            self._stream.write("FAILED")
        else:
            self._stream.write("OK")

        infos = []

        if failures or errors:
            if failures:
                infos.append("failures=%d" % failures)
            if errors:
                infos.append("errors=%d" % errors)

        if skipped:
            infos.append("skipped=%d" % skipped)
        if expected_failures:
            infos.append("expected failures=%d" % expected_failures)
        if unexpected_successes:
            infos.append("unexpected successes=%d" % unexpected_successes)

        if infos:
            self._stream.writeln(" (%s)" % (", ".join(infos),))
        else:
            self._stream.write("\n")
        return result


def _load_userdata(userdata):
    userdata, is_argus, part = userdata.partition("argus.")
    if is_argus:
        userdata = util.get_resource(part.replace(".", "/"))
    else:
        with open(userdata, 'rb') as stream:
            userdata = stream.read()
    return userdata


def _load_metadata(metadata):
    if os.path.isfile(metadata):
        with open(metadata) as stream:
            return json.load(stream)
    return json.loads(metadata)


def build_scenario(scenario, config):
    test_result = unittest.TextTestResult(
        _WritelnDecorator(sys.stderr), None, 0)
    image = None

    for image in config.images:
        if image.name == scenario.image:
            break
    else:
        raise exceptions.ArgusError(
            "Could not find the image for the scenario %r" % scenario.name)

    # TODO: load userdata and metadata
    if scenario.userdata:
        userdata = _load_userdata(scenario.userdata)
    else:
        userdata = None
    metadata = _load_metadata(scenario.metadata)
    test_class = util.load_qualified_object(scenario.test_class)
    recipee = util.load_qualified_object(scenario.recipee)
    scenario_class = util.load_qualified_object(scenario.scenario)

    return scenario_class(
        test_class=test_class,
        recipee=recipee,
        metadata=metadata,
        userdata=userdata,
        image=image,
        result=test_result)


def run_scenarios():
    # TODO(cpopa): add scenario filtering.
    scenario_classes = [build_scenario(scenario, CONF)
                        for scenario in CONF.scenarios]
    Runner(scenario_classes).run()