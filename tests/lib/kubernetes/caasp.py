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
import contextlib
from tests.lib.kubernetes.kubernetes_base import KubernetesBase


logger = logging.getLogger(__name__)


class CaaSP(KubernetesBase):
    def __init__(self, hardware):
        super().__init__(hardware)
        self._clusterpath = os.path.join(hardware.working_dir, 'cluster')
        self._kubeconfig = os.path.join(self.hardware.working_dir,
                                        'admin.conf')
        self._ssh_agent()

    def _ssh_agent(self):
        try:
            res = subprocess.run(['ssh-agent'], check=True,
                                 capture_output=True)
        except subprocess.CalledProcessError:
            msg = 'Failed to start ssh agent'
            logger.exception(msg)
            raise

        self._ssh_agent_auth_sock = res.stdout.decode(
            'utf-8').split(';')[0].split('=')[1]
        self._ssh_agent_pid = res.stdout.decode(
            'utf-8').split(';')[2].split('=')[1]
        os.environ['SSH_AUTH_SOCK'] = self._ssh_agent_auth_sock
        os.environ['SSH_AGENT_PID'] = self._ssh_agent_pid
        try:
            res = subprocess.run(['ssh-add', self.hardware._private_key],
                                 check=True)
        except subprocess.CalledProcessError:
            msg = 'Failed to add keys to agent'
            logger.exception(msg)
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
        with self._working_directory(self._clusterpath):
            self._caasp_bootstrap()
        with self._working_directory(self._clusterpath):
            self._caasp_join()

    def _caasp_init(self):
        try:
            res = subprocess.run(
                ['skuba', 'cluster', 'init', '--control-plane',
                 self.hardware.masters[0].get_ssh_ip(),
                 self._clusterpath], check=True)
            logger.debug(res.args)
        except subprocess.CalledProcessError:
            msg = 'Cluster init step failed'
            logger.exception(msg)
            raise

    def _caasp_bootstrap(self):
        try:
            res = subprocess.run(
                ['skuba', 'node', 'bootstrap', '--user', 'sles', '--sudo',
                 '--target', self.hardware.masters[0].get_ssh_ip(),
                 self.hardware.masters[0].dnsname], check=True)
            logger.debug(res.args)
        except subprocess.CalledProcessError:
            msg = 'Cluster bootsrap step failed'
            logger.exception(msg)
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
                msg = f'Node {worker.dnsname} failed to join cluster'
                logger.exception(msg)
                raise

    @contextlib.contextmanager
    def _working_directory(self, path):
        """A context manager which changes the working directory to the given
        path, and then changes it back to its previous value on exit.

        """
        prev_cwd = os.getcwd()
        os.chdir(path)
        try:
            yield
        finally:
            os.chdir(prev_cwd)
