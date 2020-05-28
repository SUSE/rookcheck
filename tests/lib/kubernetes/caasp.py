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

from tests.lib.kubernetes.kubernetes_base import KubernetesBase
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase, NodeRole
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
        self.workspace.execute("skuba cluster init --control-plane "
                               f"{self.hardware.masters[0].get_ssh_ip()} "
                               f"{self._clusterpath}", capture=True,
                               check=True)

        logger.info("skuba node bootstrap. This may take a while")
        self.workspace.execute(
            "skuba node bootstrap --user sles --sudo --target"
            f" {self.hardware.masters[0].get_ssh_ip()}"
            f" {self.hardware.masters[0].dnsname}", capture=True,
            check=True, chdir=self._clusterpath
        )

    def join(self, node: NodeBase):
        super().join(node)
        if node.role == NodeRole.WORKER:
            role = 'worker'
        else:
            role = 'master'

        self.workspace.execute(
            f"skuba node join --role {role} --user sles --sudo "
            f"--target {node.get_ssh_ip()} {node.dnsname}",
            capture=True, check=True, chdir=self._clusterpath
        )

    def install_kubernetes(self):
        super().install_kubernetes()
        for worker in self.hardware.workers:
            self.join(worker)
