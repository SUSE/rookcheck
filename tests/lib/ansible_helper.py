# Copyright (c) 2019 SUSE LINUX GmbH
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# The Hardware module should take care of the operating system abstraction
# through images.
# libcloud will provide a common set of cloud-agnostic objects such as Node[s]
# We might extend the Node object to have an easy way to run arbitrary commands
# on the node such as Node.execute().
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

import logging
import os
import shutil
import tarfile
import tempfile
from typing import Dict
import urllib.request
import yaml

from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.playbook.play import Play
from ansible import context as ansible_context
import ansible.plugins.loader
import ansible.executor.task_queue_manager
from ansible.plugins.callback.default import CallbackModule
import ansible.constants as C

from tests.lib.hardware.node_base import NodeBase


logger = logging.getLogger(__name__)


class ResultCallback(CallbackModule):
    """This callback stores the latest results for a run in an instance
    variable (host_ok, host_unreachable, host_failed).
    It is intended to be instanciated for each individual run.
    """
    def __init__(self):
        super(ResultCallback, self).__init__()
        self._load_name = "CustomResultCallback"
        self.set_options()
        self.host_ok = {}
        self.host_unreachable = {}
        self.host_failed = {}

    def v2_runner_on_unreachable(self, result):
        if result._host.get_name() not in self.host_unreachable:
            self.host_unreachable[result._host.get_name()] = []
        self.host_unreachable[result._host.get_name()].append(result)
        super(ResultCallback, self).v2_runner_on_unreachable(result)

    def v2_runner_on_ok(self, result):
        if result._host.get_name() not in self.host_ok:
            self.host_ok[result._host.get_name()] = []
        self.host_ok[result._host.get_name()].append(result)
        super(ResultCallback, self).v2_runner_on_ok(result)

    def v2_runner_on_failed(self, result, ignore_errors=False):
        if result._host.get_name() not in self.host_failed:
            self.host_failed[result._host.get_name()] = []
        self.host_failed[result._host.get_name()].append(result)
        super(ResultCallback, self).v2_runner_on_failed(result, ignore_errors)


class AnsibleRunner(object):
    def __init__(self, nodes: Dict[str, NodeBase], working_dir=None):
        # since the API is constructed for CLI it expects certain options to
        # always be set in the context object
        ansible_context.CLIARGS = ImmutableDict(
            connection='ssh', module_path=[''], forks=10,
            gather_facts='no', host_key_checking=False,
            verbosity=4
        )

        # Takes care of finding and reading yaml, json and ini files
        self.loader = DataLoader()
        self.passwords = dict(vault_pass='secret')

        # create inventory, use path to host config file as source or hosts in
        # a comma separated string
        self.inventory_file = self.create_inventory(nodes, working_dir)
        self.inventory = InventoryManager(
            loader=self.loader, sources=self.inventory_file)

        # variable manager takes care of merging all the different sources to
        # give you a unified view of variables available in each context
        self.variable_manager = VariableManager(
            loader=self.loader, inventory=self.inventory)

        mitogen_plugin = self.download_mitogen(working_dir)

        # Hack around loading strategy modules:
        ansible.executor.task_queue_manager.strategy_loader = \
            ansible.plugins.loader.PluginLoader(
                'StrategyModule',
                'ansible.plugins.strategy',
                [mitogen_plugin] + C.DEFAULT_STRATEGY_PLUGIN_PATH,
                'strategy_plugins',
                required_base_class='StrategyBase',
            )

    def create_inventory(self, nodes, working_dir=None):
        if not working_dir:
            # NOTE(jhesketh): The working dir is never cleaned up. This is
            # somewhat deliberate to keep the private key if it is needed for
            # debugging.
            working_dir = tempfile.mkdtemp()

        inv = {
            'all': {
                'hosts': {},
                'children': {}
            }
        }

        for node in nodes.values():
            if not node.tags:
                inv['all']['hosts'][node.name] = node.ansible_inventory_vars()
            else:
                for tag in node.tags:
                    if tag not in inv['all']['children']:
                        inv['all']['children'][tag] = {'hosts': {}}
                    inv['all']['children'][tag]['hosts'][node.name] = \
                        node.ansible_inventory_vars()

        inv_path = os.path.join(working_dir, "inventory")
        with open(inv_path, 'w') as inv_file:
            yaml.dump(inv, inv_file)

        return inv_path

    def run_play(self, play_source):
        # Create a new results instance for each run
        # Instantiate our ResultCallback for handling results as they come in.
        # Ansible expects this to be one of its main display outlets
        results_callback = ResultCallback()

        # Create play object, playbook objects use .load instead of init or new
        # methods,
        # this will also automatically create the task objects from the info
        # provided in play_source
        play = Play().load(play_source, variable_manager=self.variable_manager,
                           loader=self.loader)

        # Run it - instantiate task queue manager, which takes care of forking
        # and setting up all objects to iterate over host list and tasks

        # TODO(jhesketh): the results callback could be a new instance each
        # time storing the run's specific feedback to return as a dict in this
        # method.
        tqm = None
        result = -1
        try:
            tqm = ansible.executor.task_queue_manager.TaskQueueManager(
                inventory=self.inventory,
                variable_manager=self.variable_manager,
                loader=self.loader,
                passwords=self.passwords,
                stdout_callback=results_callback,
            )
            result = tqm.run(play)
        finally:
            # we always need to cleanup child procs and the structures we use
            # to communicate with them
            if tqm is not None:
                tqm.cleanup()

            # Remove ansible tmpdir
            shutil.rmtree(C.DEFAULT_LOCAL_TMP, True)

        # TODO(jhesketh): Return the results of this run individually
        if result != 0:
            # TODO(jhesketh): Provide more useful information
            # *0* -- OK or no hosts matched
            # *1* -- Error
            # *2* -- One or more hosts failed
            # *3* -- One or more hosts were unreachable
            # *4* -- Parser error
            # *5* -- Bad or incomplete options
            # *99* -- User interrupted execution
            # *250* -- Unexpected error
            Exception("An error occurred running playbook")

        return results_callback

    def download_mitogen(self, working_dir):
        logger.info("Downloading and unpacking mitogen")
        tar_url = "https://networkgenomics.com/try/mitogen-0.2.9.tar.gz"
        stream = urllib.request.urlopen(tar_url)
        tar_file = tarfile.open(fileobj=stream, mode="r|gz")
        tar_file.extractall(path=working_dir)
        return os.path.join(
            working_dir, 'mitogen-0.2.9/ansible_mitogen/plugins/strategy')
