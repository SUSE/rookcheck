# Copyright (c) 2020 SUSE LLC
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

import contextlib
import logging
import os
from pprint import pformat
import shutil
import subprocess
from typing import Dict, Optional
import uuid

import paramiko.rsakey

from tests import config
from tests.lib.ansible_helper import AnsibleRunner
from tests.lib.hardware.node_base import NodeBase


logger = logging.getLogger(__name__)


class Workspace():
    def __init__(self):
        # Set up a common workspace that most modules will expect
        self._workspace_uuid: str = str(uuid.uuid4())[:8]
        self._working_dir: str = self._get_working_dir()

        self._sshkey_name: Optional[str] = None
        self._public_key: Optional[str] = None
        self._private_key: Optional[str] = None

        self._generate_keys()

        self._ssh_agent_auth_sock: str = os.path.join(
            self.working_dir, 'ssh-agent.sock')
        self._ssh_agent()

        self._ansible_runner: Optional[AnsibleRunner] = None
        self._ansible_runner_nodes: Dict[str, NodeBase] = {}

        logger.info(f"Workspace {self.name} set up at {self.working_dir}")
        logger.info(f"public key {self.public_key}")
        logger.info(f"private key {self.private_key}")

    # TODO fix self rep

    @property
    def name(self) -> str:
        return "%s%s" % (config.CLUSTER_PREFIX, self._workspace_uuid)

    @property
    def working_dir(self) -> str:
        return self._working_dir

    @property
    def sshkey_name(self):
        return self._sshkey_name

    @property
    def public_key(self):
        return self._public_key

    @property
    def private_key(self):
        return self._private_key

    def _generate_keys(self):
        """
        Generatees a public and private key
        """
        key = paramiko.rsakey.RSAKey.generate(2048)
        self._private_key = os.path.join(
            self.working_dir, 'private.key')
        with open(self._private_key, 'w') as key_file:
            key.write_private_key(key_file)
        os.chmod(self._private_key, 0o400)

        self._sshkey_name = "%s_key" % (self.name)
        self._public_key = "%s %s" % (key.get_name(), key.get_base64())

    @property
    def ssh_agent_auth_sock(self) -> str:
        return self._ssh_agent_auth_sock

    @property
    def ssh_agent_pid(self) -> str:
        return self._ssh_agent_pid

    def _ssh_agent(self):
        try:
            res = subprocess.run(
                ['ssh-agent', '-a', self._ssh_agent_auth_sock],
                check=True, capture_output=True)
        except subprocess.CalledProcessError:
            logger.exception('Failed to start ssh agent')
            raise

        logger.info(f"ssh-agent started: {res.stdout.decode('utf-8')}")
        self._ssh_agent_pid = res.stdout.decode(
            'utf-8').split(';')[2].split('=')[1]
        try:
            res = subprocess.run(
                ['ssh-add', self.private_key],
                check=True,
                env={
                    'SSH_AUTH_SOCK': self.ssh_agent_auth_sock,
                    'SSH_AGENT_PID': self.ssh_agent_pid,
                }
            )
        except subprocess.CalledProcessError:
            logger.exception('Failed to add keys to agent')
            raise

    def execute_ansible_play_raw(self, playbook: str,
                                 nodes: Dict[str, NodeBase],
                                 inventory_vars: Optional[Dict] = None):
        if not self._ansible_runner or \
           self._ansible_runner_nodes != nodes:
            # Create a new AnsibleRunner if the nodes dict has changed (to
            # generate a new inventory).
            self._ansible_runner = AnsibleRunner(self, nodes, inventory_vars)
            self._ansible_runner_nodes = nodes.copy()

        return self._ansible_runner.run_play_raw(playbook)

    def _execute_ansible_play(self, play_source: Dict,
                              nodes: Dict[str, NodeBase],
                              inventory_vars: Optional[Dict] = None):
        if not self._ansible_runner or \
           self._ansible_runner_nodes != nodes:
            # Create a new AnsibleRunner if the nodes dict has changed (to
            # generate a new inventory).
            self._ansible_runner = AnsibleRunner(self, nodes, inventory_vars)
            self._ansible_runner_nodes = nodes.copy()

        return self._ansible_runner.run_play(play_source)

    def execute_ansible_play(self, play_source: Dict,
                             nodes: Dict[str, NodeBase],
                             inventory_vars: Optional[Dict] = None):
        r = self._execute_ansible_play(play_source, nodes, inventory_vars)
        failure = False
        if r.host_unreachable:
            logger.error("One or more hosts were unreachable")
            logger.error(pformat(r.host_unreachable))
            failure = True
        if r.host_failed:
            logger.error("One or more hosts failed")
            logger.error(pformat(r.host_failed))
            failure = True
        if failure:
            logger.debug("The successful hosts returned:")
            logger.debug(pformat(r.host_ok))
            raise Exception(
                f"Failure running ansible playbook {play_source['name']}")
        return r

    @contextlib.contextmanager
    def chdir(self, path=None):
        """A context manager which changes the working directory to the given
        path, and then changes it back to its previous value on exit.

        """
        if not path:
            path = self.working_dir
        prev_cwd = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(prev_cwd)

    def _get_working_dir(self):
        working_dir_path = os.path.join(
            config.WORKSPACE_DIR, self.name
        )
        os.makedirs(working_dir_path)
        return working_dir_path

    def destroy(self):
        # This kills the SSH_AGENT_PID agent
        try:
            subprocess.run(
                ['ssh-agent', '-k'],
                check=True,
                env={
                    'SSH_AUTH_SOCK': self.ssh_agent_auth_sock,
                    'SSH_AGENT_PID': self.ssh_agent_pid,
                }
            )
        except subprocess.CalledProcessError:
            logger.exception(f'Killing ssh-agent with PID'
                             f' {self._ssh_agent_pid} failed')

        if config._REMOVE_WORKSPACE:
            logger.info(f"Removing workspace {self.working_dir} from disk")
            shutil.rmtree(self.working_dir)
        else:
            logger.info(f"Keeping workspace on disk at {self.working_dir}")

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
