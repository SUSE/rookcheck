# Copyright (c) 2020 SUSE LINUX GmbH
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


# This module should take care of deploying kubernetes. There will likely be
# multiple variations of an abstract base class to do so. However, the
# implementation may need to require a certain base OS. For example, skuba
# would require SLE and can raise an exception if that isn't provided.

import logging
import os
import subprocess
from tests.lib.kubernetes.kubernetes_base import KubernetesBase
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.workspace import Workspace


logger = logging.getLogger(__name__)


class CaaSP(KubernetesBase):
    def __init__(self, workspace: Workspace, hardware: HardwareBase):
        super().__init__(workspace, hardware)
        self._clusterpath = os.path.join(self.workspace.working_dir, 'cluster')
        self._kubeconfig = os.path.join(self.workspace.working_dir,
                                        'admin.conf')
        self._ssh_agent_auth_sock = os.path.join(hardware.working_dir,
                                                 'ssh-agent.sock')
        self._ssh_agent()

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
        os.environ['SSH_AUTH_SOCK'] = self._ssh_agent_auth_sock
        os.environ['SSH_AGENT_PID'] = self._ssh_agent_pid
        try:
            res = subprocess.run(['ssh-add', self.hardware._private_key],
                                 check=True)
        except subprocess.CalledProcessError:
            logger.exception('Failed to add keys to agent')
            raise

    def destroy(self, skip=False):
        logger.info(f"kube destroy on hardware {self.hardware}")
        if skip:
            # We can skip in most cases since the nodes themselves will be
            # destroyed instead.
            return
        # This kills the SSH_AGENT_PID agent
        try:
            subprocess.run(['ssh-agent', '-k'], check=True)
        except subprocess.CalledProcessError:
            logger.exception(f'Killing ssh-agent with PID \
{self._ssh_agent_pid} failed')

        # TODO(jhesketh): Uninstall kubernetes

    def install_kubernetes(self):
        super().install_kubernetes()
        self.hardware.execute_ansible_play_raw('playbook_caasp.yaml')
        self.hardware.get_masters()
        self.hardware.get_workers()
        self._caasp_init()
        with self.workspace.chdir(self._clusterpath):
            self._caasp_bootstrap()
        with self.workspace.chdir(self._clusterpath):
            self._caasp_join()

    def _caasp_init(self):
        try:
            res = subprocess.run(
                ['skuba', 'cluster', 'init', '--control-plane',
                 self.hardware.masters[0].get_ssh_ip(),
                 self._clusterpath], check=True)
            logger.debug(res.args)
        except subprocess.CalledProcessError:
            logger.exception('Cluster init step failed')
            raise

    def _caasp_bootstrap(self):
        try:
            res = subprocess.run(
                ['skuba', 'node', 'bootstrap', '--user', 'sles', '--sudo',
                 '--target', self.hardware.masters[0].get_ssh_ip(),
                 self.hardware.masters[0].dnsname], check=True)
            logger.debug(res.args)
        except subprocess.CalledProcessError:
            logger.exception('Cluster bootsrap step failed')
            raise

    def _caasp_join(self):
        for worker in self.hardware.workers:
            try:
                res = subprocess.run(
                    ['skuba', 'node', 'join', '--role', 'worker',
                     '--user', 'sles', '--sudo', '--target',
                     worker.get_ssh_ip(), worker.dnsname], check=True)
                logger.debug(res.args)
            except subprocess.CalledProcessError:
                logger.exception(
                    f'Node {worker.dnsname} failed to join cluster')
                raise
