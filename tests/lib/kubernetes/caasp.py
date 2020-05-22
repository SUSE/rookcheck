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
        self._kubeconfig = os.path.join(self.workspace.working_dir, 'cluster',
                                        'admin.conf')
        # FIXME(toabctl): The CaaSP implementation is not downloading the
        # 'kubectl' executable so it's not available in the workspace dir.
        # We currently just assume that on the local machine, 'kubectl'
        # is available
        self._kubectl_exec = 'kubectl'

    def bootstrap(self):
        super().bootstrap()
        self.hardware.execute_ansible_play_raw('playbook_caasp.yaml')
        self._caasp_init()
        with self.workspace.chdir(self._clusterpath):
            self._caasp_bootstrap()

    def install_kubernetes(self):
        super().install_kubernetes()
        with self.workspace.chdir(self._clusterpath):
            self._caasp_join()

    def _caasp_init(self):
        try:
            self.workspace.execute("skuba cluster init --control-plane "
                                   f"{self.hardware.masters[0].get_ssh_ip()} "
                                   f"{self._clusterpath}", capture=True)
        except subprocess.CalledProcessError as e:
            logger.exception('skuba cluster init failed: '
                             f'{e.stdout}\n{e.stderr}')
            raise

    def _caasp_bootstrap(self):
        try:
            logger.info("skube node bootstrap. This may take a while")
            self.workspace.execute(
                "skuba node bootstrap --user sles --sudo --target"
                f" {self.hardware.masters[0].get_ssh_ip()}"
                f" {self.hardware.masters[0].dnsname}", capture=True,
                chdir=self._clusterpath
            )
        except subprocess.CalledProcessError as e:
            logger.exception('skuba node bootstrap failed: '
                             f'{e.stdout}\n{e.stderr}')
            raise

    def _caasp_join(self):
        for worker in self.hardware.workers:
            try:
                self.workspace.execute(
                    "skuba node join --role worker --user sles --sudo "
                    f"--target {worker.get_ssh_ip()} {worker.dnsname}",
                    capture=True, chdir=self._clusterpath
                )
            except subprocess.CalledProcessError as e:
                logger.exception(
                    f'skuba node join worker for  {worker.dnsname} failed: '
                    f'{e.stdout}\n{e.stderr}')
                raise
