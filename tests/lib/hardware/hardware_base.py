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
# There will be a challenge where those arbitrary commands differ between OS's;
# this is an abstraction that is not yet well figured out, but will likely
# take the form of cloud-init or similar bringing the target node to an
# expected state.

from abc import ABC, abstractmethod
import json
import os
import yaml
import shutil
import logging
from typing import Dict, List
import threading

from tests.config import settings
from tests.lib.common import handle_cleanup_input
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
        self._ansible_inventory_dir = os.path.join(self.workspace.working_dir,
                                                   'inventory')
        # when nodes are created in threads, we need to lock the recreation
        # of the ansible inventory dir
        self._ansible_create_inventory_lock = threading.Lock()

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

    def destroy(self, skip=False):
        if skip:
            logger.warning("Hardware will not be removed!")
            logger.warning("The following nodes and their associated resources"
                           " (such as IP's and volumes) will remain:")
            for n in self.nodes.values():
                logger.warning(f"Leaving node {n.name} at ip {n.get_ssh_ip()}")
                logger.warning(f".. with volumes {n._disks}")
                # TODO(jhesketh): Neaten up how disks are handled
            return

        if settings.as_bool('_TEAR_DOWN_CLUSTER_CONFIRM'):
            handle_cleanup_input("pause before cleanup hardware")

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
        with self._ansible_create_inventory_lock:
            self._ansible_create_inventory()

    def node_remove(self, node: NodeBase):
        logger.info(f"removing node {node.name} from hardware {self}")
        del self.nodes[node.name]
        with self._ansible_create_inventory_lock:
            self._ansible_create_inventory()
        node.destroy()

    @abstractmethod
    def boot_nodes(self, masters: int, workers: int, offset: int = 0):
        logger.info("boot nodes")

    def prepare_nodes(self, limit_to_nodes: List[NodeBase] = []):
        logger.info("prepare nodes")
        self.ansible_run_playbook("playbook_node_base.yml", limit_to_nodes)

    def ansible_run_playbook(self, playbook: str,
                             limit_to_nodes: List[NodeBase] = [],
                             extra_vars={}):
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '../../assets/ansible', playbook
        ))

        if limit_to_nodes:
            limit = "--limit " + ":".join([n.name for n in limit_to_nodes])
        else:
            limit = ""

        extra_vars_param = ""
        if extra_vars:
            extra_vars_param += f" --extra-vars '{json.dumps(extra_vars)}'"
        if settings.ANSIBLE_EXTRA_VARS:
            extra_vars_param += f" --extra-vars "\
                                f" '{settings.ANSIBLE_EXTRA_VARS}'"

        logger.info(f'Running playbook {path} ({limit})')
        self.workspace.execute(
            f"ansible-playbook -i {self._ansible_inventory_dir} "
            f"{limit} {extra_vars_param} {path}",
            logger_name=f"ansible {playbook}")

    def _ansible_create_inventory(self):
        """
        Create an ansible inventory/ directory structure which will
        be used during ansible-playbook runs
        """
        group_vars_dir = os.path.join(self._ansible_inventory_dir,
                                      'group_vars')
        group_vars_all_dir = os.path.join(group_vars_dir, 'all')

        # drop old inventory dir if available
        if os.path.exists(self._ansible_inventory_dir):
            shutil.rmtree(self._ansible_inventory_dir)
            logger.info("deleted current ansible inventory "
                        f"dir {self._ansible_inventory_dir}")

        # create a inventory & group_vars directory
        os.makedirs(group_vars_all_dir)

        # write hardware groups vars which are useful for *all* nodes
        group_vars_all_common = os.path.join(group_vars_all_dir, 'common.yml')
        with open(group_vars_all_common, 'w') as f:
            yaml.dump(self.workspace.ansible_inventory_vars(), f)

        # write node specific inventory
        inv = {
            'all': {
                'hosts': {},
                'children': {}
            }
        }

        for node in self.nodes.values():
            if not node.tags:
                inv['all']['hosts'][node.name] = node.ansible_inventory_vars()
            else:
                for tag in node.tags:
                    if tag not in inv['all']['children']:
                        inv['all']['children'][tag] = {'hosts': {}}
                    inv['all']['children'][tag]['hosts'][node.name] = \
                        node.ansible_inventory_vars()

        nodes_inv_path = os.path.join(self._ansible_inventory_dir, "nodes.yml")
        with open(nodes_inv_path, 'w') as inv_file:
            yaml.dump(inv, inv_file)

        logger.info('Inventory path: {}'.format(self._ansible_inventory_dir))

    def _get_node_by_role(self, role: NodeRole):
        items = []
        for node_name, node_obj in self.nodes.items():
            if node_obj._role == role:
                items.append(node_obj)
        return items

    def __enter__(self):
        return self

    def __exit__(self, type, value, traceback):
        self.destroy(skip=not settings.as_bool('_TEAR_DOWN_CLUSTER'))
