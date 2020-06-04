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

import logging
import os
import shutil
import yaml

logger = logging.getLogger(__name__)


class AnsibleRunner(object):
    def __init__(self, workspace, nodes):
        self._workspace = workspace
        self._nodes = nodes

        # create inventory, use path to host config file as source or hosts in
        # a comma separated string
        self.inventory_dir = self.create_inventory()

    @property
    def workspace(self):
        return self._workspace

    @property
    def nodes(self):
        return self._nodes

    def create_inventory(self):
        inventory_dir = os.path.join(self.workspace.working_dir, 'inventory')
        group_vars_dir = os.path.join(inventory_dir, 'group_vars')
        group_vars_all_dir = os.path.join(group_vars_dir, 'all')

        # drop old inventory dir if available
        if os.path.exists(inventory_dir):
            shutil.rmtree(inventory_dir)
            logger.info("deleted current ansible inventory "
                        f"dir f{inventory_dir}")

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

        nodes_inv_path = os.path.join(inventory_dir, "nodes.yml")
        with open(nodes_inv_path, 'w') as inv_file:
            yaml.dump(inv, inv_file)

        logger.info('Inventory path: {}'.format(inventory_dir))
        return inventory_dir

    def run_play_raw(self, playbook):
        path = os.path.abspath(os.path.join(
            os.path.dirname(__file__), '../assets/ansible', playbook
        ))
        logger.info(f'Running playbook {path}')
        self.workspace.execute(
            f"ansible-playbook -i {self.inventory_dir} {path}")
