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
from typing import List
import threading
import re
import time

from tests.lib.kubernetes.kubernetes_base import KubernetesBase
from tests.lib.hardware.hardware_base import HardwareBase
from tests.lib.hardware.node_base import NodeBase, NodeRole
from tests.lib.workspace import Workspace
from tests.lib import common


logger = logging.getLogger(__name__)


class CaaSP(KubernetesBase):
    def __init__(self, workspace: Workspace, hardware: HardwareBase):
        super().__init__(workspace, hardware)
        self._clusterpath = os.path.join(self.workspace.working_dir, 'cluster')
        self._kubeconfig = os.path.join(
            self.workspace.working_dir, 'cluster', 'admin.conf')
        self._skuba = os.path.join(self.workspace.working_dir, 'bin/skuba')

    def bootstrap(self):
        super().bootstrap()
        self.hardware.ansible_run_playbook('playbook_caasp.yaml')
        self.workspace.execute(f"{self._skuba} cluster init --control-plane "
                               f"{self.hardware.masters[0].get_ssh_ip()} "
                               f"{self._clusterpath}", capture=True,
                               check=True)

        logger.info("skuba node bootstrap. This may take a while")
        self.workspace.execute(
            f"{self._skuba} node bootstrap --user sles --sudo --target"
            f" {self.hardware.masters[0].get_ssh_ip()}"
            f" {self.hardware.masters[0].name}", capture=True,
            check=True, chdir=self._clusterpath
        )

    def _skuba_join(self, node: NodeBase):
        if node.role == NodeRole.WORKER:
            role = 'worker'
        else:
            role = 'master'

        self.workspace.execute(
            f"{self._skuba} node join --role {role} --user sles --sudo "
            f"--target {node.get_ssh_ip()} {node.name}",
            capture=True, check=True, chdir=self._clusterpath
        )

    def join(self, nodes: List[NodeBase]):
        super().join(nodes)

        self.hardware.ansible_run_playbook('playbook_caasp.yaml', nodes)

        # join nodes in parallel
        threads = []
        for node in nodes:
            t = threading.Thread(target=self._skuba_join, args=(node,))
            threads.append(t)
            t.start()
        # wait for all threads to finish
        for t in threads:
            t.join()

        # Mark the worker nodes for any role:
        for node in nodes:
            if node.role == NodeRole.WORKER:
                self.kubectl(
                    f"label node {node.name} node-role.rook-ceph/cluster=any")

    def install_kubernetes(self):
        super().install_kubernetes()
        self.join(self.hardware.workers)
        logger.info("Wait for all nodes to be in 'Ready' state"
                    "(this may take a while...)")
        pattern = re.compile(r' +Ready.*')
        common.wait_for_result(
            self.workspace.execute, f"{self._skuba} cluster status",
            matcher=common.regex_count_matcher(
                pattern, len(self.hardware.nodes)),
            attempts=60,
            interval=10,
            chdir=self._clusterpath,
            capture=True)
        # Give skupa-update/zypper some time to release lock
        time.sleep(5)
