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

from abc import ABC, abstractmethod
import logging
from typing import Dict, List

from tests.lib.distro import get_distro
from tests.lib.hardware.node_base import NodeBase, NodeRole

from tests.lib.workspace import Workspace

logger = logging.getLogger(__name__)


class HardwareBase(ABC):
    """
    Base Hardware class
    """
    def __init__(self, workspace: Workspace):
        self._workspace = workspace
        self._nodes: Dict[str, NodeBase] = {}
        self._conn = self.get_connection()

        logger.info(f"hardware {self}: Using {self.workspace.name}")

    @property
    def workspace(self):
        return self._workspace

    @property
    def conn(self):
        return self._conn

    @property
    def nodes(self):
        return self._nodes

    @property
    def masters(self) -> List[NodeRole]:
        return self._get_node_by_role(NodeRole.MASTER)

    @property
    def workers(self) -> List[NodeRole]:
        return self._get_node_by_role(NodeRole.WORKER)

    def _node_remove_ssh_key(self, node: NodeBase):
        # The mitogen plugin does not correctly ignore host key checking, so we
        # should remove any host keys for our nodes before starting.
        # The 'ssh' connection imports ssh-keys for us, so as a first step we
        # run a standard ssh connection to do the imports. We could import the
        # sshkeys manually first, but we also want to wait on the connection to
        # be available (in order to even be able to get them).
        # Therefore simply remove any entries from your known_hosts. It's also
        # helpful to do this after a build to clean up anything locally.
        logger.info(
            f"Removing {node.get_ssh_ip()} from known-hosts if exists.")
        self.workspace.execute(
            f"ssh-keygen -R {node.get_ssh_ip()}", check=False,
            log_stderr=False)

    def destroy(self):
        logger.info("Remove all nodes from Hardware")
        for n in list(self.nodes):
            self.node_remove(self.nodes[n])

    @abstractmethod
    def get_connection(self):
        pass

    @abstractmethod
    def node_create(self, name: str, role: NodeRole,  # type: ignore
                    tags: List[str]) -> NodeBase:
        """
        Create a new Node object and return it
        """
        logger.info(f"creating a new node for hardware {self}")

    def node_add(self, node: NodeBase):
        logger.info(f"adding new node {node.name} to hardware {self}")
        self._node_remove_ssh_key(node)
        self.nodes[node.name] = node

    def node_remove(self, node: NodeBase):
        logger.info(f"removing node {node.name} from hardware {self}")
        del self.nodes[node.name]
        node.destroy()

    @abstractmethod
    def boot_nodes(self, masters: int = 1, workers: int = 2, offset: int = 0):
        logger.info("boot nodes")

    def prepare_nodes(self):
        logger.info("prepare nodes")
        d = get_distro()()

        self.execute_ansible_play(d.wait_for_connection_play())
        self.execute_ansible_play(d.bootstrap_play())

    def execute_ansible_play_raw(self, playbook):
        return self.workspace.execute_ansible_play_raw(playbook, self.nodes)

    def execute_ansible_play(self, play_source):
        return self.workspace.execute_ansible_play(play_source, self.nodes)

    def _get_node_by_role(self, role: NodeRole):
        items = []
        for node_name, node_obj in self.nodes.items():
            if node_obj._role == role:
                items.append(node_obj)
        return items

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy()
