# Copyright (c) 2019 SUSE LINUX GmbH
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 3 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

from abc import ABC, abstractmethod
from typing import Dict, Any

from tests import config


class NodeBase(ABC):
    """
    Base class for nodes
    """
    def __init__(self, name: str, private_key: str):
        self.name = name
        self.private_key = private_key

    @abstractmethod
    def get_ssh_ip(self) -> str:
        """
        Get the IP address that can be used to ssh into the node
        """
        pass

    def ansible_inventory_vars(self) -> Dict[str, Any]:
        vars = {
            'ansible_host': self.get_ssh_ip(),
            # FIXME(jhesketh): Set username depending on OS
            'ansible_user': config.NODE_IMAGE_USER,
            'ansible_ssh_private_key_file': self.private_key,
            'ansible_host_key_checking': False,
            'ansible_ssh_host_key_checking': False,
            'ansible_scp_extra_args': '-o StrictHostKeyChecking=no',
            'ansible_ssh_extra_args': '-o StrictHostKeyChecking=no',
            'ansible_python_interpreter': '/usr/bin/python3',
            'ansible_become': False,
        }
        if config.NODE_IMAGE_USER != "root":
            vars['ansible_become'] = True
            vars['ansible_become_method'] = 'sudo'
            vars['ansible_become_user'] = 'root'
        return vars
