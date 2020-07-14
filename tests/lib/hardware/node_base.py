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
from abc import ABC, abstractmethod
from enum import Enum
from typing import Dict, Any, List

from tests.config import settings


logger = logging.getLogger(__name__)


class NodeRole(Enum):
    MASTER = 0
    WORKER = 1


class NodeBase(ABC):
    """
    Base class for nodes
    """
    def __init__(self, name: str, role: NodeRole, tags: List[str] = []):
        self._name = name
        self.dnsname = self.name.replace('_', '-')
        self._role = role
        self.tags = tags
        self._disks: Dict[str, Any] = {}

    @abstractmethod
    def boot(self):
        """
        Boot a node so the node is ready to be used (eg. via get_ssh_ip())
        """
        pass

    @abstractmethod
    def get_ssh_ip(self) -> str:
        """
        Get the IP address that can be used to ssh into the node
        """
        pass

    # TODO: We need to add three methods actually
    # disk_create
    # disk_attach
    # disk_detach
    @abstractmethod
    def disk_create(self, capacity):
        """
        Create a disk volume
        """
        pass

    @abstractmethod
    def disk_attach(self, capacity):
        """
        Attach a disk volume
        """
        pass

    @abstractmethod
    def disk_detach(self, capacity):
        """
        Detach a disk volume
        """
        pass

    @property
    def name(self):
        return self._name

    @property
    def role(self):
        return self._role

    def ansible_inventory_vars(self) -> Dict[str, Any]:
        vars = {
            'ansible_host': self.get_ssh_ip(),
            # FIXME(jhesketh): Set username depending on OS
            'ansible_user': settings.NODE_IMAGE_USER,
        }
        if settings.NODE_IMAGE_USER != "root":
            vars['ansible_become'] = 'true'
            vars['ansible_become_method'] = 'sudo'
            vars['ansible_become_user'] = 'root'
        return vars

    @abstractmethod
    def destroy(self):
        pass
